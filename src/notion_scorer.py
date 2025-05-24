import os
import json
import re
from src.openrouter import OpenRouterClient

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
• Return **only** valid JSON - no trailing commas, no comments, no extra text.
• Ensure all strings are properly quoted and escaped.
• Double-check JSON syntax before responding.
• Use EXACTLY these field names (required):

REQUIRED FIELDS:
- "IDO": "Yes" or "No"
- "IDO_Rationale": "string explanation"
- "Investment": "Yes" or "No"
- "Investment_Rationale": "string explanation"
- "Advisory": "Yes" or "No"
- "Advisory_Rationale": "string explanation"
- "BullCase": "string"
- "BearCase": "string"
- "Conviction": "BullCase" or "BearCase"
- "Comments": "string"

RETURN ONLY JSON WITH THESE EXACT FIELD NAMES.
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

def _clean_and_fix_json(text: str) -> str:
    """Clean and fix common JSON formatting issues."""
    if not text:
        return ""
    
    # Remove any text before the first { and after the last }
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx == -1 or end_idx == -1:
        return ""
    
    json_text = text[start_idx:end_idx + 1]
    
    # Common fixes for malformed JSON
    fixes = [
        # Remove trailing commas before closing braces/brackets
        (r',\s*}', '}'),
        (r',\s*]', ']'),
        
        # Fix unescaped quotes in strings
        (r'(?<!")([^",\{\}\[\]:]+)"(?=[,\}\]])', r'"\1"'),
        
        # Fix broken strings with newlines
        (r'"\s*\n\s*([^"]*)\s*\n\s*"', r'"\1"'),
        
        # Fix incomplete field values
        (r':\s*"[^"]*$', ': ""'),
        
        # Remove duplicate field definitions (keep the last one)
        (r'("[^"]+"):\s*"[^"]*",?\s*\1:', r'\1:'),
        
        # Fix field names that got split across lines
        (r'"\s*\n\s*([^"]+)\s*\n\s*":', r'"\1":'),
        
        # Fix broken field names
        (r'"[^"]*\n[^"]*":', r'"broken_field":'),
    ]
    
    for pattern, replacement in fixes:
        json_text = re.sub(pattern, replacement, json_text, flags=re.MULTILINE | re.DOTALL)
    
    # Ensure the JSON ends properly
    if not json_text.strip().endswith('}'):
        json_text = json_text.rstrip() + '}'
    
    return json_text

def _transform_wrong_format(data: dict) -> dict:
    """Transform incorrectly formatted scoring data to expected format."""
    _logger.info("action=transforming_format available_keys=%s", list(data.keys()))
    
    # Try to extract meaningful information from wrong format and map to correct format
    result = {
        "IDO": "No",
        "IDO_Rationale": "Unable to determine from available data",
        "Investment": "No", 
        "Investment_Rationale": "Insufficient structured data for recommendation",
        "Advisory": "No",
        "Advisory_Rationale": "Data format mismatch - manual review needed",
        "BullCase": "Project shows potential based on available information",
        "BearCase": "Analysis incomplete due to data format issues",
        "Conviction": "BearCase",
        "Comments": "Original analysis used non-standard format - manual review recommended"
    }
    
    # Try to extract useful information from the wrong format
    if "overall_score" in data:
        score = data.get("overall_score", 0)
        if isinstance(score, (int, float)) and score > 7.5:
            result["Investment"] = "Yes"
            result["Investment_Rationale"] = f"High overall score of {score}/10 indicates strong potential"
            result["BullCase"] = f"Project scored {score}/10 in comprehensive analysis"
            result["Conviction"] = "BullCase"
    
    if "recommendation" in data:
        rec = str(data.get("recommendation", "")).lower()
        if "invest" in rec or "recommend" in rec or "positive" in rec:
            result["Investment"] = "Yes"
            result["Investment_Rationale"] = f"Positive recommendation: {data['recommendation']}"
    
    # Extract project name if available
    if "project_name" in data:
        result["Comments"] = f"Analysis for {data['project_name']} - format transformation applied"
    
    _logger.info("action=format_transformation_complete")
    return result

