import os
import json
import pytest
from notion_client import Client
from dotenv import load_dotenv
from datetime import datetime, timedelta


@pytest.fixture(scope='session', autouse=True)
def setup_env():  # noqa: F811
    """Load environment variables from .env before any test runs."""
    load_dotenv()


@ pytest.fixture(scope='session')
def notion_client():
    """Instantiate a Notion client using NOTION_TOKEN from env."""
    token = os.getenv('NOTION_TOKEN')
    if not token:
        pytest.skip('NOTION_TOKEN not set in environment or .env')
    return Client(auth=token)


@ pytest.fixture(scope='session')
def database_id():
    """Retrieve NOTION_DB_ID from environment."""
    db = os.getenv('NOTION_DB_ID')
    if not db:
        pytest.skip('NOTION_DB_ID not set in environment or .env')
    return db


def _get_all_pages(client, database_id: str) -> list:
    """Paginate through a Notion database and return all page objects."""
    pages = []
    start_cursor = None
    while True:
        if start_cursor:
            resp = client.databases.query(database_id=database_id, page_size=100, start_cursor=start_cursor)
        else:
            resp = client.databases.query(database_id=database_id, page_size=100)
        pages.extend(resp.get('results', []))
        if not resp.get('has_more', False):
            break
        start_cursor = resp.get('next_cursor')
    return pages


def _get_blocks(client: Client, block_id: str) -> list:
    """Retrieve all child blocks for a given block/page by paginating."""
    blocks = []
    start_cursor = None
    while True:
        if start_cursor:
            resp = client.blocks.children.list(block_id=block_id, page_size=100, start_cursor=start_cursor)
        else:
            resp = client.blocks.children.list(block_id=block_id, page_size=100)
        blocks.extend(resp.get('results', []))
        if not resp.get('has_more', False):
            break
        start_cursor = resp.get('next_cursor')
    return blocks


def _get_recent_pages(client, database_id: str, days: int = 30) -> list:
    """Return pages whose created_time is within the past `days`. Uses Notion filter to minimise results."""
    on_or_after = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    pages = []
    start_cursor = None
    while True:
        query_kwargs = dict(database_id=database_id, page_size=100,
                            filter={
                                "timestamp": "created_time",
                                "created_time": {
                                    "on_or_after": on_or_after
                                }
                            })
        if start_cursor:
            query_kwargs["start_cursor"] = start_cursor
        resp = client.databases.query(**query_kwargs)
        pages.extend(resp.get("results", []))
        if not resp.get("has_more", False):
            break
        start_cursor = resp.get("next_cursor")
    return pages


def test_dump_recent_db_structure(notion_client, database_id):
    """Debug helper: print IDs, titles, properties & block types for pages created in last 30 days."""
    pages = _get_recent_pages(notion_client, database_id)
    assert pages, "No pages found in the database"
    for page in pages:
        # Extract page title (title property)
        title = ''
        for prop in page.get('properties', {}).values():
            if prop.get('type') == 'title':
                title = prop['title'][0]['plain_text'] if prop['title'] else ''
                break
        print(f"Page ID: {page['id']}\n  Title: {title}\n  Properties: {list(page.get('properties', {}).keys())}")
        # List top-level block types under this page
        blocks = _get_blocks(notion_client, page['id'])
        types = [b.get('type') for b in blocks]
        print(f"  Blocks: {types}\n")


def test_find_recent_completed_ddq(notion_client, database_id):
    """Identify CRM cards (created last 30 days) whose Due Diligence Questionnaire is marked completed (☑️)."""
    pages = _get_recent_pages(notion_client, database_id)
    completed_cards = []

    for page in pages:
        # Extract title
        title = ''
        for prop in page.get('properties', {}).values():
            if prop.get('type') == 'title':
                title = prop['title'][0]['plain_text'] if prop['title'] else ''
                break
        # Fetch top-level blocks to find the Questionnaire subpage link
        blocks = _get_blocks(notion_client, page['id'])
        ddq_block = None
        for b in blocks:
            if b.get('type') == 'child_page' and b['child_page']['title'].lower().startswith('due diligence'):
                ddq_block = b
                break
        if not ddq_block:
            continue
        ddq_page_id = ddq_block['id']
        # Fetch DD Questionnaire page content
        ddq_blocks = _get_blocks(notion_client, ddq_page_id)
        # Scan from bottom for a checked to_do or markdown '[x]'
        completed = False
        for b in reversed(ddq_blocks):
            # Native to_do block
            if b.get('type') == 'to_do':
                completed = bool(b['to_do'].get('checked', False))
                break
            # Fallback: paragraph or list item containing literal '[x]'
            for kind in ('paragraph', 'bulleted_list_item', 'numbered_list_item'):
                if b.get('type') == kind:
                    rich = b[kind].get('rich_text', [])
                    text = ''.join(t.get('plain_text', '') for t in rich)
                    low = text.lower()
                    if '[x]' in low:
                        completed = True
                        break
                    if '[ ]' in text:
                        completed = False
                        break
            if completed:
                break
        if completed:
            completed_cards.append(title)

    print(f"Completed cards (last 30 days): {completed_cards}")
    # Currently only used for inspection; ensure we return a list without failing on content variance
    assert isinstance(completed_cards, list) 