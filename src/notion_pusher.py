# pusher.py
import os
from typing import List, Dict, Any, Tuple
from notion_client import Client
from pathlib import Path


# ---------------------------------------------------------------------------
# Extended Ratings *pusher* – sync JSON scores back to Notion
# ---------------------------------------------------------------------------
#
# The original *create_ratings_database* helper remains untouched so callers
# can bootstrap a 🔥 *Ratings* inline database from scratch.  The new
# *publish_ratings* orchestrator mirrors the high-level flow of
# *writer.publish_report*: it will
#
# 1. Ensure the Ratings database exists under the given project card (create
#    it only if missing).
# 2. Ensure the *AI_intern* row & its detail sub-page exist (create if needed).
# 3. Run the LLM scoring pipeline (scorer.run_project_scoring) to obtain the
#    JSON answers.
# 4. Map the first-level answers to table columns and append all *_Rationale
#    fields to the **Comments** column.
# 5. Write all question-level answers (IDO_Q*, LA_Q*) right next to the
#    numbered questions inside the detail page – skipping any
#    "HUMAN_INPUT" placeholders.
#
# Much of the retry & Notion client boilerplate copies the lightweight
# approach already used in *src.writer* to guarantee robustness.
# ---------------------------------------------------------------------------


def create_ratings_database(parent_page_id: str) -> None:
    """Create the 🔥 Ratings database directly under the given Notion page."""
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise EnvironmentError("NOTION_TOKEN environment variable not set")

    notion = Client(auth=token)

    # 1. Create the database (table) under the parent page
    db = notion.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        icon={"type": "emoji", "emoji": "🔥"},
        title=[{"type": "text", "text": {"content": "Ratings"}}],
        properties={
            "Researcher": {"title": {}},
            "Conviction": {
                "select": {
                    "options": [
                        {"name": "Bull", "color": "green"},
                        {"name": "Bear", "color": "red"},
                    ]
                }
            },
            "IDO": {
                "select": {
                    "options": [
                        {"name": "Yes", "color": "green"},
                        {"name": "No", "color": "red"},
                    ]
                }
            },
            "Advisory": {
                "select": {
                    "options": [
                        {"name": "Yes", "color": "green"},
                        {"name": "No", "color": "red"},
                    ]
                }
            },
            "Investment": {
                "select": {
                    "options": [
                        {"name": "Yes", "color": "green"},
                        {"name": "No", "color": "red"},
                    ]
                }
            },
            "Liquid Program": {
                "select": {
                    "options": [
                        {"name": "Yes", "color": "green"},
                        {"name": "No", "color": "red"},
                    ]
                }
            },
            "Bull case": {"rich_text": {}},
            "Bear case": {"rich_text": {}},
            "Max. Val. IDO/Inv": {"rich_text": {}},
            "Disclosures": {"rich_text": {}},
            "Comments": {"rich_text": {}},
        },
    )
    db_id = db["id"]

    # 2. Add default rows and fill their pages
    for name in ("Template", "AI_intern"):
        row = notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "Researcher": {"title": [{"text": {"content": name}}]},
                "IDO": {"select": {"name": "No"}},
                "Advisory": {"select": {"name": "No"}},
                "Investment": {"select": {"name": "No"}},
                "Liquid Program": {"select": {"name": "No"}},
            },
        )
        _populate_detail_page(notion, row["id"])


# ───────────────────────────────────────── helpers ──────────────────────────────────────────


