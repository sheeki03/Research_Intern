import pytest
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.watcher import poll_notion_db
from src.research import run_deep_research
from src.writer import publish_report

@pytest.mark.integration
def test_publish_reports_last_week(tmp_path: Path):
    """End-to-end: watcher ➜ research ➜ writer for all completed DDQs in the last week."""

    # --------------------------------------------------------------
    # 0. Check env vars early so we know exactly which are missing
    # --------------------------------------------------------------
    required = [
        ("NOTION_TOKEN", os.getenv("NOTION_TOKEN")),
        ("NOTION_DB_ID", os.getenv("NOTION_DB_ID")),
        ("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
    ]

    missing = [name for name, val in required if not val]
    if missing:
        pytest.skip("Missing env vars: " + ", ".join(missing))

    # --------------------------------------------------------------
    # 1. Poll Notion for pages completed within the last week
    # --------------------------------------------------------------
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    pages = poll_notion_db(since=cutoff)
    if not pages:
        pytest.skip("Watcher returned 0 completed DDQs updated in last 7 days.")

    # --------------------------------------------------------------
    # 2. Sequentially produce and publish reports for each page
    # --------------------------------------------------------------
    for idx, page in enumerate(pages, start=1):
        page_id = page["page_id"]

        print(f"[{idx}/{len(pages)}] Generating & publishing report for: {page.get('title', 'Untitled')} ({page_id})")
        
        # generate research report
        ddq_md_path = tmp_path / f"ddq_{idx}.md"
        report_path = run_deep_research(page_id, ddq_md_path)

        # publish to notion
        url = publish_report(page_id, report_path)

        print(f"      → Published: {url}")

        assert url.startswith("https://"), "Writer should return a notion URL"
