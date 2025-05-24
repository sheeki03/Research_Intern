"""
High-level orchestration helper to fetch Notion DDQ content and generate
*AI Deep Research Reports* from it.

This module exposes a single public helper – ``run_deep_research`` – that
retrieves the raw content of a due diligence questionnaire (DDQ) from a
Notion project card, conducts a deep web-search analysis using the DDQ
text as input and finally persists the resulting markdown report to disk.

The bulk of the actual research logic is delegated to the external
``web_research.deep_research`` module.
"""

# Standard library imports
import os
import asyncio
import logging
import pathlib
from pathlib import Path
from typing import Any, Dict, List, cast

# Third-party imports
import httpx
from notion_client import Client as NotionClient
from notion_client.errors import RequestTimeoutError
from notion_client import APIResponseError
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

# No longer import web_research as we're using OpenRouterClient directly
# from web_research.deep_research import deep_research as _deep_research
# from web_research.deep_research import write_final_report as _write_final_report

__all__ = ["run_deep_research"]

# ---------------------------------------------------------------------------
# Logging – a lightweight RotatingFileHandler mirroring watcher.py
# ---------------------------------------------------------------------------
_LOG_PATH = pathlib.Path("logs/research.log")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger(__name__)
_handler = None

if not _logger.handlers:  # Prevent duplication during pytest reloads
    _logger.setLevel(logging.INFO)
    _handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter(
            fmt=(
                "timestamp=%(asctime)s "
                "level=%(levelname)s "
                "message=%(message)s"
            ),
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    _logger.addHandler(_handler)

# Try to route deep_research internal logger to the same file if available
try:
    from web_research.utils import logger as _dp_logger  # noqa: E402
    if _handler and not any(isinstance(h, logging.FileHandler) and h.baseFilename == _handler.baseFilename for h in _dp_logger.handlers):
        _dp_logger.addHandler(_handler)
        _dp_logger.setLevel(logging.INFO)
except ImportError:
    # web_research module not available, skip
    pass

# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _build_notion_client() -> NotionClient:
    """Create a configured Notion client from ``NOTION_TOKEN`` env var."""
    import os

    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise RuntimeError("Environment variable NOTION_TOKEN is required.")

    timeout_cfg = httpx.Timeout(180.0, connect=10.0)
    http_client = httpx.Client(timeout=timeout_cfg)
    return NotionClient(auth=token, client=http_client)


def _is_retryable(exc: Exception) -> bool:  # pragma: no cover
    if isinstance(exc, (RequestTimeoutError, httpx.TimeoutException)):
        return True
    if isinstance(exc, APIResponseError):
        retryable = {"internal_server_error", "service_unavailable", "rate_limited"}
        return exc.code in retryable or cast(int, getattr(exc, "status", 0)) // 100 == 5
    return False


def _tenacity() -> Retrying:  # small helper for consistent retry policy
    return Retrying(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )


def _list_blocks(client: NotionClient, block_id: str) -> List[Dict[str, Any]]:
    """Return *all* child blocks under the provided block (handles pagination)."""

    blocks: List[Dict[str, Any]] = []
    cursor: str | None = None

    while True:
        payload: Dict[str, Any] = {"block_id": block_id, "page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor

        for attempt in _tenacity():
            with attempt:
                resp = cast(Dict[str, Any], client.blocks.children.list(**payload))

        blocks.extend(cast(List[Dict[str, Any]], resp.get("results", [])))

        if not resp.get("has_more", False):
            break
        cursor = cast(str, resp.get("next_cursor"))
    return blocks


def _notion_block_to_markdown(block: Dict[str, Any]) -> str:
    """Very lightweight block->Markdown converter (best-effort)."""

    b_type: str = block.get("type", "unknown")
    data = block.get(b_type, {})  # type: ignore[arg-type]

    def _rich_to_text(rich: List[Dict[str, Any]]) -> str:
        return "".join(part.get("plain_text", "") for part in rich)

    if b_type in {"paragraph", "quote", "callout", "toggle"}:
        return _rich_to_text(data.get("rich_text", []))
    if b_type in {"heading_1", "heading_2", "heading_3"}:
        hashes = "#" * int(b_type[-1])
        return f"{hashes} {_rich_to_text(data.get('rich_text', []))}"
    if b_type == "bulleted_list_item":
        return f"- {_rich_to_text(data.get('rich_text', []))}"
    if b_type == "numbered_list_item":
        return f"1. {_rich_to_text(data.get('rich_text', []))}"
    if b_type == "to_do":
        chk = "x" if data.get("checked", False) else " "
        return f"- [{chk}] {_rich_to_text(data.get('rich_text', []))}"
    # fallback – ignore unsupported blocks
    return ""


def _fetch_ddq_markdown(page_id: str) -> str:
    """Fetch the DDQ sub-page for the given *page_id* and return Markdown."""

    client = _build_notion_client()

    # First list children of the main page and find the DDQ sub-page
    blocks = _list_blocks(client, page_id)
    ddq_block = next(
        (
            b
            for b in blocks
            if b.get("type") == "child_page"
            and b["child_page"]["title"].lower().startswith("due diligence")
        ),
        None,
    )
    if not ddq_block:
        raise RuntimeError(f"Page {page_id} does not contain a Due Diligence sub-page.")

    ddq_id = cast(str, ddq_block["id"])
    ddq_blocks = _list_blocks(client, ddq_id)

    markdown_lines: List[str] = []
    for blk in ddq_blocks:
        text = _notion_block_to_markdown(blk).rstrip()
        if text:
            markdown_lines.append(text)

    return "\n".join(markdown_lines)


def _fetch_calls_text(page_id: str) -> str:
    """Return Markdown-like text contained in the *Call Notes* child-page.

    If the card does not include a *Call Notes* child-page, an empty string
    is returned.  The function does *not* raise because call notes are
    considered optional context.
    """

    client = _build_notion_client()

    # Locate child-pages named *Call Notes* (case-insensitive, allow prefix)
    top_blocks = _list_blocks(client, page_id)
    call_note_pages: List[Dict[str, Any]] = [
        b
        for b in top_blocks
        if b.get("type") == "child_page"
        and b["child_page"]["title"].lower().startswith("call notes")
    ]

    if not call_note_pages:
        return ""  # nothing found – optional context

    page = call_note_pages[0]  # take the first match
    call_id = cast(str, page["id"])
    blocks = _list_blocks(client, call_id)

    lines: List[str] = []
    for blk in blocks:
        text = _notion_block_to_markdown(blk).rstrip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _fetch_freeform_text(page_id: str) -> str:
    """Return Markdown-like text from the *main card body* (non-child blocks)."""

    client = _build_notion_client()
    blocks = _list_blocks(client, page_id)

    lines: List[str] = []
    for blk in blocks:
        # Skip child-pages (DDQs, Call Notes, Ratings, etc.) – we only want
        # the free-form content directly written on the card itself.
        if blk.get("type") == "child_page":
            continue

        text = _notion_block_to_markdown(blk).rstrip()
        if text:
            lines.append(text)

    return "\n".join(lines)


async def _deep_research_runner(
    page_id: str,
    ddq_md_path: Path,
    *,
    breadth: int = 4,
    depth: int = 2,
    concurrency: int = 2,
) -> Path:
    """Internal async helper that orchestrates the deep-research run."""

    _logger.info("action=run.start page_id=%s", page_id)

    # ------------------------------------------------------------------
    # 1. Fetch DDQ markdown (and write it to disk for traceability)
    # ------------------------------------------------------------------
    ddq_markdown = _fetch_ddq_markdown(page_id)
    ddq_md_path.write_text(ddq_markdown, encoding="utf-8")
    _logger.info("action=ddq.fetched bytes=%d", len(ddq_markdown))

    # ------------------------------------------------------------------
    # 2. Kick-off deep research
    # ------------------------------------------------------------------
    from src.openrouter import OpenRouterClient
    client = OpenRouterClient()
    model = os.getenv("OPENROUTER_PRIMARY_MODEL", "qwen/qwen3-30b-a3b:free")

    # You probably already fetched ddq_markdown earlier
    research_query = f"""
Project Due Diligence Questionnaire for analysis
================================================

Act as a senior blockchain fund analyst. Read the questionnaire below, then
perform deep web-research to produce an institutional level report 
on the given project to help guide investment decision by Impossible Finance.
Your output will be covering: product, technology, traction, team, tokenomics & 
token vlue accrual, revenue model & P/E, competitive landscape, key risks, valuation, 
and a final recommend / pass.

<ddq_markdown>
{ddq_markdown}
</ddq_markdown>
""".strip()

    # Use our OpenRouter client directly instead of web_research deep_research
    research_prompt = f"""
Please analyze the following Due Diligence Questionnaire and generate a comprehensive investment analysis report:

{research_query}

Please provide detailed analysis covering:
1. Executive Summary
2. Product and Technology Assessment
3. Team and Execution Capability
4. Market Opportunity and Competitive Landscape
5. Tokenomics and Value Accrual Analysis
6. Revenue Model and Financial Projections
7. Risk Assessment
8. Investment Recommendation

Focus on actionable insights for institutional investment decision making.
"""
    
    report_md = await client.generate_response(
        prompt=research_prompt,
        system_prompt="You are a senior blockchain investment analyst at Impossible Finance. Provide comprehensive due diligence analysis for institutional investment decisions.",
        model_override=model
    )
    
    if not report_md:
        raise RuntimeError("Failed to generate research report")

    # Format the report with metadata
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    formatted_report = f"""# Due Diligence Investment Analysis Report

**Generated:** {timestamp}
**Model:** {model}
**Page ID:** {page_id}

---

{report_md}

---

*This report was generated by AI Research Agent for Impossible Finance*
"""

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"report_{page_id}.md"
    report_path.write_text(formatted_report, encoding="utf-8")

    _logger.info("action=report.saved path=%s bytes=%d", report_path, len(formatted_report))

    # ------------------------------------------------------------------
    # 4. Clean-up scraping resources (e.g. Playwright) to avoid warnings
    # ------------------------------------------------------------------
    try:
        from web_research.data_acquisition.services import search_service  # local import to avoid heavy deps upfront

        if hasattr(search_service, "cleanup"):
            await search_service.cleanup()
    except Exception as e:  # pragma: no cover – defensive, log but don't fail
        _logger.warning("action=cleanup.warning error=%s", e)

    return report_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_deep_research(page_id: str, ddq_md_path: Path | str) -> Path:
    """High-level wrapper to execute deep research synchronously.

    Parameters
    ----------
    page_id
        The Notion card's page ID (e.g. retrieved from ``poll_notion_db``).
    ddq_md_path
        Local path where the DDQ markdown will be written *before* research
        starts.  The file will be overwritten if it already exists.

    Returns
    -------
    Path
        The path to the newly-created report Markdown file under ``reports/``.

    Raises
    ------
    RuntimeError
        If any step fails (HTTP errors, OpenAI issues, etc.).
    """

    try:
        path_obj = Path(ddq_md_path)
        report_path = asyncio.run(_deep_research_runner(page_id, path_obj))
        return report_path
    except Exception as exc:
        _logger.exception("action=run.error page_id=%s", page_id)
        raise RuntimeError("Deep research failed") from exc