def _populate_detail_page(notion: Client, page_id: str) -> None:
    """Append headings and question lists to the given page."""
    ido_questions: List[str] = [
        "Is the background of the Team reputable and legit?",
        "Does the Team have unique advantages in their niche market?",
        "Are business metrics solid?",
        "Are social metrics solid?",
        "Is the product good overall?",
        "Does the product have key differentiators?",
        "Is the project scalable for future growth?",
        "Is the valuation justified?",
        "Are the investment terms favorable?",
        "Would you invest personally?",
        "Do you expect it to pump on day 1 of the IDO?",
    ]

    liquid_questions: List[str] = [
        "Runway",
        "P/E Ratio",
        "Requires token migration / restructure cap. table",
        "Max. upside",
        "Listings",
        "Liquid sell pressure",
        "Would working with this Team be good for IF?",
        "Is the scope of work hard?",
        "Is IF a suitable partner for this Team?",
        "Does this work achieve another goal?",
        "Is the valuation justified?",
        "Is this deal the best of its class?",
        "Are the terms suitable?",
        "Would you buy the liquid token? At what max. valuation?",
        "Would you recommend IF to engage as advisors?",
    ]

    blocks: List[Dict] = []
    blocks.append(_heading("IDO Questions"))
    blocks.extend(_numbered_list(ido_questions))
    blocks.append(_heading("Liquid deals / Advisory"))
    blocks.extend(_numbered_list(liquid_questions))
    blocks.append(_heading("Information request"))
    blocks.append(_paragraph("List here the questions you would ask the Team"))
    blocks.append(_bullet("List"))

    notion.blocks.children.append(block_id=page_id, children=blocks)


def _heading(text: str) -> Dict:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _numbered_list(items: List[str]) -> List[Dict]:
    return [
        {
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {
                "rich_text": [{"type": "text", "text": {"content": item}}]
            },
        }
        for item in items
    ]


def _paragraph(text: str) -> Dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _bullet(text: str) -> Dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


# ---------------------------------------------------------------------------
# New helpers & public *publish_ratings* orchestrator
# ---------------------------------------------------------------------------


from src.notion_scorer import run_project_scoring


# ----------------------------- Notion client ------------------------------


