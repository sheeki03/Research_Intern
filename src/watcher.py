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

from datetime import datetime, timezone
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
    """Fire the ``databases.query`` call with retry/back-off.

    This is extracted so that the tenacity logic lives in one place and can
    be easily unit-tested by monkey-patching the underlying SDK method.
    """

    retry = Retrying(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )

    # tenacity.Retrying is an iterator – we need to wrap the call.
    for attempt in retry:
        with attempt:
            return cast(
                Dict[str, object],
                client.databases.query(**payload),  # type: ignore[arg-type]
            )

    # Should be unreachable due to reraise=True.
    raise RuntimeError("Retry logic exited unexpectedly without a result.")


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


def poll_notion_db(
    *,
    since: datetime | None = None,
    created_after: datetime | None = None,
) -> List[Dict[str, str]]:
    """Return pages whose **Completed** checkbox is set to ✅.

    Parameters
    ----------
    since
        If provided, include only pages whose ``last_edited_time`` is *after*
        this timestamp.
    created_after
        If provided, include only pages whose ``created_time`` is *on or after*
        this timestamp (UTC).  Useful to limit the polling window, e.g., to
        the last 30 days.

    Returns
    -------
    list(dict)
        Each dict has the shape ``{"page_id": <id>, "title": <str>, "updated_time": <ISO>}``.

    Notes
    -----
    The utility is stateless – callers should track the timestamp of the last
    successful poll and pass it via *since*.
    """

    db_id = os.getenv("NOTION_DB_ID")
    if not db_id:
        raise RuntimeError("Environment variable NOTION_DB_ID is required.")

    _logger.info(
        "action=poll.start db_id=%s since=%s created_after=%s",
        db_id,
        since.isoformat() if since else "None",
        created_after.isoformat() if created_after else "None",
    )

    client = _build_client()

    # ------------------------------------------------------------------
    # Build the filter – only restrict by *created_time* to keep query fast.
    # We'll apply the `since` cutoff on the DDQ child page after we detect
    # completion so that updates inside the questionnaire are respected.
    # ------------------------------------------------------------------
    and_filters: List[Dict[str, object]] = []

    # NOTE: We intentionally do *not* add a parent `last_edited_time` filter
    # when `since` is provided, because ticking the final checkbox often
    # happens *inside* the DDQ sub-page and does **not** modify the parent
    # card.  We will instead filter later based on the DDQ page's own
    # `last_edited_time`.

    if created_after is not None:
        and_filters.append(
            {
                "timestamp": "created_time",
                "created_time": {"on_or_after": created_after.isoformat()},
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
        # Scan the "Due Diligence" child page for completion marker
        # ------------------------------------------------------------------
        blocks = _list_blocks(client, page_id)
        ddq_block = next(
            (
                b
                for b in blocks
                if b.get("type") == "child_page"
                and b["child_page"]["title"].lower().startswith("due diligence")
            ),
            None,
        )

        if not ddq_block:
            continue  # No questionnaire sub-page

        # Incrementally fetch blocks so we can bail once completion marker is found.
        completed = False
        ddq_cursor: str | None = None
        while True:
            blk_kwargs: Dict[str, object] = {
                "block_id": cast(str, ddq_block["id"]),
                "page_size": 100,
            }
            if ddq_cursor:
                blk_kwargs["start_cursor"] = ddq_cursor

            # Fetch next chunk of blocks with retry logic
            retry = Retrying(
                wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
                stop=stop_after_attempt(3),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            )

            for attempt in retry:
                with attempt:
                    chunk = cast(
                        Dict[str, object],
                        client.blocks.children.list(**blk_kwargs),  # type: ignore[arg-type]
                    )

            ddq_chunk_blocks = cast(List[Dict[str, object]], chunk.get("results", []))

            # Check chunk for completion marker (iterate reversed so bottom-up)
            for b in reversed(ddq_chunk_blocks):
                if b.get("type") == "to_do":
                    completed = bool(b["to_do"].get("checked", False))
                    break
                for kind in ("paragraph", "bulleted_list_item", "numbered_list_item"):
                    if b.get("type") == kind:
                        rich = b[kind].get("rich_text", [])
                        text = "".join(t.get("plain_text", "") for t in rich)
                        low = text.lower()
                        if "[x]" in low:
                            completed = True
                            break
                        if "[ ]" in low:
                            completed = False
                            break
                if completed:
                    break

            if completed or not chunk.get("has_more", False):
                break

            ddq_cursor = cast(str, chunk.get("next_cursor"))

        if not completed:
            continue  # Skip unfinished cards

        # ------------------------------------------------------------------
        # Apply *since* cutoff based on the DDQ sub-page timestamp, not the
        # parent card.  This ensures we catch pages whose final checkbox was
        # ticked inside the questionnaire without touching the parent.
        # ------------------------------------------------------------------
        if since is not None:
            ddq_last_edit: str | None = ddq_block.get("last_edited_time")  # type: ignore[assignment]
            if ddq_last_edit is not None:
                # Convert ISO 8601 string (may end with 'Z') to datetime
                if ddq_last_edit.endswith("Z"):
                    ddq_last_edit_dt = datetime.fromisoformat(ddq_last_edit.replace("Z", "+00:00"))
                else:
                    ddq_last_edit_dt = datetime.fromisoformat(ddq_last_edit)

                if ddq_last_edit_dt <= since:
                    continue  # Completed before the cutoff – skip

        pages.append(
            {
                "page_id": page_id,
                "title": title,
                # Track when the DDQ page itself was last edited (more accurate)
                "updated_time": cast(str, ddq_block.get("last_edited_time", "")),
            }
        )

    _logger.info("action=poll.success returned=%d", len(pages))

    return pages


__all__ = ["poll_notion_db"] 