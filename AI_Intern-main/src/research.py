from __future__ import annotations

"""Deep-Research wrapper utilities.

This module exposes a single public helper – ``run_deep_research`` – that
fetches the **Due-Diligence Questionnaire (DDQ)** markdown for a given
Notion card *page_id*, feeds it into the **deep_research** agent and
writes a full Markdown report to ``reports/report_{page_id}.md``.

If anything goes wrong the function raises ``RuntimeError`` so callers can
abort the pipeline early.
"""

import os                                        #---------------------------------------#
if "DEFAULT_SCRAPER" not in os.environ:          # outcomment to fall-back to playwright #
    os.environ["DEFAULT_SCRAPER"] = "firecrawl"  #---------------------------------------# 

import asyncio
import logging
import pathlib
from pathlib import Path
from typing import List, Dict, Any, cast

import httpx
from notion_client import Client as NotionClient
from notion_client.errors import RequestTimeoutError
from notion_client import APIResponseError
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

# ---------------------------------------------------------------------------
# deep_research imports – resolved lazily to avoid heavy import if unused
# ---------------------------------------------------------------------------
from web_research.ai.providers import AIClientFactory
from web_research.deep_research import deep_research as _deep_research
from web_research.deep_research import write_final_report as _write_final_report
from web_research.utils import logger as _dr_logger  # Re-use same config  # noqa: F401

__all__ = ["run_deep_research"]

# ---------------------------------------------------------------------------
# Logging – a lightweight RotatingFileHandler mirroring watcher.py
# ---------------------------------------------------------------------------
_LOG_PATH = pathlib.Path("logs/research.log")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger(__name__)
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

# Also route deep_research internal logger to the same file so that search/scrape
# diagnostics appear alongside our orchestration logs.
from web_research.utils import logger as _dp_logger  # noqa: E402
if not any(isinstance(h, logging.FileHandler) and h.baseFilename == _handler.baseFilename for h in _dp_logger.handlers):
    _dp_logger.addHandler(_handler)
    _dp_logger.setLevel(logging.INFO)

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


# ---------------------------------------------------------------------------
# Additional helper – detect whether a DDQ child page has been marked as
# completed.  We mirror the logic used in ``watcher.py`` so that both modules
# are consistent when determining which questionnaire is finished.
# ---------------------------------------------------------------------------

def _ddq_is_completed(client: NotionClient, ddq_block_id: str) -> bool:
    """Return ``True`` if the given DDQ child-page contains a completion mark.

    The heuristic replicates the one implemented in ``watcher.py``:

    1.  Scan blocks bottom-up looking for a *to-do* block – if the checkbox
        is ticked the questionnaire is considered complete.
    2.  Fallback: inspect paragraph/bullet/numbered-list items for literal
        "[x]" or "[ ]" markers (case-insensitive) which are occasionally used
        as markdown-style checkboxes inside Notion.
    """

    # Fetch **all** blocks under the questionnaire page (pagination handled)
    blocks = _list_blocks(client, ddq_block_id)

    # Walk blocks in reverse order so we reach the completion marker sooner.
    for blk in reversed(blocks):
        b_type: str = blk.get("type", "")

        if b_type == "to_do":
            return bool(blk["to_do"].get("checked", False))

        # Fallback – look for markdown-style checkboxes embedded in text
        for kind in ("paragraph", "bulleted_list_item", "numbered_list_item"):
            if b_type == kind:
                rich = blk[kind].get("rich_text", [])
                text = "".join(part.get("plain_text", "") for part in rich).lower()
                if "[x]" in text:
                    return True
                if "[ ]" in text:
                    return False

    # No explicit marker found → assume not completed
    return False


# ---------------------------------------------------------------------------
# Modified DDQ fetcher – pick the *completed* questionnaire if multiple exist
# ---------------------------------------------------------------------------

