import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.watcher import poll_notion_db
from src.research import run_deep_research


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("NOTION_TOKEN") or not os.getenv("NOTION_DB_ID") or not os.getenv("OPENAI_API_KEY"),
    reason="Real credentials are required to run integration test.",
)
def test_run_deep_research_real_world(tmp_path: Path):
    """End-to-end integration test exercising the research helper with live APIs.

    The test:
    1. Calls `poll_notion_db` restricted to pages updated in the last 15 days.
    2. Picks the most recently updated card.
    3. Executes `run_deep_research` and waits for completion.
    4. Asserts that the markdown report was written under `reports/` and is non-empty.
    5. Verifies that `logs/research.log` captured events.
    """

    # ------------------------------------------------------------------
    # 1. Retrieve candidate page IDs (real Notion API call)
    # ------------------------------------------------------------------
    since = datetime.now(timezone.utc) - timedelta(days=15)
    pages = poll_notion_db(created_after=since)

    if not pages:
        pytest.skip("No completed DDQ pages found in the last 15 days – skipping.")

    # Pick the last item (most recent in the list)
    target = pages[-1]
    page_id = target["page_id"]

    # ------------------------------------------------------------------
    # 2. Run deep research
    # ------------------------------------------------------------------
    ddq_md_path = tmp_path / "ddq.md"
    report_path = run_deep_research(page_id, ddq_md_path)

    # ------------------------------------------------------------------
    # 3. Assertions – output exists and is non-empty
    # ------------------------------------------------------------------
    assert report_path.exists(), "Report markdown file was not created."
    assert report_path.stat().st_size > 100, "Report file appears unexpectedly small."

    # ------------------------------------------------------------------
    # 4. Ensure logging captured events
    # ------------------------------------------------------------------
    log_path = Path("logs/research.log")
    assert log_path.exists(), "Log file was not created."
    assert log_path.stat().st_size > 0, "Log file is empty."
