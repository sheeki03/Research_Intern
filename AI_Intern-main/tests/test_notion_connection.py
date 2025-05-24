import os
import json
import pytest
from notion_client import Client
from dotenv import load_dotenv


@pytest.fixture(scope="session", autouse=True)
def setup_env():
    """Load .env so NOTION_TOKEN and NOTION_DB_ID are available."""
    load_dotenv()


@pytest.fixture(scope="session")
def notion_client():
    token = os.getenv("NOTION_TOKEN")
    if not token:
        pytest.skip("NOTION_TOKEN missing in env/.env")
    return Client(auth=token)


@pytest.fixture(scope="session")
def database_id():
    db = os.getenv("NOTION_DB_ID")
    if not db:
        pytest.skip("NOTION_DB_ID missing in env/.env")
    return db


def test_basic_database_access(notion_client, database_id):
    """Minimal sanity-check: hit Notion API and dump raw JSON for inspection."""
    # Retrieve database metadata
    db_meta = notion_client.databases.retrieve(database_id=database_id)
    print("\n=== Database metadata ===\n", json.dumps(db_meta, indent=2))

    # Query FIRST page of the database (page_size 3 for brevity)
    query = notion_client.databases.query(database_id=database_id, page_size=3)
    print("\n=== Query results (first 3) ===\n", json.dumps(query, indent=2))

    # Simple assertion: database has a title and at least 1 result
    assert db_meta.get("title"), "Database title missing – unexpected structure"
    assert query.get("results"), "No pages returned – check DB permissions or contents" 