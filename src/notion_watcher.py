from __future__ import annotations
# flake8: noqa: E501

"""Notion database watcher.

This module exposes a single public helper – ``poll_notion_db`` – that
queries the **New Deck Dump** database for pages whose **Completed** checkbox
is ticked (``True``).  The utility is intentionally minimal and stateless so
that the orchestrator in ``main.py`` can call it every few minutes without
requiring additional storage.

Key design points
-----------------
1.  **Retry logic.**  All calls to the Notion API are wrapped by a
    ``tenacity`` retry decorator providing exponential back-off with an
    upper bound of three attempts (0.5 s → 1 s → 2 s).  This guards the
    script against transient 5xx/429 responses.
2.  **Structured logging.**  A module-level logger writes JSON-ish key=value
    pairs to ``logs/watcher.log`` via a ``RotatingFileHandler``.  The log is
    lightweight (<1 MiB/rotation) and respects PEP 8 guidelines.
3.  **Type safety.**  The code is fully type-annotated and passes
    ``mypy --strict``; no ``Any`` leaks into the public surface.

The implementation purposefully avoids catching *all* exceptions – only
errors that are expected to be transient are retried.  Anything else will be
raised to the caller so that the orchestrator can decide whether to abort or
escalate.
"""

from datetime import datetime, timezone, timedelta
import logging
import os
import pathlib
from logging.handlers import RotatingFileHandler
from typing import Dict, List, cast

from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from notion_client import APIResponseError, Client
from notion_client.errors import RequestTimeoutError, HTTPResponseError
import httpx
from httpx import HTTPStatusError