def _notion() -> Client:
    """Return an authenticated Notion client (env var NOTION_TOKEN required)."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise RuntimeError("Environment variable NOTION_TOKEN is required.")
    # Re-use the higher default timeout used elsewhere in the codebase.
    import httpx

    timeout_cfg = httpx.Timeout(180.0, connect=10.0)
    return Client(auth=token, client=httpx.Client(timeout=timeout_cfg))


# ----------------------- database / row existence -------------------------


def _ratings_db_exists(parent_page_id: str) -> Tuple[bool, str | None]:
    """Return (exists?, database_id) for a 🔥 Ratings child-database.

    The Notion `blocks.children.list` endpoint returns at most 100 blocks per
    call.  For pages that already contain many blocks our Ratings database may
    end up beyond the first 100 items which would cause us to incorrectly
    assume it is missing and create a duplicate one on subsequent runs.  We
    therefore need to walk through **all** paginated results until we either
    find the child-database or exhaust the list.
    """

    notion = _notion()

    next_cursor: str | None = None
    while True:
        resp = notion.blocks.children.list(
            block_id=parent_page_id,
            page_size=100,
            start_cursor=next_cursor,
        )

        for blk in resp.get("results", []):
            if (
                blk.get("type") == "child_database"
                and blk["child_database"].get("title") == "Ratings"
            ):
                return True, blk["id"]

        # Collect any child_database blocks when title comparison fails
        candidate_db_ids = [
            blk["id"]
            for blk in resp.get("results", [])
            if blk.get("type") == "child_database"
        ]

        if candidate_db_ids:
            # Found at least one database – assume the first one is Ratings
            # (a parent project card is expected to have a single inline DB).
            return True, candidate_db_ids[0]

        # Pagination handling
        if resp.get("has_more") and resp.get("next_cursor"):
            next_cursor = resp["next_cursor"]
        else:
            break

    # ------------------------------------------------------------------
    # Fallback: workspace search (handles edge-cases where the inline DB is
    # not part of the first-level child blocks – e.g. inside synced blocks
    # or other container blocks – or when the Notion API omits the
    # `child_database` block in the children list for the integration).
    # ------------------------------------------------------------------

    search_results = notion.search(
        query="Ratings",
        filter={"property": "object", "value": "database"},
        page_size=100,
    )
    for res in search_results.get("results", []):
        if res.get("object") != "database":
            continue
        parent = res.get("parent", {})
        if parent.get("type") == "page_id" and parent.get("page_id") == parent_page_id:
            # Extract plain text from the title rich_text array (may be empty)
            title_parts = res.get("title", [])
            title_txt = "".join(part.get("plain_text", "") for part in title_parts)
            if title_txt.strip().lower() == "ratings":
                return True, res["id"]

    return False, None


def _ensure_ratings_db(parent_page_id: str) -> str:
    """Return database_id – creating the Ratings DB if absent."""

    exists, db_id = _ratings_db_exists(parent_page_id)
    if exists and db_id:
        return db_id

    # Create new Ratings database (and default rows) using existing helper.
    create_ratings_database(parent_page_id)

    _, db_id = _ratings_db_exists(parent_page_id)
    if not db_id:
        raise RuntimeError("Failed to locate newly created Ratings database")
    return db_id


def _ensure_ai_row(notion: Client, db_id: str) -> str:
    """Return page_id of the *AI_intern* row – create if missing."""

    query = notion.databases.query(
        database_id=db_id,
        filter={
            "property": "Researcher",
            "title": {"equals": "AI_intern"},
        },
    )
    if query.get("results"):
        return query["results"][0]["id"]

    # Create row and populate default template page.
    row = notion.pages.create(
        parent={"database_id": db_id},
        properties={
            "Researcher": {"title": [{"type": "text", "text": {"content": "AI_intern"}}]},
            "IDO": {"select": {"name": "No"}},
            "Advisory": {"select": {"name": "No"}},
            "Investment": {"select": {"name": "No"}},
            "Liquid Program": {"select": {"name": "No"}},
        },
    )
    page_id = row["id"]
    _populate_detail_page(notion, page_id)
    return page_id


# ----------------------------- JSON → table -------------------------------


def _text_prop(val: str) -> Dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": val}}]}


def _select_prop(val: str) -> Dict[str, Any]:
    return {"select": {"name": val}}


def _combine_rationales(score: Dict[str, Any]) -> str:
    """Concatenate all *_Rationale fields – newline separated."""

    parts = [f"{k}: {v}" for k, v in score.items() if k.endswith("_Rationale") and v]
    return "\n".join(parts)


# ------------------------- detail page questions --------------------------


_QUESTION_MAP: Dict[str, str] = {
    # IDO questions
    "IDO_Q1_TeamLegit": "Is the background of the Team reputable and legit?",
    "IDO_Q2_NicheAdvantage": "Does the Team have unique advantages in their niche market?",
    "IDO_Q3_BusinessMetrics": "Are business metrics solid?",
    "IDO_Q4_SocialMetrics": "Are social metrics solid?",
    "IDO_Q5_ProductQuality": "Is the product good overall?",
    "IDO_Q6_KeyDifferentiators": "Does the product have key differentiators?",
    "IDO_Q7_Scalability": "Is the project scalable for future growth?",
    "IDO_Q8_ValuationJustified": "Is the valuation justified?",
    "IDO_Q9_InvestmentTerms": "Are the investment terms favorable?",
    "IDO_Q10_InvestPersonally": "Would you invest personally?",
    "IDO_Q11_PumpDay1": "Do you expect it to pump on day 1 of the IDO?",
    # Liquid / Advisory questions
    "LA_Q1_Runway": "Runway",
    "LA_Q2_PERatio": "P/E Ratio",
    "LA_Q3_TokenMigration": "Requires token migration / restructure cap. table",
    "LA_Q4_MaxUpside": "Max. upside",
    "LA_Q5_Listings": "Listings",
    "LA_Q6_LiquidSellPressure": "Liquid sell pressure",
    "LA_Q7_WorkGoodForIF": "Would working with this Team be good for IF?",
    "LA_Q8_ScopeHard": "Is the scope of work hard?",
    "LA_Q9_IFSuitablePartner": "Is IF a suitable partner for this Team?",
    "LA_Q10_OtherGoal": "Does this work achieve another goal?",
    "LA_Q11_ValuationJustified": "Is the valuation justified?",
    "LA_Q12_BestOfClass": "Is this deal the best of its class?",
    "LA_Q13_TermsSuitable": "Are the terms suitable?",
    "LA_Q14_BuyLiquidToken": "Would you buy the liquid token? At what max. valuation?",
    "LA_Q15_RecommendAdvisory": "Would you recommend IF to engage as advisors?",
}


_REV_MAP: Dict[str, str] = {v: k for k, v in _QUESTION_MAP.items()}


def _update_detail_page(notion: Client, page_id: str, score: Dict[str, Any]) -> None:
    """Write answers next to their questions inside the AI_intern detail page."""

    # Fetch up to 200 blocks (enough for template). No need for pagination logic.
    children = notion.blocks.children.list(block_id=page_id, page_size=200)
    for blk in children.get("results", []):
        if blk.get("type") != "numbered_list_item":
            continue

        rt = blk["numbered_list_item"].get("rich_text", [])
        if not rt:
            continue

        # Extract the original question (strip any existing answer suffix)
        full_text = "".join(seg.get("plain_text") or seg["text"]["content"] for seg in rt)
        base_question = full_text.split(" - ", 1)[0].split(" – ", 1)[0].split(" — ", 1)[0].strip()

        key = _REV_MAP.get(base_question)
        if not key:
            continue  # unrelated list item

        answer = score.get(key, "")
        if not answer or answer == "HUMAN_INPUT":
            continue  # skip placeholders

        new_content = f"{base_question} – {answer}"
        if new_content == full_text:
            continue  # already up-to-date

        notion.blocks.update(
            block_id=blk["id"],
            numbered_list_item={"rich_text": [{"type": "text", "text": {"content": new_content}}]},
        )


# ------------------------------ orchestrator ------------------------------


def publish_ratings(page_id: str) -> str:
    """End-to-end helper: ensures Ratings DB exists & syncs AI_intern answers.

    Returns
    -------
    str
        The database_id of the Ratings table under *page_id*.
    """

    notion = _notion()

    # 1. Run scorer to obtain fresh JSON answers
    json_path: Path = run_project_scoring(page_id)
    score = json_path.read_text(encoding="utf-8")
    import json as _json

    score_dict: Dict[str, Any] = _json.loads(score)

    # 2. Ensure Ratings DB & AI row
    db_id = _ensure_ratings_db(page_id)
    ai_row_id = _ensure_ai_row(notion, db_id)

    # 3. Update table columns for AI_intern row
    conviction_select = "Bull" if score_dict.get("Conviction") == "BullCase" else "Bear"

    props: Dict[str, Any] = {
        "Conviction": _select_prop(conviction_select),
        "IDO": _select_prop(score_dict.get("IDO", "No")),
        "Advisory": _select_prop(score_dict.get("Advisory", "No")),
        "Investment": _select_prop(score_dict.get("Investment", "No")),
        "Liquid Program": _select_prop(score_dict.get("LiquidProgram", "No")),
        "Bull case": _text_prop(score_dict.get("BullCase", "")),
        "Bear case": _text_prop(score_dict.get("BearCase", "")),
        "Max. Val. IDO/Inv": _text_prop(
            f"IDO: {score_dict.get('MaxValuation_IDO', '')}; Investment: {score_dict.get('MaxValuation_Investment', '')}"
        ),
        "Disclosures": _text_prop(score_dict.get("Disclosures", "")),
        "Comments": _text_prop(_combine_rationales(score_dict)),
    }

    notion.pages.update(page_id=ai_row_id, properties=props)

    # 4. Update detail page answers
    _update_detail_page(notion, ai_row_id, score_dict)

    return db_id


if __name__ == "__main__":
    PARENT_PAGE_ID = os.getenv("PARENT_PAGE_ID")
    if not PARENT_PAGE_ID:
        raise EnvironmentError("PARENT_PAGE_ID environment variable not set")
    create_ratings_database(PARENT_PAGE_ID)