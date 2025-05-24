import os
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv

from src.watcher import poll_notion_db


@pytest.fixture(scope="session", autouse=True)
def _env_setup():
    """Load env vars so the integration test can access NOTION_TOKEN & DB."""
    load_dotenv()


def test_list_completed_projects_last_30_days():
    """Print titles & IDs of cards with completed DDQs created in last 30 days."""
    token = os.getenv("NOTION_TOKEN")
    db = os.getenv("NOTION_DB_ID")
    if not token or not db:
        pytest.skip("NOTION_TOKEN / NOTION_DB_ID not configured – skipping live integration test")

    since = datetime.now(timezone.utc) - timedelta(days=30)

    pages = poll_notion_db(created_after=since)

    print("\n=== Completed DDQs (last 30 days) ===")
    for p in pages:
        print(f"{p['title']}  |  {p['page_id']}")

    # Simple sanity check: function returned a list structure
    assert isinstance(pages, list) 