async def _fallback_simple_scoring(client, ddq_text: str, ai_text: str, calls_text: str, freeform_text: str) -> dict:
    """Fallback with simplified scoring when complex JSON fails."""
    _logger.info("action=fallback_scoring_attempt")
    
    simple_prompt = f"""
Based on this project information, provide a simple investment assessment:

PROJECT INFO:
{ddq_text[:1000]}...

RESEARCH REPORT:
{ai_text[:1000]}...

Return ONLY this JSON format (no extra text):
{{
  "IDO": "Yes or No",
  "IDO_Rationale": "Brief explanation",
  "Investment": "Yes or No", 
  "Investment_Rationale": "Brief explanation",
  "Advisory": "Yes or No",
  "Advisory_Rationale": "Brief explanation",
  "BullCase": "Brief bull case",
  "BearCase": "Brief bear case",
  "Conviction": "BullCase or BearCase",
  "Comments": "Overall assessment"
}}
"""
    
    response = await client.generate_response(
        prompt=simple_prompt,
        system_prompt="You are an investment analyst. Return only valid JSON with the exact format requested.",
        temperature=0.0
    )
    
    if not response:
        raise RuntimeError("Fallback scoring got empty response")
    
    # Try to parse the simplified response
    cleaned = _clean_and_fix_json(response)
    if cleaned:
        try:
            result = json.loads(cleaned)
            _logger.info("action=fallback_scoring_success fields=%s", list(result.keys()))
            
            # Ensure required fields are present with default values
            required_fields = {
                "IDO": "No",
                "IDO_Rationale": "Unable to determine from available information",
                "Investment": "No", 
                "Investment_Rationale": "Insufficient data for investment recommendation",
                "Advisory": "No",
                "Advisory_Rationale": "Limited information available for advisory assessment",
                "BullCase": "Potential for growth in cross-chain infrastructure market",
                "BearCase": "High competition and execution risks in DeFi space",
                "Conviction": "BearCase",
                "Comments": "Analysis limited by data availability - requires more detailed due diligence"
            }
            
            # Fill in missing fields
            for field, default_value in required_fields.items():
                if field not in result or not result[field] or result[field] in ['N/A', 'n/a', '']:
                    result[field] = default_value
                    _logger.info(f"action=fallback_field_defaulted field={field}")
            
            return result
        except json.JSONDecodeError as e:
            _logger.error("action=fallback_json_parse_failed error=%s response=%s", str(e), response[:200])
            
            # Ultimate fallback - return a basic structure
            _logger.info("action=ultimate_fallback_used")
            return {
                "IDO": "No",
                "IDO_Rationale": "JSON parsing failed - manual review required",
                "Investment": "No", 
                "Investment_Rationale": "Technical analysis incomplete due to parsing errors",
                "Advisory": "No",
                "Advisory_Rationale": "Unable to complete automated assessment",
                "BullCase": "Project has potential but requires manual analysis",
                "BearCase": "Technical assessment failed - risk assessment incomplete",
                "Conviction": "BearCase",
                "Comments": "Automated scoring failed - manual review recommended"
            }
    
    # If cleaning failed entirely, return ultimate fallback
    _logger.error("action=json_cleaning_failed response_preview=%s", response[:200])
    return {
        "IDO": "No",
        "IDO_Rationale": "Automated analysis failed",
        "Investment": "No", 
        "Investment_Rationale": "System error during assessment",
        "Advisory": "No",
        "Advisory_Rationale": "Technical failure in scoring system",
        "BullCase": "Unable to assess due to system error",
        "BearCase": "System failure indicates high technical risk",
        "Conviction": "BearCase",
        "Comments": "Scoring system failure - requires manual intervention"
    }

