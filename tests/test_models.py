"""Tests for the data models."""

import pytest
from datetime import datetime, timezone

from src.models.feed import (
    ActionType,
    Actor,
    Content,
    EventSource,
    FeedEvent,
    Financials,
    SlidingWindow,
    WhitelistConfig,
)


class TestActor:
    """Test Actor model."""

    def test_create_actor(self):
        """Test creating an Actor instance."""
        actor = Actor(
            nameEn="Nancy Pelosi",
            nameZh="南希·佩洛西",
            identityEn="Representative (CA)",
            identityZh="联邦众议员 (加利福尼亚州)",
        )
        assert actor.name_en == "Nancy Pelosi"
        assert actor.name_zh == "南希·佩洛西"
        assert actor.identity_en == "Representative (CA)"
        assert actor.identity_zh == "联邦众议员 (加利福尼亚州)"

    def test_actor_aliases(self):
        """Test Actor model with aliases."""
        data = {
            "nameEn": "Tim Cook",
            "nameZh": "蒂姆·库克",
            "identityEn": "CEO",
            "identityZh": "首席执行官",
        }
        actor = Actor(**data)
        assert actor.name_en == "Tim Cook"

    def test_actor_serialization(self):
        """Test Actor serialization."""
        actor = Actor(
            nameEn="Test",
            nameZh="测试",
            identityEn="CEO",
            identityZh="首席执行官",
        )
        data = actor.model_dump(by_alias=True)
        assert "nameEn" in data
        assert "nameZh" in data


class TestFinancials:
    """Test Financials model."""

    def test_create_buy_financials(self):
        """Test creating buy financials."""
        fin = Financials(
            action=ActionType.BUY,
            price=150.50,
            volume=1000,
            valueRange="$100,001 - $250,000",
        )
        assert fin.action == ActionType.BUY
        assert fin.price == 150.50
        assert fin.volume == 1000
        assert fin.value_range == "$100,001 - $250,000"

    def test_create_sell_financials(self):
        """Test creating sell financials."""
        fin = Financials(action=ActionType.SELL)
        assert fin.action == ActionType.SELL
        assert fin.price == 0.0
        assert fin.volume == 0.0

    def test_financials_defaults(self):
        """Test default values."""
        fin = Financials(action=ActionType.BUY)
        assert fin.price == 0.0
        assert fin.volume == 0.0
        assert fin.value_range == ""


class TestContent:
    """Test Content model."""

    def test_create_content(self):
        """Test creating Content instance."""
        content = Content(
            titleEn="Test Title",
            titleZh="测试标题",
            bodyEn="Test body",
            bodyZh="测试内容",
        )
        assert content.title_en == "Test Title"
        assert content.title_zh == "测试标题"
        assert content.body_en == "Test body"
        assert content.body_zh == "测试内容"


class TestFeedEvent:
    """Test FeedEvent model."""

    def test_create_congress_event(self):
        """Test creating a Congress trade event."""
        event = FeedEvent(
            eventId="abc123",
            source=EventSource.CONGRESS,
            ticker="NVDA",
            eventTimestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            actor=Actor(
                nameEn="Nancy Pelosi",
                nameZh="南希·佩洛西",
                identityEn="Representative",
                identityZh="联邦众议员",
            ),
            financials=Financials(
                action=ActionType.BUY,
                valueRange="$500,001 - $1,000,000",
            ),
            content=Content(
                titleEn="Pelosi buys NVDA calls",
                titleZh="佩洛西买入英伟达看涨期权",
                bodyEn="",
                bodyZh="AI投资洞察：看涨信号强劲",
            ),
            sourceUrl="https://example.com",
        )
        assert event.event_id == "abc123"
        assert event.source == EventSource.CONGRESS
        assert event.ticker == "NVDA"
        assert event.actor.name_zh == "南希·佩洛西"
        assert event.financials.action == ActionType.BUY

    def test_create_insider_event(self):
        """Test creating an insider trade event."""
        event = FeedEvent(
            eventId="def456",
            source=EventSource.INSIDER,
            ticker="AAPL",
            eventTimestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
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
                titleEn="Tim Cook sells AAPL shares",
                titleZh="蒂姆·库克卖出苹果股票",
                bodyEn="",
                bodyZh="高管减持",
            ),
            sourceUrl="https://example.com",
        )
        assert event.event_id == "def456"
        assert event.source == EventSource.INSIDER
        assert event.financials.price == 180.50

    def test_create_article_event(self):
        """Test creating an article event."""
        event = FeedEvent(
            eventId="ghi789",
            source=EventSource.ARTICLE,
            ticker="TSLA",
            eventTimestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            actor=Actor(
                nameEn="Reuters",
                nameZh="路透社",
                identityEn="Financial News",
                identityZh="金融新闻",
            ),
            content=Content(
                titleEn="Tesla beats expectations",
                titleZh="特斯拉业绩超预期",
                bodyEn="",
                bodyZh="特斯拉Q2业绩大幅超预期",
            ),
            sourceUrl="https://example.com",
        )
        assert event.event_id == "ghi789"
        assert event.source == EventSource.ARTICLE
        assert event.financials is None

    def test_event_serialization(self):
        """Test event serialization with aliases."""
        event = FeedEvent(
            eventId="test123",
            source=EventSource.CONGRESS,
            ticker="NVDA",
            eventTimestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            actor=Actor(
                nameEn="Test",
                nameZh="测试",
                identityEn="Test",
                identityZh="测试",
            ),
            content=Content(
                titleEn="Test",
                titleZh="测试",
                bodyEn="",
                bodyZh="",
            ),
            sourceUrl="https://example.com",
        )
        data = event.model_dump(by_alias=True)
        assert "eventId" in data
        assert "eventTimestamp" in data
        assert "sourceUrl" in data


class TestWhitelistConfig:
    """Test WhitelistConfig model."""

    def test_create_whitelist(self):
        """Test creating whitelist config."""
        config = WhitelistConfig(
            tickers=["AAPL", "NVDA", "TSLA"],
        )
        assert len(config.tickers) == 3
        assert "AAPL" in config.tickers

    def test_empty_whitelist(self):
        """Test empty whitelist."""
        config = WhitelistConfig()
        assert config.tickers == []
        assert config.last_updated is None


class TestSlidingWindow:
    """Test SlidingWindow model."""

    def test_create_window(self):
        """Test creating sliding window."""
        now = datetime.now(timezone.utc)
        window = SlidingWindow(
            events={"abc123": now, "def456": now},
        )
        assert len(window.events) == 2
        assert "abc123" in window.events

    def test_empty_window(self):
        """Test empty sliding window."""
        window = SlidingWindow()
        assert window.events == {}


class TestEventSource:
    """Test EventSource enum."""

    def test_congress_value(self):
        """Test CONGRESS value."""
        assert EventSource.CONGRESS == "CONGRESS"

    def test_insider_value(self):
        """Test INSIDER value."""
        assert EventSource.INSIDER == "INSIDER"

    def test_article_value(self):
        """Test ARTICLE value."""
        assert EventSource.ARTICLE == "ARTICLE"


class TestActionType:
    """Test ActionType enum."""

    def test_buy_value(self):
        """Test BUY value."""
        assert ActionType.BUY == "BUY"

    def test_sell_value(self):
        """Test SELL value."""
        assert ActionType.SELL == "SELL"
