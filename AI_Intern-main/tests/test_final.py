import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Pipeline entry points we want to exercise end-to-end.
from src.watcher import poll_notion_db
from src.research import run_deep_research
from src.writer import publish_report, _report_already_exists  # type: ignore
from src.scorer import run_project_scoring
from src.pusher import publish_ratings


@pytest.mark.integration
def test_full_e2e_flow_last_week(tmp_path: Path):
    """End-to-end: watcher ➜ research ➜ writer ➜ scorer ➜ pusher.

    The test iterates over *all* project cards with a completed DDQ in the last
    7 days that do *not* yet have a published **AI Deep Research Report** and
    performs the following steps sequentially for each card:

    1. Generate the AI Deep Research markdown report via *run_deep_research*.
    2. Publish / update the **AI Deep Research Report** page in Notion.
    3. Run the JSON *score_project* LLM function through *run_project_scoring*.
    4. Publish / update the 🔥 **Ratings** inline database and fill in the
       answers via *publish_ratings*.

    The helper intentionally skips cards that already contain a report to
    avoid accidental overwrites.  If no eligible cards are found within the
    last week the test is skipped.
    """

    # ------------------------------------------------------------------
    # 0. Environment-variable sanity – skip early when credentials missing
    # ------------------------------------------------------------------
    required = [
        ("NOTION_TOKEN", os.getenv("NOTION_TOKEN")),
        ("NOTION_DB_ID", os.getenv("NOTION_DB_ID")),
        ("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
    ]

    missing = [name for name, val in required if not val]
    if missing:
        pytest.skip("Missing env vars: " + ", ".join(missing))

    # ------------------------------------------------------------------
    # 1. Poll Notion for project cards completed during the last 7 days
    # ------------------------------------------------------------------
    since = datetime.now(timezone.utc) - timedelta(days=150)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    raw_pages = poll_notion_db(last_updated=cutoff, created_after=since)

    # Exclude cards that already contain a published AI report so as not to
    # overwrite existing analyst work.
    pages = [p for p in raw_pages if not _report_already_exists(p["page_id"])]

    if not pages:
        pytest.skip(
            "All completed DDQs already have an AI Deep Research Report – nothing to do."
        )

    print("\nEligible project cards (without existing report):")
    for idx, page in enumerate(pages, start=1):
        print(f"  [{idx}/{len(pages)}] {page.get('title', 'Untitled')} ({page['page_id']})")

    # ------------------------------------------------------------------
    # 2. Iterate over each eligible card and run the full pipeline
    # ------------------------------------------------------------------
    for idx, page in enumerate(pages, start=1):
        page_id = page["page_id"]

        print(
            f"[{idx}/{len(pages)}] Generating research, publishing report, scoring and pushing ratings for: "
            f"{page.get('title', 'Untitled')} ({page_id})"
        )

        # --------------------------------------------------------------
        # 2a. Deep-research markdown generation
        # --------------------------------------------------------------
        ddq_md_path = tmp_path / f"ddq_{idx}.md"
        report_path = run_deep_research(page_id, ddq_md_path)

        # --------------------------------------------------------------
        # 2b. Publish / update the AI Deep Research Report in Notion
        # --------------------------------------------------------------
        url = publish_report(page_id, report_path)
        assert url.startswith("https://"), "Writer should return a valid Notion URL"

        # --------------------------------------------------------------
        # 2c. Run the LLM scoring pipeline – ensures JSON is generated
        # --------------------------------------------------------------
        json_path = run_project_scoring(page_id)
        assert json_path.exists(), "Score JSON file was not created."
        assert json_path.stat().st_size > 1024, "Score JSON file appears unexpectedly small."

        # --------------------------------------------------------------
        # 2d. Push Ratings table & answers back to Notion
        # --------------------------------------------------------------
        db_id = publish_ratings(page_id)
        assert db_id and "-" in db_id, "publish_ratings should return a valid Notion database ID"

        print(f"      → Report published: {url}")
        print(f"      → Score JSON: {json_path}")
        print(f"      → Ratings DB ID: {db_id}\n")
