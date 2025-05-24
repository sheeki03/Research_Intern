from __future__ import annotations

"""Notion report writer – posts the AI Deep Research Report under a project card.

Public helper:
    publish_report(page_id: str, report_path: Path) -> str

Behaviour
---------
• If a child page named *AI Deep Research Report* already exists under the given
  Notion page it is overwritten (its existing blocks are replaced).
• Otherwise a new child page is created under the parent card.
• The Markdown report is naively converted to paragraph / heading / bullet
  blocks (good-enough for MVP).
• Returns the URL of the report page so the caller can store / display it.

Logging goes to ``logs/writer.log`` mirroring the style used by watcher.py.
"""

from pathlib import Path
import logging
import os
import pathlib
from typing import List, Dict, Any, cast, Iterable
import re

import httpx
from notion_client import Client as NotionClient
from notion_client.errors import RequestTimeoutError
from notion_client import APIResponseError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

__all__ = ["publish_report"]

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
_LOG_PATH = pathlib.Path("logs/writer.log")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger(__name__)
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    _handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter(
            fmt="timestamp=%(asctime)s level=%(levelname)s message=%(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    _logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Helpers – retry logic mirrors watcher.py
# ---------------------------------------------------------------------------

def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (RequestTimeoutError, httpx.TimeoutException)):
        return True
    if isinstance(exc, APIResponseError):
        if exc.code in {"internal_server_error", "service_unavailable", "rate_limited"}:
            return True
        status = cast(int, getattr(exc, "status", 0))
        return status == 429 or status // 100 == 5
    return False


def _tenacity() -> Retrying:
    return Retrying(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )


def _notion() -> NotionClient:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise RuntimeError("Environment variable NOTION_TOKEN is required.")
    timeout_cfg = httpx.Timeout(180.0, connect=10.0)
    return NotionClient(auth=token, client=httpx.Client(timeout=timeout_cfg))


# ---------------------------------------------------------------------------
# NEW: Markdown helpers – code & table
# ---------------------------------------------------------------------------

def _code_block(code: str, lang: str | None = "plain text") -> Dict[str, Any]:
    """Return a Notion *code* block."""
    return {
        "type": "code",
        "code": {
            "rich_text": [{"type": "text", "text": {"content": code}}],
            "language": lang or "plain text",
        },
    }


def _table_lines_to_blocks(lines: List[str]) -> List[Dict[str, Any]]:
    """Convert pipe-delimited Markdown lines to a Notion *table* block.

    Supports an optional header separator like ``|---|---|`` that will be
    detected automatically and converted to a column header in Notion.

    The Notion API expects the row blocks to be stored under the *table*
    object itself (``table.children``) – **not** as top-level ``children``
    of the block.  Keep that exact shape to avoid 400-validation errors.
    """
    if not lines:
        return []

    # Parse rows → list[list[str]] without outer pipes / surrounding whitespace
    rows: List[List[str]] = []
    for ln in lines:
        parts = [cell.strip() for cell in ln.strip().strip("|").split("|")]
        rows.append(parts)

    # Detect header separator row (e.g. |----|----|) – must be 2nd row and only
    # contain dashes / colons.
    has_header = False
    if len(rows) >= 2 and all(set(c) <= {"-", ":"} for c in rows[1]):
        has_header = True
        rows.pop(1)  # remove the separator row

    # Notion demands that every row has exactly table_width cells.
    # Compute the maximum width across rows, then pad shorter rows with
    # empty strings so all have equal length.
    table_width = max(len(r) for r in rows)

    for r in rows:
        if len(r) < table_width:
            r.extend([""] * (table_width - len(r)))

    table_children: List[Dict[str, Any]] = []
    for row in rows:
        cells = [
            _inline_md_to_rich_text(cell)
            for cell in row
        ]
        table_children.append({"type": "table_row", "table_row": {"cells": cells}})

    return [
        {
            "type": "table",
            "table": {
                "table_width": table_width,
                "has_column_header": has_header,
                "has_row_header": False,
                "children": table_children,
            },
        }
    ]


# ---------------------------------------------------------------------------
# Inline Markdown helpers (bold **text**)
# ---------------------------------------------------------------------------

_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _sanitize_text(text: str) -> str:
    """Remove control characters (except tab) that Notion rejects."""
    return "".join(ch for ch in text if (ord(ch) >= 32 or ch == "\t"))


