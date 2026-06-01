"""MD5 fingerprint engine for event deduplication.

This module implements the deterministic hash fingerprinting algorithm
as specified in the OmniFeed specification for sliding window deduplication.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional


# Sliding window expiration: 90 days
WINDOW_EXPIRY_DAYS = 90


def compute_congress_event_id(
    stock_ticker: str,
    last_name: str,
    disclosure_date: str,
    amount: str,
    transaction_type: str,
) -> str:
    """Compute unique event ID for Congress trades.

    Formula: MD5(stockTicker + lastName + disclosureDate + amount + type)
    """
    raw = f"{stock_ticker}{last_name}{disclosure_date}{amount}{transaction_type}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def compute_insider_event_id(
    symbol: str,
    insider_name: str,
    filing_date: str,
    securities_transacted: str,
    transaction_type: str,
) -> str:
    """Compute unique event ID for insider transactions.

    Formula: MD5(symbol + insiderName + filingDate + securitiesTransacted + transactionType)
    """
    raw = f"{symbol}{insider_name}{filing_date}{securities_transacted}{transaction_type}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def compute_article_event_id(title: str, pub_date: str) -> str:
    """Compute unique event ID for news articles.

    Formula: MD5(title + pubDate)
    """
    raw = f"{title}{pub_date}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def is_expired(timestamp: datetime, reference_time: Optional[datetime] = None) -> bool:
    """Check if a timestamp is expired (older than 90 days)."""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    expiry_threshold = reference_time - timedelta(days=WINDOW_EXPIRY_DAYS)
    return timestamp < expiry_threshold


def prune_expired_entries(
    window: dict[str, datetime],
    reference_time: Optional[datetime] = None,
) -> dict[str, datetime]:
    """Remove expired entries from the sliding window.

    Returns a new dictionary with only non-expired entries.
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    return {
        event_id: ts
        for event_id, ts in window.items()
        if not is_expired(ts, reference_time)
    }


def filter_new_events(
    current_window: dict[str, datetime],
    new_event_ids: list[str],
    current_time: Optional[datetime] = None,
) -> list[str]:
    """Filter out already-seen event IDs, returning only new ones.

    Args:
        current_window: The existing sliding window of event IDs to timestamps.
        new_event_ids: List of newly computed event IDs to check.
        current_time: Current timestamp for new entries.

    Returns:
        List of event IDs that are not in the current window.
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)
    return [eid for eid in new_event_ids if eid not in current_window]
