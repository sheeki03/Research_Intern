"""Integration test: scorer ➜ pusher – publish Ratings table & answers."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()


PAGE_ID = "1eb7cf9e-26b8-81a3-b3ff-ca70731a64dd"  # Blockmesh project card


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("NOTION_TOKEN") or not os.getenv("OPENAI_API_KEY"),
    reason="Real credentials required for Notion & OpenAI APIs.",
)
def test_publish_ratings_real_world(tmp_path: Path):
    """End-to-end helper should create Ratings DB (if missing) and fill answers."""

    from src.pusher import publish_ratings

    db_id = publish_ratings(PAGE_ID)

    # Basic sanity: database_id looks like a UUID (contains dashes)
    assert db_id and "-" in db_id, "publish_ratings should return a valid Notion database ID"
