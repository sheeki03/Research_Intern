import os
import json
from src.openrouter_client import OpenRouterClient

SYSTEM_PROMPT = os.getenv("PROJECT_SCORER_PROMPT")

USER_PROMPT_TEMPLATE = """
## DDQ
{ddq_text}

## AI Deep Research Report
{ai_text}

## Call Notes
{calls_text}

## Card – Key Information
{freeform_text}

### Instructions
• Follow the system-prompt rules verbatim.  
• Return **only** JSON through the `score_project` function call.
"""

SCORE_PROJECT_SCHEMA = {
  "name": "score_project",
  "parameters": {
    "type": "object",
    "properties": {
      "IDO":   {"type": "string", "enum": ["Yes","No"]},
      "IDO_Rationale": {"type": "string"},
      "Advisory": {"type": "string", "enum": ["Yes","No"]},
      "Advisory_Rationale": {"type": "string"},
      "Investment": {"type": "string", "enum": ["Yes","No"]},
      "Investment_Rationale": {"type": "string"},
      "LiquidProgram": {"type": "string", "enum": ["Yes","No"]},
      "LiquidProgram_Rationale": {"type": "string"},
      "BullCase": {"type": "string"},
      "BearCase": {"type": "string"},
      "Conviction": {"type": "string", "enum": ["BullCase","BearCase"]},
      "Conviction_Rationale": {"type": "string"},
      "MaxValuation_IDO": {"type": "string"},
      "MaxValuation_IDO_Rationale": {"type": "string"},
      "MaxValuation_Investment": {"type": "string"},
      "MaxValuation_Investment_Rationale": {"type": "string"},
      "ProposedScope": {"type": "string"},
      "Comments": {"type": "string"},
      "Disclosures": {"type": "string"},
      "IDO_Q1_TeamLegit": {"type": "string"},
      "IDO_Q2_NicheAdvantage": {"type": "string"},
      "IDO_Q3_BusinessMetrics": {"type": "string"},
      "IDO_Q4_SocialMetrics": {"type": "string"},
      "IDO_Q5_ProductQuality": {"type": "string"},
      "IDO_Q6_KeyDifferentiators": {"type": "string"},
      "IDO_Q7_Scalability": {"type": "string"},
      "IDO_Q8_ValuationJustified": {"type": "string"},
      "IDO_Q9_InvestmentTerms": {"type": "string"},
      "IDO_Q10_InvestPersonally": {"type": "string"},
      "IDO_Q11_PumpDay1": {"type": "string"},
      "LA_Q1_Runway": {"type": "string"},
      "LA_Q2_PERatio": {"type": "string"},
      "LA_Q3_TokenMigration": {"type": "string"},
      "LA_Q4_MaxUpside": {"type": "string"},
      "LA_Q5_Listings": {"type": "string"},
      "LA_Q6_LiquidSellPressure": {"type": "string"},
      "LA_Q7_WorkGoodForIF": {"type": "string"},
      "LA_Q8_ScopeHard": {"type": "string"},
      "LA_Q9_IFSuitablePartner": {"type": "string"},
      "LA_Q10_OtherGoal": {"type": "string"},
      "LA_Q11_ValuationJustified": {"type": "string"},
      "LA_Q12_BestOfClass": {"type": "string"},
      "LA_Q13_TermsSuitable": {"type": "string"},
      "LA_Q14_BuyLiquidToken": {"type": "string"},
      "LA_Q15_RecommendAdvisory": {"type": "string"}
    }
  }
}

def score_project(ddq_text: str, ai_text: str, calls_text: str, freeform_text: str) -> dict:
    # Use OpenRouter with Qwen3 30B A3B (free) model
    model = os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")  # Free model
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
            ddq_text=ddq_text, ai_text=ai_text,
            calls_text=calls_text, freeform_text=freeform_text
        )}
    ]
    
    # Create OpenRouter client
    client = OpenRouterClient()
    
    # Note: OpenRouter models may not support function calling
    # So we'll use a structured prompt approach instead
    structured_prompt = f"""
{SYSTEM_PROMPT}

{USER_PROMPT_TEMPLATE.format(ddq_text=ddq_text, ai_text=ai_text, calls_text=calls_text, freeform_text=freeform_text)}

Return your response as a valid JSON object with exactly these fields:
{json.dumps(SCORE_PROJECT_SCHEMA["parameters"]["properties"], indent=2)}

Return ONLY the JSON object, no other text.
"""
    
    response = client.chat_completion(
        messages=[{"role": "user", "content": structured_prompt}],
        model=model,
        temperature=0.1,  # Low temperature for structured output
        max_tokens=4000
    )
    
    # Extract JSON from response
    content = response["choices"][0]["message"]["content"].strip()
    
    # Clean up the response to extract JSON
    if content.startswith("```json"):
        content = content[7:]
    if content.endswith("```"):
        content = content[:-3]
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        # Fallback: try to extract JSON from the response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            raise ValueError(f"Could not parse JSON response: {content}") from e

# ---------------------------------------------------------------------------
# NEW: high-level helper to score a Notion project card end-to-end
# ---------------------------------------------------------------------------

from pathlib import Path
import logging
import pathlib
from typing import Any, Dict

