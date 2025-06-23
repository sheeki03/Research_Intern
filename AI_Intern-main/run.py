#!/usr/bin/env python3
"""Automated DDQ research pipeline.

This script runs the end-to-end DDQ scoring workflow:

1. Detect project cards with a *completed* Due Diligence Questionnaire (DDQ)
   in the last 7 days (created in the last 150 days).
2. Skip any card that already has an **AI Deep Research Report** attached.
3. For each eligible card run the full pipeline:

   a. Generate markdown report via ``run_deep_research``.
   b. Publish / update the **AI Deep Research Report** page in Notion.
   c. Generate project score JSON via ``run_project_scoring``.
   d. Publish / update the 🔥 **Ratings** inline database via ``publish_ratings``.

The script is designed for AWS EC2 cron execution every 3 days.
It uses environment variables from the root Research_Intern_latest directory.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Load configuration from root directory
from src.config import check_required_env

# Pipeline entry points -------------------------------------------------------
from src.watcher import poll_notion_db
from src.research import run_deep_research
from src.writer import publish_report, _report_already_exists  # type: ignore
from src.scorer import run_project_scoring
from src.pusher import publish_ratings


def _eligible_project_pages() -> list[dict[str, str]]:
    """Return project cards ready for processing (no existing report)."""

    # Last 150-day creation window, but completed DDQ in the last week.
    since_created = datetime.now(timezone.utc) - timedelta(days=150)
    completed_after = datetime.now(timezone.utc) - timedelta(days=7)

    raw_pages = poll_notion_db(last_updated=completed_after, created_after=since_created)
    return [p for p in raw_pages if not _report_already_exists(p["page_id"])]


def _run_pipeline(page: dict[str, str], idx: int, total: int, tmp_dir: Path) -> None:
    """Execute full research → writer → scorer → pusher chain for *page*."""

    page_id = page["page_id"]
    title = page.get("title", "Untitled")

    print(f"[{idx}/{total}] Processing: {title} ({page_id})")

    # Step 1 – Deep research markdown
    md_path = tmp_dir / f"ddq_{idx}.md"
    try:
        report_path = run_deep_research(page_id, md_path)
    except Exception as exc:  # noqa: BLE001 – surface but continue with next card
        print(f"      ✖ research generation failed: {exc}", file=sys.stderr)
        return

    # Step 2 – Publish / update Notion report
    try:
        notion_url = publish_report(page_id, report_path)
    except Exception as exc:  # noqa: BLE001
        print(f"      ✖ report publishing failed: {exc}", file=sys.stderr)
        return

    # Step 3 – Run scoring pipeline (JSON)
    try:
        json_path = run_project_scoring(page_id)
    except Exception as exc:  # noqa: BLE001
        print(f"      ✖ project scoring failed: {exc}", file=sys.stderr)
        return

    # Step 4 – Push Ratings inline DB
    try:
        ratings_db_id = publish_ratings(page_id)
    except Exception as exc:  # noqa: BLE001
        print(f"      ✖ pushing ratings failed: {exc}", file=sys.stderr)
        return

    print(f"      ✓ Report published: {notion_url}")
    print(f"      ✓ Score JSON: {json_path}")
    print(f"      ✓ Ratings DB ID: {ratings_db_id}\n")

    # ------------------------------------------------------------------
    # House-keeping – remove local artifacts so that no files linger beyond
    # the lifetime of this script.  They were written only to facilitate
    # intermediate steps (writer & pusher) and are no longer needed.
    # ------------------------------------------------------------------
    try:
        report_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 – best-effort cleanup
        pass


def main() -> None:  # noqa: D401 – imperative mood preferred
    """Run the DDQ research pipeline once."""

    # Check environment variables from root directory
    try:
        check_required_env()
        print("✓ Environment variables loaded from root directory")
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    pages = _eligible_project_pages()
    if not pages:
        print("No eligible project cards found – everything up-to-date.")
        return

    print("Eligible project cards (without existing report):")
    for idx, page in enumerate(pages, 1):
        print(f"  [{idx}/{len(pages)}] {page.get('title', 'Untitled')} ({page['page_id']})")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for idx, page in enumerate(pages, 1):
            _run_pipeline(page, idx, len(pages), tmp_dir)


if __name__ == "__main__":
    main()
