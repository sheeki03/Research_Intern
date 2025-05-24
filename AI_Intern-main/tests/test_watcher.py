import os
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv

from src.watcher import poll_notion_db


@pytest.fixture(scope="session", autouse=True)
def _env_setup():
    """Load env vars so the integration test can access NOTION_TOKEN & DB."""
    load_dotenv()


def test_list_completed_projects():
    """Print titles & IDs of cards with completed DDQs in the last 7 days, for projects created in last 180 days."""
    token = os.getenv("NOTION_TOKEN")
    db = os.getenv("NOTION_DB_ID")
    if not token or not db:
        pytest.skip("NOTION_TOKEN / NOTION_DB_ID not configured – skipping live integration test")

    since = datetime.now(timezone.utc) - timedelta(days=180)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # ------------------------------------------------------------------
    # Run the helper under test – this returns ONLY the pages that satisfy
    # the completion & recency criteria.  We'll later compare the returned
    # IDs with the full result set to mark ✅ / ❌ for each card.
    # ------------------------------------------------------------------
    kept_pages = poll_notion_db(last_updated=cutoff, created_after=since)
    kept_ids = {p["page_id"] for p in kept_pages}

    # ------------------------------------------------------------------
    # Fetch *all* candidate cards so that we can render a full report that
    # shows which ones were skipped (❌) and which ones were kept (✅).
    # ------------------------------------------------------------------
    from src.watcher import (
        _build_client,  # pylint: disable=protected-access
        _query_database,  # pylint: disable=protected-access
        _list_blocks,  # pylint: disable=protected-access
        _ddq_is_completed,  # pylint: disable=protected-access
        _page_last_edited_time,  # pylint: disable=protected-access
    )

    client = _build_client()

    # Build the *created_after* filter exactly like poll_notion_db so that we
    # examine the SAME result window.
    and_filters = [
        {
            "timestamp": "created_time",
            "created_time": {"on_or_after": since.isoformat()},
        }
    ]

    payload = {"database_id": db, "page_size": 100, "filter": and_filters[0]}

    response = _query_database(client, payload)
    all_results = response.get("results", [])

    print("\n=== DDQ Audit (✅ = kept | ❌ = skipped) ===")

    for page in all_results:
        # -----------------------------
        # Pull basic metadata (title, id)
        # -----------------------------
        title = ""
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title" and prop["title"]:
                title = prop["title"][0]["plain_text"]
                break

        page_id = page["id"]

        # --------------------------------------------------------------
        # Evaluate DDQ completion status & last-edited timestamp – we re-use
        # the same helpers so the heuristics are identical to poll_notion_db.
        # --------------------------------------------------------------
        blocks = _list_blocks(client, page_id)
        ddq_candidates = [
            b
            for b in blocks
            if b.get("type") == "child_page"
            and "due diligence" in b["child_page"]["title"].lower()
        ]

        completed_found = False
        ddq_last_edit_dt = None

        for cand in ddq_candidates:
            cand_id = cand["id"]
            if not _ddq_is_completed(client, cand_id):
                continue

            completed_found = True

            cand_dt = _page_last_edited_time(client, cand_id)

            blk_ts_raw = cand.get("last_edited_time")
            if blk_ts_raw:
                blk_dt = (
                    datetime.fromisoformat(blk_ts_raw.replace("Z", "+00:00"))
                    if blk_ts_raw.endswith("Z")
                    else datetime.fromisoformat(blk_ts_raw)
                )
                if cand_dt is None or blk_dt > cand_dt:
                    cand_dt = blk_dt

            if cand_dt is not None and (
                ddq_last_edit_dt is None or cand_dt > ddq_last_edit_dt
            ):
                ddq_last_edit_dt = cand_dt

        # Determine whether this card was *kept* by the original helper
        is_kept = page_id in kept_ids

        status_emoji = "✅" if is_kept else "❌"

        ts_str = ddq_last_edit_dt.isoformat() if ddq_last_edit_dt else "N/A"

        print(f"{status_emoji}  {title}  |  {page_id}  |  DDQ last edit: {ts_str}")

    # ------------------------------------------------------------------
    # Sanity check remains – ensure the public helper still returns a list
    # structure as part of the regression test.
    # ------------------------------------------------------------------
    assert isinstance(kept_pages, list) 