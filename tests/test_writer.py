import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.watcher import poll_notion_db
from src.research import run_deep_research
from src.writer import publish_report


@pytest.mark.integration
def test_publish_report_real_world(tmp_path: Path):
    """End-to-end: watcher ➜ research ➜ writer."""

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

    since = datetime.now(timezone.utc) - timedelta(days=15)
    pages = poll_notion_db(created_after=since)
    if not pages:
        pytest.skip("Watcher returned 0 completed DDQs in last 15 days.")

    page_id = pages[-1]["page_id"]

    # generate research report
    ddq_md_path = tmp_path / "ddq.md"
    report_path = run_deep_research(page_id, ddq_md_path)

    # publish to notion
    url = publish_report(page_id, report_path)

    assert url.startswith("https://"), "Writer should return a notion URL"