# ---------------------------------------------------------------------------
# Logging setup – rotate at ~1 MiB with three historical backups
# ---------------------------------------------------------------------------
_LOG_PATH = pathlib.Path("logs/watcher.log")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger(__name__)
if not _logger.handlers:  # Prevent duplicate handlers with pytest reloads
    _logger.setLevel(logging.INFO)

    _handler = RotatingFileHandler(
        _LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    _handler.setFormatter(
        logging.Formatter(
            fmt=(
                "timestamp=%(asctime)s "
                "level=%(levelname)s "
                "message=%(message)s"
            ),
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    _logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def _build_client() -> Client:
    """Instantiate a Notion SDK client from *NOTION_TOKEN*.

    Raises
    ------
    RuntimeError
        If the environment variable is missing.
    """

    token = os.getenv("NOTION_TOKEN")
    if token is None:
        raise RuntimeError("Environment variable NOTION_TOKEN is required.")

    timeout_cfg = httpx.Timeout(180.0, connect=10.0)
    http_client = httpx.Client(timeout=timeout_cfg)
    # Explicitly pass our preconfigured HTTPX client to the Notion SDK.
    return Client(auth=token, client=http_client)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_retryable(exc: Exception) -> bool:  # pragma: no cover – trivial predicate
    """Return *True* if the exception warrants a retry (429 or 5xx).

    The Notion SDK wraps HTTP errors in ``APIResponseError`` with ``code``
    strings such as ``internal_server_error`` (5xx) or ``rate_limited`` (429).
    We treat those two buckets as transient.
    """

    if isinstance(exc, (RequestTimeoutError, httpx.TimeoutException)):
        return True

    # Notion SDK high-level error objects ---------------------------------
    if isinstance(exc, APIResponseError):
        retryable_codes = {"internal_server_error", "service_unavailable", "rate_limited"}

        if exc.code in retryable_codes:
            return True

        status: int | None = getattr(exc, "status", None)
        if status is not None and (status == 429 or status // 100 == 5):
            return True

    # When the SDK cannot parse JSON body it raises HTTPResponseError
    if isinstance(exc, HTTPResponseError):
        status = getattr(exc.response, "status_code", 0)
        return status == 429 or status // 100 == 5

    # Fall back to raw HTTPStatusError from httpx if surfaced directly
    if isinstance(exc, HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status // 100 == 5

    return False


def _query_database(client: Client, payload: Dict[str, object]) -> Dict[str, object]:
    """Query a Notion database and *return **all** matching pages*.

    The Notion API returns results in pages of at most 100 items.  The
    original implementation surfaced only the first page which meant callers
    could silently miss older cards once the project list grew beyond 100.

    We now follow the ``next_cursor`` pointer until ``has_more`` is ``False``
    so that the caller always receives a complete view.  The helper still
    preserves the original response structure (dict with a ``results`` key)
    but aggregates the items across all pages.  ``has_more`` is forced to
    ``False`` to make it explicit that pagination has been resolved.
    """

    all_results: List[Dict[str, object]] = []
    next_cursor: str | None = None
    first_resp: Dict[str, object] | None = None

    while True:
        call_kwargs = payload.copy()
        if next_cursor is not None:
            call_kwargs["start_cursor"] = next_cursor

        # --------------------------------------------------------------
        # Fire the API request with Tenacity retry/back-off
        # --------------------------------------------------------------
        retry = Retrying(
            wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
            stop=stop_after_attempt(3),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )

        resp: Dict[str, object] | None = None
        for attempt in retry:
            with attempt:
                resp = cast(
                    Dict[str, object],
                    client.databases.query(**call_kwargs),  # type: ignore[arg-type]
                )

        if resp is None:  # pragma: no cover – defensive guard
            raise RuntimeError("Notion API call unexpectedly returned None.")

        # Save the first page so we can reuse its metadata when we return
        if first_resp is None:
            first_resp = resp

        all_results.extend(cast(List[Dict[str, object]], resp.get("results", [])))

        if not resp.get("has_more", False):
            break

        next_cursor = cast(str, resp.get("next_cursor"))
        if next_cursor is None:  # Safety net – should not happen per API docs
            break

    # ------------------------------------------------------------------
    # Build the aggregated response – replicate the first page's structure
    # but replace results / pagination flags so callers remain compatible.
    # ------------------------------------------------------------------
    aggregated: Dict[str, object] = first_resp.copy() if first_resp else {}
    aggregated["results"] = all_results
    aggregated["has_more"] = False
    aggregated["next_cursor"] = None

    return aggregated


def _list_blocks(client: Client, block_id: str) -> List[Dict[str, object]]:
    """Return *all* child blocks under a given block (handles pagination)."""

    blocks: List[Dict[str, object]] = []
    cursor: str | None = None

    while True:
        call_kwargs: Dict[str, object] = {
            "block_id": block_id,
            "page_size": 100,
        }
        if cursor:
            call_kwargs["start_cursor"] = cursor

        # Re-use Tenacity retry via `_is_retryable` predicate
        retry = Retrying(
            wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
            stop=stop_after_attempt(3),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )

        for attempt in retry:
            with attempt:
                resp = cast(
                    Dict[str, object],
                    client.blocks.children.list(**call_kwargs),  # type: ignore[arg-type]
                )

        blocks.extend(cast(List[Dict[str, object]], resp.get("results", [])))

        if not resp.get("has_more", False):
            break

        cursor = cast(str, resp.get("next_cursor"))

    return blocks


def _ddq_is_completed(client: Client, ddq_block_id: str) -> bool:
    """Return True if the DDQ child-page contains a completion mark (✅).

    The heuristic mirrors *research.py* so that both modules stay aligned:

    1. Walk blocks bottom-up and look for a *to-do* block – if it's checked
       the questionnaire is considered finished.
    2. Fallback: inspect paragraph/bullet/numbered-list blocks for literal
       "[x]" or "[ ]" markers that are sometimes used as markdown-style
       checkboxes inside Notion.
    """

    blocks = _list_blocks(client, ddq_block_id)

    for blk in reversed(blocks):
        b_type: str = blk.get("type", "")

        if b_type == "to_do":
            return bool(blk["to_do"].get("checked", False))

        # Fallback – look for markdown-style checkboxes inside rich text
        for kind in ("paragraph", "bulleted_list_item", "numbered_list_item"):
            if b_type == kind:
                rich = blk[kind].get("rich_text", [])
                text = "".join(part.get("plain_text", "") for part in rich).lower()
                if "[x]" in text:
                    return True
                if "[ ]" in text:
                    return False

    return False


def _page_last_edited_time(client: Client, page_id: str) -> datetime | None:
    """Return ``last_edited_time`` for a Notion *page* (UTC-aware).

    We need to call `pages.retrieve` because the *child_page* block under the
    parent card **does not update** its own `last_edited_time` when content
    *inside* the page changes (which is what usually happens when the ✅ box
    is ticked).  Relying on the block-level timestamp therefore causes us to
    miss recently-edited questionnaires.
    """

    retry = Retrying(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )

    resp: Dict[str, object] | None = None
    for attempt in retry:
        with attempt:
            resp = cast(Dict[str, object], client.pages.retrieve(page_id=page_id))  # type: ignore[arg-type]

    if resp is None:
        return None

    ts: str | None = cast(str | None, resp.get("last_edited_time"))
    if ts is None:
        return None

    if ts.endswith("Z"):
        page_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    else:
        page_dt = datetime.fromisoformat(ts)

    # ------------------------------------------------------------------
    # Fallback v2 – inspect *top-level* child blocks
    # ------------------------------------------------------------------
    # Some workspaces never update the page-level metadata even when
    # blocks inside the page change.  As a secondary heuristic we scan the
    # timestamps of the immediate child blocks and take the most recent
    # one.  We purposefully avoid a deep recursive crawl to keep the number
    # of API requests bounded – in the vast majority of questionnaires the
    # final ✅ checkbox that matters lives at the first level anyway.
    # ------------------------------------------------------------------
    try:
        blocks = _list_blocks(client, page_id)
    except Exception as exc:  # pragma: no cover – defensive guard
        _logger.warning("action=page.ts_blocks.error page_id=%s err=%s", page_id, exc)
        return page_dt  # Fall back to the original page timestamp

    latest_block_dt: datetime | None = None
    for blk in blocks:
        blk_ts_raw: str | None = blk.get("last_edited_time")  # noqa: E501 – long attr name
        if blk_ts_raw is None:
            continue

        blk_dt: datetime
        if blk_ts_raw.endswith("Z"):
            blk_dt = datetime.fromisoformat(blk_ts_raw.replace("Z", "+00:00"))
        else:
            blk_dt = datetime.fromisoformat(blk_ts_raw)

        if latest_block_dt is None or blk_dt > latest_block_dt:
            latest_block_dt = blk_dt

    # Return whichever timestamp is newer – the page itself or its blocks.
    if latest_block_dt and latest_block_dt > page_dt:
        return latest_block_dt

    return page_dt


def poll_notion_db(
    *,
    last_updated: datetime | None = None,
    created_after: datetime | int | float | timedelta | None = None,
    ready_for_rating_only: bool = False,
) -> List[Dict[str, str]]:
    """Return pages whose **Completed** checkbox is set to ✅.

    Parameters
    ----------
    last_updated
        If provided, include only pages whose ``last_edited_time`` is *after*
        this timestamp.
    created_after
        If provided, include only pages whose ``created_time`` is *on or after*
        this timestamp (UTC).  Useful to limit the polling window, e.g., to
        the last 30 days.
    ready_for_rating_only
        If True, only return pages that are in the "Ready for Rating" column/status.

    Returns
    -------
    list(dict)
        Each dict has the shape ``{"page_id": <id>, "title": <str>, "updated_time": <ISO>}``.

    Notes
    -----
    The utility is stateless – callers should track the timestamp of the last
    successful poll and pass it via *last_updated*.
    """

    db_id = os.getenv("NOTION_DB_ID")
    if not db_id:
        raise RuntimeError("Environment variable NOTION_DB_ID is required.")

    # ------------------------------------------------------------------
    # Normalise *created_after* ------------------------------------------------
    # ------------------------------------------------------------------
    ca_dt: datetime | None
    if created_after is None:
        ca_dt = None
    elif isinstance(created_after, datetime):
        ca_dt = created_after
    elif isinstance(created_after, (int, float)):
        # Treat the numeric value as a day-delta so that ``created_after=120``
        # translates to "within the last 120 days" – this aligns with the
        # intuitive expectation for larger integers and keeps the behaviour
        # consistent across both absolute and relative forms.
        ca_dt = datetime.now(timezone.utc) - timedelta(days=float(created_after))
    elif isinstance(created_after, timedelta):
        ca_dt = datetime.now(timezone.utc) - created_after
    else:  # pragma: no cover – defensive guard for unexpected types
        raise TypeError(
            "'created_after' must be datetime, int, float, timedelta or None. "
            f"Got {type(created_after).__name__} instead."
        )

    _logger.info(
        "action=poll.start db_id=%s last_updated=%s created_after=%s",
        db_id,
        last_updated.isoformat() if last_updated else "None",
        ca_dt.isoformat() if ca_dt else "None",
    )

    client = _build_client()

    # ------------------------------------------------------------------
    # Build the filter – only restrict by *created_time* to keep query fast.
    # We'll apply the `last_updated` cutoff on the DDQ child page after we detect
    # completion so that updates inside the questionnaire are respected.
    # ------------------------------------------------------------------
    and_filters: List[Dict[str, object]] = []

    # NOTE: We intentionally do *not* add a parent `last_edited_time` filter
    # when `last_updated` is provided, because ticking the final checkbox often
    # happens *inside* the DDQ sub-page and does **not** modify the parent
    # card.  We will instead filter later based on the DDQ page's own
    # `last_edited_time`.

    if ca_dt is not None:
        and_filters.append(
            {
                "timestamp": "created_time",
                "created_time": {"on_or_after": ca_dt.isoformat()},
            }
        )

    filter_expr: Dict[str, object] | None = None
    if and_filters:
        filter_expr = and_filters[0] if len(and_filters) == 1 else {"and": and_filters}

    payload: Dict[str, object] = {
        "database_id": db_id,
        "page_size": 100,
    }
    if filter_expr is not None:
        payload["filter"] = filter_expr

    response: Dict[str, object] = _query_database(client, payload)
    results = cast(List[Dict[str, object]], response.get("results", []))

    pages: List[Dict[str, str]] = []

    for page in results:
        # Extract readable title
        title: str = ""
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                if prop["title"]:
                    title = prop["title"][0]["plain_text"]
                break

        page_id: str = cast(str, page["id"])

        # ------------------------------------------------------------------
        # Check "Ready for Rating" column filter if requested
        # ------------------------------------------------------------------
        if ready_for_rating_only:
            # Look for Status/Stage column that contains "Ready for Rating"
            ready_for_rating = False
            properties = page.get("properties", {})
            
            # Check common column names for status/stage
            for prop_name, prop_value in properties.items():
                if prop_name.lower() in ["status", "stage", "pipeline", "state"]:
                    if prop_value.get("type") == "select" and prop_value.get("select"):
                        select_name = prop_value["select"].get("name", "")
                        if "ready for rating" in select_name.lower():
                            ready_for_rating = True
                            break
                    elif prop_value.get("type") == "multi_select":
                        multi_select = prop_value.get("multi_select", [])
                        for item in multi_select:
                            if "ready for rating" in item.get("name", "").lower():
                                ready_for_rating = True
                                break
                        if ready_for_rating:
                            break
            
            if not ready_for_rating:
                continue  # Skip pages not in "Ready for Rating"

        # ------------------------------------------------------------------
        # Scan all "Due Diligence" child pages for a *completed* questionnaire
        # ------------------------------------------------------------------
        blocks = _list_blocks(client, page_id)
        ddq_candidates = [
            b
            for b in blocks
            if b.get("type") == "child_page"
            and "due diligence" in b["child_page"]["title"].lower()
        ]

        if not ddq_candidates:
            continue  # No questionnaire sub-page at all

        # --------------------------------------------------------------
        # Evaluate *all* DDQ pages that are marked complete and remember
        # the most recently edited one.  This covers the scenario where
        # multiple questionnaires exist and only some are up-to-date.
        # --------------------------------------------------------------

        ddq_last_edit_dt: datetime | None = None
        completed_found = False

        for cand in ddq_candidates:
            cand_id = cast(str, cand["id"])

            # Skip if the questionnaire is not completed
            if not _ddq_is_completed(client, cand_id):
                continue

            completed_found = True

            # -----------------------------
            # Pull the accurate page-level ts
            # -----------------------------
            cand_dt = _page_last_edited_time(client, cand_id)

            # Fallback: compare with the block's own timestamp (sometimes newer)
            blk_ts_raw: str | None = cast(str | None, cand.get("last_edited_time"))
            if blk_ts_raw:
                blk_dt = datetime.fromisoformat(blk_ts_raw.replace("Z", "+00:00")) if blk_ts_raw.endswith("Z") else datetime.fromisoformat(blk_ts_raw)
                if cand_dt is None or blk_dt > cand_dt:
                    cand_dt = blk_dt

            # Keep the most recent among all completed DDQs
            if cand_dt is not None and (ddq_last_edit_dt is None or cand_dt > ddq_last_edit_dt):
                ddq_last_edit_dt = cand_dt

        if not completed_found:
            continue  # None of the questionnaires are finished – skip this card

        # ------------------------------------------------------------------
        # Apply *last_updated* cutoff using the DDQ page timestamp (if available)
        # ------------------------------------------------------------------
        if last_updated is not None and ddq_last_edit_dt is not None:
            if ddq_last_edit_dt <= last_updated:
                continue  # Completed before the cutoff – skip

        pages.append(
            {
                "page_id": page_id,
                "title": title,
                # Track when the DDQ page itself was last edited (more accurate)
                "updated_time": ddq_last_edit_dt.isoformat() if ddq_last_edit_dt else "",
            }
        )

    _logger.info("action=poll.success returned=%d", len(pages))

    # ------------------------------------------------------------------
    # Emit a follow-up line with the readable titles/IDs of the projects
    # we detected so that operators can quickly confirm which cards were
    # processed without having to cross-reference elsewhere.
    # ------------------------------------------------------------------
    if pages:
        joined = ", ".join(f"{p['title']} ({p['page_id']})" for p in pages)
        # Keep the key=value structure so that downstream log parsers retain
        # compatibility while still exposing human-readable information.
        _logger.info("action=poll.pages list=%s", joined)

    return pages


__all__ = ["poll_notion_db"] 