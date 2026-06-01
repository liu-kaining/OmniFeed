"""Tests for the RSS generator."""

import pytest
from datetime import datetime, timezone

from src.models.feed import (
    ActionType,
    Actor,
    Content,
    EventSource,
    FeedEvent,
    Financials,
)
from src.services.rss_generator import (
    _format_rss_date,
    generate_congress_rss,
    generate_insider_rss,
)


@pytest.fixture
def sample_congress_events():
    """Sample Congress trade events."""
    return [
        FeedEvent(
            eventId="congress1",
            source=EventSource.CONGRESS,
            ticker="NVDA",
            eventTimestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            actor=Actor(
                nameEn="Nancy Pelosi",
                nameZh="南希·佩洛西",
                identityEn="Representative (CA)",
                identityZh="联邦众议员 (加利福尼亚州)",
            ),
            financials=Financials(
                action=ActionType.BUY,
                valueRange="$500,001 - $1,000,000",
            ),
            content=Content(
                titleEn="Pelosi buys NVDA calls",
                titleZh="佩洛西买入英伟达看涨期权",
                bodyEn="",
                bodyZh="看涨信号强劲",
            ),
            sourceUrl="https://efdsearch.senate.gov/example",
        ),
        FeedEvent(
            eventId="congress2",
            source=EventSource.CONGRESS,
            ticker="TSLA",
            eventTimestamp=datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc),
            actor=Actor(
                nameEn="Tommy Tuberville",
                nameZh="汤米·图伯维尔",
                identityEn="Senator (R-AL)",
                identityZh="联邦参议员 (阿拉巴马州)",
            ),
            financials=Financials(
                action=ActionType.BUY,
                valueRange="$250,001 - $500,000",
            ),
            content=Content(
                titleEn="Tuberville buys TSLA",
                titleZh="图伯维尔买入特斯拉",
                bodyEn="",
                bodyZh="信号敏感",
            ),
            sourceUrl="https://efdsearch.senate.gov/example2",
        ),
    ]


@pytest.fixture
def sample_insider_events():
    """Sample insider trade events."""
    return [
        FeedEvent(
            eventId="insider1",
            source=EventSource.INSIDER,
            ticker="AAPL",
            eventTimestamp=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            actor=Actor(
                nameEn="Tim Cook",
                nameZh="蒂姆·库克",
                identityEn="CEO",
                identityZh="首席执行官",
            ),
            financials=Financials(
                action=ActionType.SELL,
                price=180.50,
                volume=50000,
            ),
            content=Content(
                titleEn="Tim Cook sells AAPL",
                titleZh="蒂姆·库克卖出苹果股票",
                bodyEn="",
                bodyZh="高管减持",
            ),
            sourceUrl="https://sec.gov/example",
        ),
    ]


class TestFormatRssDate:
    """Test RSS date formatting."""

    def test_format_utc_datetime(self):
        """Test formatting UTC datetime."""
        dt = datetime(2026, 6, 1, 12, 30, 0, tzinfo=timezone.utc)
        result = _format_rss_date(dt)
        assert "Sun, 01 Jun 2026 12:30:00 GMT" == result

    def test_format_naive_datetime(self):
        """Test formatting naive datetime (assumed UTC)."""
        dt = datetime(2026, 6, 1, 12, 30, 0)
        result = _format_rss_date(dt)
        assert "GMT" in result


class TestGenerateCongressRss:
    """Test Congress RSS generation."""

    def test_generates_valid_xml(self, sample_congress_events):
        """Test that valid XML is generated."""
        rss = generate_congress_rss(sample_congress_events)
        assert '<?xml version="1.0"' in rss
        assert '<rss version="2.0"' in rss

    def test_contains_channel_info(self, sample_congress_events):
        """Test that channel information is included."""
        rss = generate_congress_rss(sample_congress_events)
        assert "<title>OmniFeed - 国会山政治异动追踪源</title>" in rss
        assert "<link>https://omnifeed.pages.dev</link>" in rss

    def test_contains_items(self, sample_congress_events):
        """Test that items are included."""
        rss = generate_congress_rss(sample_congress_events)
        assert "<item>" in rss
        assert "congress1" in rss
        assert "congress2" in rss

    def test_items_sorted_by_date(self, sample_congress_events):
        """Test that items are sorted by date (most recent first)."""
        rss = generate_congress_rss(sample_congress_events)
        # congress2 (June 2) should come before congress1 (June 1)
        pos2 = rss.index("congress2")
        pos1 = rss.index("congress1")
        assert pos2 < pos1

    def test_empty_events(self):
        """Test RSS generation with no events."""
        rss = generate_congress_rss([])
        assert '<?xml version="1.0"' in rss
        assert "<item>" not in rss

    def test_contains_build_date(self, sample_congress_events):
        """Test that build date is included."""
        build_time = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        rss = generate_congress_rss(sample_congress_events, build_time)
        assert "Mon, 03 Jun 2026 12:00:00 GMT" in rss


class TestGenerateInsiderRss:
    """Test insider RSS generation."""

    def test_generates_valid_xml(self, sample_insider_events):
        """Test that valid XML is generated."""
        rss = generate_insider_rss(sample_insider_events)
        assert '<?xml version="1.0"' in rss
        assert '<rss version="2.0"' in rss

    def test_contains_channel_info(self, sample_insider_events):
        """Test that channel information is included."""
        rss = generate_insider_rss(sample_insider_events)
        assert "<title>OmniFeed - 公司管理层内幕交易追踪源</title>" in rss

    def test_contains_items(self, sample_insider_events):
        """Test that items are included."""
        rss = generate_insider_rss(sample_insider_events)
        assert "<item>" in rss
        assert "insider1" in rss

    def test_empty_events(self):
        """Test RSS generation with no events."""
        rss = generate_insider_rss([])
        assert '<?xml version="1.0"' in rss
        assert "<item>" not in rss