def _inline_md_to_rich_text(text: str) -> List[Dict[str, Any]]:
    """Convert inline markdown (**bold**, [link](url)) to Notion rich_text list."""
    parts: List[Dict[str, Any]] = []
    pos = 0  # current scan position
    while pos < len(text):
        # Find the next bold or link occurrence after current position.
        bold_match = _BOLD_PATTERN.search(text, pos)
        link_match = _LINK_PATTERN.search(text, pos)

        # Determine which match comes first (lowest start index)
        next_match: re.Match[str] | None
        is_link = False
        if link_match and (not bold_match or link_match.start() < bold_match.start()):
            next_match = link_match
            is_link = True
        elif bold_match:
            next_match = bold_match
            is_link = False
        else:
            next_match = None

        # If no more patterns, break the loop
        if next_match is None:
            break

        # Add plain text that appears before the matched token
        if next_match.start() > pos:
            plain = text[pos : next_match.start()]
            if plain:
                parts.append({
                    "type": "text",
                    "text": {"content": _sanitize_text(plain)},
                })

        if is_link:
            link_text, link_url = next_match.group(1), next_match.group(2)
            parts.append(
                {
                    "type": "text",
                    "text": {
                        "content": _sanitize_text(link_text),
                        "link": {"url": link_url},
                    },
                }
            )
        else:
            bold_txt = next_match.group(1)
            parts.append(
                {
                    "type": "text",
                    "text": {"content": _sanitize_text(bold_txt)},
                    "annotations": {"bold": True},
                }
            )

        pos = next_match.end()

    # Append any remaining tail text
    if pos < len(text):
        tail = text[pos:]
        if tail:
            parts.append({
                "type": "text",
                "text": {"content": _sanitize_text(tail)},
            })

    # Ensure at least one segment exists to keep structure intact
    if not parts:
        parts.append({
            "type": "text",
            "text": {"content": _sanitize_text(text)},
        })

    return parts


# ---------------------------------------------------------------------------
# Markdown → Notion blocks (extended implementation)
# ---------------------------------------------------------------------------

def _md_to_blocks(md: str) -> List[Dict[str, Any]]:
    """Very small Markdown subset → Notion blocks.

    Supported elements:
    • Headings # / ## / ###
    • Bullets (-) and numbered lists (1. )
    • Pipe-tables (including optional header separator)
    • Fenced code blocks (```lang)
    • Plain paragraphs
    """

    blocks: List[Dict[str, Any]] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.lstrip()

        # ----------------------------------------------------------------
        # fenced code  ```lang
        # ----------------------------------------------------------------
        if stripped.startswith("```"):
            lang = stripped[3:].strip() or "plain text"
            code_buf: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                code_buf.append(lines[i])
                i += 1
            blocks.append(_code_block("\n".join(code_buf), lang))
            i += 1  # skip closing fence
            continue

        # ----------------------------------------------------------------
        # pipe table – gather consecutive lines that contain ≥2 pipes.
        # ----------------------------------------------------------------
        if "|" in ln and ln.count("|") >= 2:
            table_buf: List[str] = []
            while i < len(lines) and "|" in lines[i]:
                table_buf.append(lines[i])
                i += 1
            blocks.extend(_table_lines_to_blocks(table_buf))
            continue

        # ----------------------------------------------------------------
        # Headings / list items / paragraphs
        # ----------------------------------------------------------------
        if not stripped:
            i += 1
            continue  # skip blank line after table or code block

        if stripped.startswith("### "):
            blocks.append({
                "type": "heading_3",
                "heading_3": {"rich_text": _inline_md_to_rich_text(stripped[4:])},
            })
        elif stripped.startswith("## "):
            blocks.append({
                "type": "heading_2",
                "heading_2": {"rich_text": _inline_md_to_rich_text(stripped[3:])},
            })
        elif stripped.startswith("# "):
            blocks.append({
                "type": "heading_1",
                "heading_1": {"rich_text": _inline_md_to_rich_text(stripped[2:])},
            })
        elif stripped.startswith("- "):
            blocks.append({
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _inline_md_to_rich_text(stripped[2:])},
            })
        elif len(stripped) >= 3 and stripped[0].isdigit() and stripped[1:3] == ". ":
            content = stripped[3:]
            blocks.append({
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _inline_md_to_rich_text(content)},
            })
        else:
            blocks.append({
                "type": "paragraph",
                "paragraph": {"rich_text": _inline_md_to_rich_text(stripped)},
            })

        i += 1

    return blocks


# ---------------------------------------------------------------------------
# Utility – chunk iterable (max_size=100 for Notion API)
# ---------------------------------------------------------------------------