def _fetch_ddq_markdown(page_id: str) -> str:
    """Return Markdown for the *completed* DDQ questionnaire under *page_id*.

    If multiple "Due Diligence …" child-pages exist we locate the one that
    carries a completion mark (✅).  This guarantees that the deep-research
    pipeline analyses the most relevant questionnaire and ignores drafts or
    external templates still in progress.
    """

    client = _build_notion_client()

    # Gather **all** child pages whose title begins with "Due Diligence" – the
    # card may contain separate internal/external questionnaires.
    blocks = _list_blocks(client, page_id)
    ddq_candidates: List[Dict[str, Any]] = [
        b
        for b in blocks
        if b.get("type") == "child_page"
        and b["child_page"]["title"].lower().startswith("due diligence")
    ]

    # Prefer the first questionnaire that is marked as completed.
    ddq_block: Dict[str, Any] | None = None
    for cand in ddq_candidates:
        cand_id = cast(str, cand["id"])
        if _ddq_is_completed(client, cand_id):
            ddq_block = cand
            break

    if ddq_block is None:
        titles = ", ".join(b["child_page"]["title"] for b in ddq_candidates) or "<none>"
        raise RuntimeError(
            f"No completed Due Diligence questionnaire found for page {page_id}. "
            f"Candidates inspected: {titles}"
        )

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


# Research configuration from environment variables
BREADTH = int(os.getenv("RESEARCH_BREADTH",1))
DEPTH = int(os.getenv("RESEARCH_DEPTH",1))
CONCURRENCY = int(os.getenv("RESEARCH_CONCURRENCY",1))

async def _deep_research_runner(
    page_id: str,
    ddq_md_path: Path,
    *,
    breadth: int = BREADTH,
    depth: int = DEPTH,
    concurrency: int = CONCURRENCY,
) -> Path:
    """Internal async helper that orchestrates the deep-research run."""

    _logger.info("action=run.start page_id=%s", page_id)

    # ------------------------------------------------------------------
    # 1. Fetch core Notion content (DDQ + supplementary context) and persist
    #    the DDQ to disk for traceability.
    # ------------------------------------------------------------------
    ddq_text = _fetch_ddq_markdown(page_id)
    calls_text = _fetch_calls_text(page_id)
    freeform_text = _fetch_freeform_text(page_id)

    # Preserve the DDQ text exactly as before for audit/debug purposes
    ddq_md_path.write_text(ddq_text, encoding="utf-8")
    _logger.info("action=content.fetched ddq_bytes=%d calls_bytes=%d freeform_bytes=%d",
                len(ddq_text), len(calls_text), len(freeform_text))

    # ------------------------------------------------------------------
    # 2. Kick-off deep research
    # ------------------------------------------------------------------
    client = AIClientFactory.get_client("openai")
    model = AIClientFactory.get_model("openai")

    # Build the prompt that will be fed into the deep-research agent.
    header = os.getenv("DEEP_RESEARCH_PROMPT")
    research_query = (
        f"{header}\n\n"
        f"<freeform_text>\n{freeform_text}\n</freeform_text>\n\n"
        f"<calls_text>\n{calls_text}\n</calls_text>\n\n"
        f"<ddq_text>\n{ddq_text}\n</ddq_text>"
    )

    results = await _deep_research(
        query=research_query,
        breadth=breadth,
        depth=depth,
        concurrency=concurrency,
        client=client,
        model=model,
    )

    # 'learnings' is a list of distilled insights—each string is a key finding
    # produced by the deep-research agent, summarizing the most significant
    # information gathered during the DDQ analysis and web searches.
    learnings: List[str] = cast(List[str], results.get("learnings", []))
    visited_urls: List[str] = cast(List[str], results.get("visited_urls", []))
    _logger.info(
        "action=research.done learnings=%d urls=%d", len(learnings), len(visited_urls)
    )

    if visited_urls:
        _logger.info("action=research.urls %s", " ".join(visited_urls))
    else:
        _logger.warning("action=research.warning no_urls_found")

    # ------------------------------------------------------------------
    # 3. Compose final report
    # ------------------------------------------------------------------
    report_md = await _write_final_report(
        prompt=ddq_text,
        learnings=learnings,
        visited_urls=visited_urls,
        client=client,
        model=model,
    )

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"report_{page_id}.md"
    report_path.write_text(report_md, encoding="utf-8")
    _logger.info("action=report.saved path=%s bytes=%d", report_path, len(report_md))

    # ------------------------------------------------------------------
    # DEBUG: persist the exact prompt used for the LLM to the reports dir
    # so analysts can easily inspect what went into the model.
    # ------------------------------------------------------------------
    try:
        prompt_path = reports_dir / f"prompt_{page_id}.txt"
        prompt_path.write_text(research_query, encoding="utf-8")
        _logger.info("action=prompt.saved path=%s bytes=%d", prompt_path, len(research_query))
    except Exception as e:  # pragma: no cover – best-effort debug output
        _logger.warning("action=prompt.save_failed error=%s", e)

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