async def score_project(ddq_text: str, ai_text: str, calls_text: str, freeform_text: str) -> dict:
    client = OpenRouterClient()
    
    # Build the prompt for scoring
    user_prompt = USER_PROMPT_TEMPLATE.format(
        ddq_text=ddq_text, 
        ai_text=ai_text,
        calls_text=calls_text, 
        freeform_text=freeform_text
    )
    
    # Enhanced system prompt with better JSON instructions
    system_prompt = SYSTEM_PROMPT or """You are an expert investment analyst. Analyze the provided project information and return a comprehensive scoring assessment as valid JSON.

CRITICAL: Your response must be VALID JSON only. No trailing commas, no comments, no extra text. Ensure all strings are properly quoted and escaped.

You MUST use EXACTLY these field names in your JSON response:
{
  "IDO": "Yes or No",
  "IDO_Rationale": "explanation",
  "Investment": "Yes or No",
  "Investment_Rationale": "explanation", 
  "Advisory": "Yes or No",
  "Advisory_Rationale": "explanation",
  "BullCase": "positive case",
  "BearCase": "negative case",
  "Conviction": "BullCase or BearCase",
  "Comments": "overall assessment"
}

Return ONLY JSON with these exact field names - no other fields."""
    
    # Use OpenRouter client with more explicit JSON formatting
    response_text = await client.generate_response(
        prompt=user_prompt + "\n\nIMPORTANT: Return ONLY valid JSON with no trailing commas or syntax errors.",
        system_prompt=system_prompt,
        temperature=0.0  # Even lower temperature for consistent JSON formatting
    )
    
    if not response_text:
        raise RuntimeError("Failed to get scoring response from AI")
    
    try:
        # Parse the JSON response
        result = json.loads(response_text)
        
        # Check if result has the expected format, if not try to transform it
        expected_fields = {'IDO', 'Investment', 'Advisory', 'BullCase', 'BearCase'}
        if not any(field in result for field in expected_fields):
            _logger.info("action=attempting_format_transformation")
            result = _transform_wrong_format(result)
        
        return result
    except json.JSONDecodeError as e:
        # If direct parsing fails, try to clean and fix the JSON
        cleaned_json = _clean_and_fix_json(response_text)
        if cleaned_json:
            try:
                return json.loads(cleaned_json)
            except json.JSONDecodeError:
                pass
        
        # If still failing, try to extract JSON from the response
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            extracted_json = json_match.group()
            cleaned_extracted = _clean_and_fix_json(extracted_json)
            if cleaned_extracted:
                try:
                    return json.loads(cleaned_extracted)
                except json.JSONDecodeError:
                    pass
        
        # Log the failed response for debugging
        _logger.error("action=json_parse_failed error=%s response_preview=%s", str(e), response_text[:500])
        
        # As a last resort, try to generate a simplified response
        _logger.info("action=attempting_fallback_scoring")
        try:
            return await _fallback_simple_scoring(client, ddq_text, ai_text, calls_text, freeform_text)
        except Exception as fallback_error:
            _logger.error("action=fallback_scoring_failed error=%s", str(fallback_error))
            raise RuntimeError(f"Failed to parse JSON response: {e}. Fallback also failed: {fallback_error}. Response preview: {response_text[:500]}...")

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

async def run_project_scoring(page_id: str) -> Path:
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
    enhanced_report_md_path = reports_dir / f"enhanced_report_{page_id}.md"

    if ai_text is None:
        # Fallback to local file if API retrieval failed / page doesn't exist
        # Check for enhanced report first, then regular report
        if enhanced_report_md_path.exists():
            ai_text = enhanced_report_md_path.read_text(encoding="utf-8")
            _logger.info("action=report.loaded.source=enhanced_file bytes=%d", len(ai_text))
        elif report_md_path.exists():
            ai_text = report_md_path.read_text(encoding="utf-8")
            _logger.info("action=report.loaded.source=file bytes=%d", len(ai_text))
        else:
            raise RuntimeError(
                "AI Deep Research Report not found in Notion and local files "
                f"{enhanced_report_md_path} and {report_md_path} are missing. Run Enhanced Research first."
            )
    else:
        _logger.info("action=report.loaded.source=notion bytes=%d", len(ai_text))

    # ------------------------------------------------------------------
    # 3. Run the AI scoring
    # ------------------------------------------------------------------
    scores = await score_project(ddq_text, ai_text, calls_text, freeform_text)
    _logger.info("action=scoring.done")

    # ------------------------------------------------------------------
    # 4. Persist the results as JSON
    # ------------------------------------------------------------------
    reports_dir.mkdir(parents=True, exist_ok=True)
    score_path = reports_dir / f"score_{page_id}.json"
    score_path.write_text(json.dumps(scores, indent=2), encoding="utf-8")
    _logger.info("action=score.saved path=%s", score_path)

    return score_path

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