def _chunks(lst: List[Dict[str, Any]], size: int = 100):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ---------------------------------------------------------------------------
# Pre-processing helpers
# ---------------------------------------------------------------------------

def _strip_duplicate_sources(md: str) -> str:
    """Remove any later un-numbered "Sources" sections.

    Keeps the first heading whose text (after removing any numeric
    prefix like "14.") equals "Sources" (case-insensitive). Any later
    duplicate heading and its immediate bullet list (lines starting with
    "- ") are dropped.
    """
    lines = md.splitlines()
    out: List[str] = []
    sources_seen = False
    skip = False

    def is_sources_heading(s: str) -> bool:
        if not s.lstrip().startswith("#"):
            return False
        txt = s.lstrip("#").strip()
        # remove leading number and dot
        txt = re.sub(r"^\d+\.\s*", "", txt)
        return txt.lower() == "sources"

    for i, ln in enumerate(lines):
        if skip:
            stripped = ln.lstrip()
            if stripped.startswith("- ") or not stripped:  # still within list / blank
                continue
            if stripped.startswith("#"):
                skip = False  # reached next section
            else:
                continue  # any other content under duplicate heading (unlikely)
        # not skipping
        if is_sources_heading(ln):
            if sources_seen:
                skip = True  # start skipping duplicate list
                continue  # do not include duplicate heading
            sources_seen = True
        out.append(ln)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def publish_report(page_id: str, report_path: Path) -> str:
    """Create or update the *AI Deep Research Report* child page under *page_id*.

    Parameters
    ----------
    page_id : str
        The Notion parent page (Project card).
    report_path : Path
        Local Markdown file previously generated by `run_deep_research`.

    Returns
    -------
    str
        The URL of the created/updated report page.
    """

    _logger.info("action=writer.start page_id=%s", page_id)

    client = _notion()
    # ------------------------------------------------------------------
    # 1. Locate existing child page (if any)
    # ------------------------------------------------------------------
    report_page_id: str | None = None

    for attempt in _tenacity():
        with attempt:
            children = client.blocks.children.list(block_id=page_id, page_size=100)
    for blk in children.get("results", []):
        if blk.get("type") == "child_page" and blk["child_page"]["title"] == "AI Deep Research Report":
            report_page_id = blk["id"]
            break

    md = _strip_duplicate_sources(report_path.read_text(encoding="utf-8"))
    blocks = _md_to_blocks(md)

    if report_page_id is None:
        # ------------------------------------------------------------------
        # 2a. Create new child page
        # ------------------------------------------------------------------
        # First batch (≤100) on create payload, remainder appended later.
        first_batch = blocks[:100]
        for attempt in _tenacity():
            with attempt:
                new_page = client.pages.create(
                    parent={"type": "page_id", "page_id": page_id},
                    properties={
                        "title": {
                            "title": [
                                {"type": "text", "text": {"content": "AI Deep Research Report"}}
                            ]
                        }
                    },
                    icon={"emoji": "🤖"},
                    children=first_batch,
                )
        report_page_id = cast(str, new_page["id"])
        report_url = cast(str, new_page["url"])
        # Append remaining batches (if any)
        for batch in _chunks(blocks[100:]):
            for attempt in _tenacity():
                with attempt:
                    client.blocks.children.append(block_id=report_page_id, children=batch)
        _logger.info("action=writer.created page_id=%s", report_page_id)
    else:
        # ------------------------------------------------------------------
        # 2b. Overwrite existing page – remove old children then append new
        # ------------------------------------------------------------------
        for attempt in _tenacity():
            with attempt:
                client.pages.update(page_id=report_page_id, icon={"emoji": "🤖"})
        for attempt in _tenacity():
            with attempt:
                existing_children = client.blocks.children.list(block_id=report_page_id, page_size=100)
        # Delete in reverse order to respect list indices
        for blk in reversed(existing_children.get("results", [])):
            try:
                client.blocks.delete(block_id=blk["id"])
            except Exception:  # best-effort
                pass
        # Append fresh content respecting 100-block limit
        for batch in _chunks(blocks):
            for attempt in _tenacity():
                with attempt:
                    client.blocks.children.append(block_id=report_page_id, children=batch)
        report_url = f"https://www.notion.so/{report_page_id.replace('-', '')}"
        _logger.info("action=writer.updated page_id=%s", report_page_id)

    _logger.info("action=writer.success url=%s", report_url)
    return report_url 