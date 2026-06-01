"""Tests for the fingerprint module."""

import pytest
from datetime import datetime, timedelta, timezone

from src.utils.fingerprint import (
    compute_article_event_id,
    compute_congress_event_id,
    compute_insider_event_id,
    filter_new_events,
    is_expired,
    prune_expired_entries,
)


class TestComputeCongressEventId:
    """Test Congress event ID computation."""

    def test_basic_computation(self):
        """Test basic event ID computation."""
        eid = compute_congress_event_id(
            stock_ticker="NVDA",
            last_name="Pelosi",
            disclosure_date="2026-06-01",
            amount="$500,001 - $1,000,000",
            transaction_type="P",
        )
        assert isinstance(eid, str)
        assert len(eid) == 32  # MD5 hex digest length

    def test_deterministic(self):
        """Test that same inputs produce same output."""
        args = {
            "stock_ticker": "NVDA",
            "last_name": "Pelosi",
            "disclosure_date": "2026-06-01",
            "amount": "$500,001 - $1,000,000",
            "transaction_type": "P",
        }
        eid1 = compute_congress_event_id(**args)
        eid2 = compute_congress_event_id(**args)
        assert eid1 == eid2

    def test_different_inputs_different_output(self):
        """Test that different inputs produce different outputs."""
        base_args = {
            "stock_ticker": "NVDA",
            "last_name": "Pelosi",
            "disclosure_date": "2026-06-01",
            "amount": "$500,001 - $1,000,000",
            "transaction_type": "P",
        }
        eid1 = compute_congress_event_id(**base_args)

        modified_args = {**base_args, "last_name": "Tuberville"}
        eid2 = compute_congress_event_id(**modified_args)

        assert eid1 != eid2


class TestComputeInsiderEventId:
    """Test insider event ID computation."""

    def test_basic_computation(self):
        """Test basic event ID computation."""
        eid = compute_insider_event_id(
            symbol="AAPL",
            insider_name="Tim Cook",
            filing_date="2026-06-01",
            securities_transacted="10000",
            transaction_type="P",
        )
        assert isinstance(eid, str)
        assert len(eid) == 32

    def test_deterministic(self):
        """Test that same inputs produce same output."""
        args = {
            "symbol": "AAPL",
            "insider_name": "Tim Cook",
            "filing_date": "2026-06-01",
            "securities_transacted": "10000",
            "transaction_type": "P",
        }
        eid1 = compute_insider_event_id(**args)
        eid2 = compute_insider_event_id(**args)
        assert eid1 == eid2


class TestComputeArticleEventId:
    """Test article event ID computation."""

    def test_basic_computation(self):
        """Test basic event ID computation."""
        eid = compute_article_event_id(
            title="NVIDIA Surpasses Expectations",
            pub_date="2026-06-01T12:00:00Z",
        )
        assert isinstance(eid, str)
        assert len(eid) == 32

    def test_deterministic(self):
        """Test that same inputs produce same output."""
        args = {
            "title": "NVIDIA Surpasses Expectations",
            "pub_date": "2026-06-01T12:00:00Z",
        }
        eid1 = compute_article_event_id(**args)
        eid2 = compute_article_event_id(**args)
        assert eid1 == eid2


class TestIsExpired:
    """Test expiration checking."""

    def test_not_expired_recent(self):
        """Test that recent timestamp is not expired."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=30)
        assert not is_expired(recent, now)

    def test_expired_old(self):
        """Test that old timestamp is expired."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=100)
        assert is_expired(old, now)

    def test_boundary_90_days(self):
        """Test boundary at exactly 90 days."""
        now = datetime.now(timezone.utc)
        boundary = now - timedelta(days=90, seconds=1)
        assert is_expired(boundary, now)

    def test_naive_datetime(self):
        """Test that naive datetime is treated as UTC."""
        now = datetime.now(timezone.utc)
        naive = datetime.now() - timedelta(days=100)
        assert is_expired(naive, now)


class TestPruneExpiredEntries:
    """Test pruning of expired entries."""

    def test_prune_removes_expired(self):
        """Test that expired entries are removed."""
        now = datetime.now(timezone.utc)
        window = {
            "recent": now - timedelta(days=30),
            "expired": now - timedelta(days=100),
            "old": now - timedelta(days=91),
        }
        result = prune_expired_entries(window, now)
        assert "recent" in result
        assert "expired" not in result
        assert "old" not in result

    def test_prune_keeps_all_recent(self):
        """Test that all recent entries are kept."""
        now = datetime.now(timezone.utc)
        window = {
            "a": now - timedelta(days=1),
            "b": now - timedelta(days=30),
            "c": now - timedelta(days=89),
        }
        result = prune_expired_entries(window, now)
        assert len(result) == 3

    def test_empty_window(self):
        """Test pruning empty window."""
        result = prune_expired_entries({}, datetime.now(timezone.utc))
        assert result == {}


class TestFilterNewEvents:
    """Test filtering of new events."""

    def test_filter_returns_only_new(self):
        """Test that only new events are returned."""
        window = {
            "existing1": datetime.now(timezone.utc),
            "existing2": datetime.now(timezone.utc),
        }
        new_ids = ["existing1", "new1", "existing2", "new2"]
        result = filter_new_events(window, new_ids)
        assert result == ["new1", "new2"]

    def test_filter_all_new(self):
        """Test when all events are new."""
        window = {}
        new_ids = ["a", "b", "c"]
        result = filter_new_events(window, new_ids)
        assert result == ["a", "b", "c"]

    def test_filter_none_new(self):
        """Test when no events are new."""
        now = datetime.now(timezone.utc)
        window = {"a": now, "b": now}
        new_ids = ["a", "b"]
        result = filter_new_events(window, new_ids)
        assert result == []

    def test_filter_empty_input(self):
        """Test with empty inputs."""
        result = filter_new_events({}, [])
        assert result == []