# Re-use the internal content fetchers implemented in research.py so we do not
# duplicate Notion access logic.  Importing the "private" helpers is OK for
# our own package.
from src.research import (
    _fetch_ddq_markdown,
    _fetch_calls_text,
    _fetch_freeform_text,
)

__all__ = [  # re-export public API of this module
    "score_project",
    "run_project_scoring",
]

# ---------------------------------------------------------------------------
# Logging – mirror the lightweight setup used by research.py & writer.py
# ---------------------------------------------------------------------------

_LOG_PATH = pathlib.Path("logs/scorer.log")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger(__name__)
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    _handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter(
            fmt="timestamp=%(asctime)s level=%(levelname)s message=%(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    _logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Public orchestration helper
# ---------------------------------------------------------------------------

def run_project_scoring(page_id: str) -> Path:
    """End-to-end wrapper that builds the context for *score_project*.

    The helper fetches the DDQ, call notes and card text for the given
    Notion *page_id*, loads the previously generated *AI Deep Research
    Report*, feeds everything into :pyfunc:`score_project` and finally
    persists the resulting JSON under ``reports/``.

    Parameters
    ----------
    page_id : str
        The Notion card ID that should be evaluated.

    Returns
    -------
    Path
        Absolute path to the newly written ``score_{page_id}.json`` file.
    """

    _logger.info("action=scoring.start page_id=%s", page_id)

    # ------------------------------------------------------------------
    # 1. Gather textual context from Notion (same helpers as research.py)
    # ------------------------------------------------------------------
    ddq_text = _fetch_ddq_markdown(page_id)
    calls_text = _fetch_calls_text(page_id)
    freeform_text = _fetch_freeform_text(page_id)

    _logger.info(
        "action=content.fetched ddq_bytes=%d calls_bytes=%d freeform_bytes=%d",
        len(ddq_text),
        len(calls_text),
        len(freeform_text),
    )

    # ------------------------------------------------------------------
    # 2. Retrieve the *AI Deep Research Report* content
    # ------------------------------------------------------------------
    ai_text: str | None = _fetch_ai_report_markdown(page_id)

    reports_dir = Path("reports")
    report_md_path = reports_dir / f"report_{page_id}.md"

    if ai_text is None:
        # Fallback to local file if API retrieval failed / page doesn't exist
        if not report_md_path.exists():
            raise RuntimeError(
                "AI Deep Research Report not found in Notion and local file "
                f"{report_md_path} is missing. Run run_deep_research() first."
            )
        ai_text = report_md_path.read_text(encoding="utf-8")
        _logger.info("action=report.loaded.source=file bytes=%d", len(ai_text))
    else:
        _logger.info("action=report.loaded.source=notion bytes=%d", len(ai_text))

    # ------------------------------------------------------------------
    # 3. Call LLM function tool *score_project*
    # ------------------------------------------------------------------
    score_dict: Dict[str, Any] = score_project(
        ddq_text=ddq_text,
        ai_text=ai_text,
        calls_text=calls_text,
        freeform_text=freeform_text,
    )
    _logger.info("action=score.generated keys=%d", len(score_dict))

    # ------------------------------------------------------------------
    # 4. Persist JSON under /reports
    # ------------------------------------------------------------------
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"score_{page_id}.json"
    json_path.write_text(json.dumps(score_dict, indent=2, ensure_ascii=False), encoding="utf-8")

    _logger.info("action=score.saved path=%s bytes=%d", json_path, json_path.stat().st_size)

    return json_path

# ---------------------------------------------------------------------------
# Helper – fetch *AI Deep Research Report* markdown from Notion (if present)
# ---------------------------------------------------------------------------

from typing import List, Any
import httpx
from notion_client import Client as NotionClient
from notion_client.errors import RequestTimeoutError
from notion_client import APIResponseError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential


def _is_retryable(exc: Exception) -> bool:  # same logic as research.py / writer.py
    if isinstance(exc, (RequestTimeoutError, httpx.TimeoutException)):
        return True
    if isinstance(exc, APIResponseError):
        if exc.code in {"internal_server_error", "service_unavailable", "rate_limited"}:
            return True
        status = getattr(exc, "status", 0) or 0
        return isinstance(status, int) and (status == 429 or status // 100 == 5)
    return False


def _tenacity() -> Retrying:
    return Retrying(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )


# Lazily import helper functions from research.py for reuse
from src.research import _list_blocks, _notion_block_to_markdown, _build_notion_client


def _fetch_ai_report_markdown(page_id: str) -> str | None:
    """Return markdown text from the *AI Deep Research Report* child page.

    If the child page does not exist the function returns ``None`` instead of
    raising so callers can gracefully fall back to local files.
    """

    client: NotionClient = _build_notion_client()

    # 1. Locate child page named exactly "AI Deep Research Report"
    for attempt in _tenacity():
        with attempt:
            children = client.blocks.children.list(block_id=page_id, page_size=100)

    report_page: dict | None = None
    for blk in children.get("results", []):
        if blk.get("type") == "child_page" and blk["child_page"]["title"] == "AI Deep Research Report":
            report_page = blk
            break

    if report_page is None:
        return None

    report_id: str = report_page["id"]
    blocks = _list_blocks(client, report_id)

    lines: List[str] = []
    for blk in blocks:
        text = _notion_block_to_markdown(blk).rstrip()
        if text:
            lines.append(text)
    return "\n".join(lines)
