"""Main ETL pipeline orchestrator.

This module implements the core ETL pipeline that:
1. Fetches data from FMP API
2. Performs MD5 fingerprint deduplication
3. Processes through LLM gateway
4. Stores results in R2
5. Generates RSS feeds
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.models.feed import (
    ActionType,
    Actor,
    Content,
    EventSource,
    FeedEvent,
    Financials,
)
from src.services.fmp_client import FMPClient
from src.services.llm_gateway import LLMGateway
from src.services.r2_client import R2Client
from src.services.rss_generator import generate_congress_rss, generate_insider_rss
from src.utils.config import AppConfig, load_config
from src.utils.fingerprint import (
    compute_article_event_id,
    compute_congress_event_id,
    compute_insider_event_id,
    filter_new_events,
    prune_expired_entries,
)

logger = logging.getLogger(__name__)


class ETLPipeline:
    """Main ETL pipeline orchestrator."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or load_config()
        self._fmp = FMPClient(self._config.fmp)
        self._llm = LLMGateway(self._config.llm)
        self._r2 = R2Client(self._config.r2)

    async def run(self) -> dict[str, Any]:
        """Execute the full ETL pipeline.

        Returns:
            Summary of the pipeline execution.
        """
        logger.info("Starting ETL pipeline execution")
        start_time = datetime.now(timezone.utc)

        # Load current state from R2
        whitelist = self._r2.load_whitelist()
        window_data = self._r2.load_sliding_window()
        window: dict[str, datetime] = {
            eid: datetime.fromisoformat(ts) if isinstance(ts, str) else ts
            for eid, ts in window_data.items()
        }

        # Prune expired entries
        window = prune_expired_entries(window)

        # Initialize summary
        summary = {
            "start_time": start_time.isoformat(),
            "tickers_processed": len(whitelist),
            "new_congress_events": 0,
            "new_insider_events": 0,
            "new_article_events": 0,
            "errors": [],
        }

        try:
            # Process each data source
            congress_events = await self._process_congress_data(whitelist, window)
            insider_events = await self._process_insider_data(whitelist, window)
            article_events = await self._process_article_data(whitelist, window)

            summary["new_congress_events"] = len(congress_events)
            summary["new_insider_events"] = len(insider_events)
            summary["new_article_events"] = len(article_events)

            # Combine all events
            all_events = congress_events + insider_events + article_events

            if all_events:
                # Sort by timestamp (most recent first)
                all_events.sort(key=lambda e: e.event_timestamp, reverse=True)

                # Store feeds
                self._store_feeds(all_events, congress_events, insider_events)

                # Update sliding window
                self._update_sliding_window(window, all_events)

            # Save updated sliding window
            self._r2.save_sliding_window(window)

            end_time = datetime.now(timezone.utc)
            summary["end_time"] = end_time.isoformat()
            summary["duration_seconds"] = (end_time - start_time).total_seconds()
            summary["total_new_events"] = len(all_events)

            logger.info(f"ETL pipeline completed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"ETL pipeline failed: {e}")
            summary["errors"].append(str(e))
            raise
        finally:
            await self._fmp.close()
            await self._llm.close()

    async def _process_congress_data(
        self,
        tickers: list[str],
        window: dict[str, datetime],
    ) -> list[FeedEvent]:
        """Process Congress trading data."""
        logger.info("Processing Congress trading data")

        # FMP doesn't have a direct Congress API, so we simulate with placeholder
        # In production, this would connect to Senate/House disclosure APIs
        raw_trades = await self._fetch_congress_trades(tickers)

        if not raw_trades:
            return []

        # Compute event IDs and filter new events
        event_ids = []
        for trade in raw_trades:
            eid = compute_congress_event_id(
                stock_ticker=trade.get("ticker", ""),
                last_name=trade.get("lastName", ""),
                disclosure_date=trade.get("disclosureDate", ""),
                amount=trade.get("amount", ""),
                transaction_type=trade.get("type", ""),
            )
            event_ids.append(eid)

        new_ids = filter_new_events(window, event_ids)

        # Filter to only new trades
        new_trades = [
            t for t, eid in zip(raw_trades, event_ids) if eid in new_ids
        ]

        if not new_trades:
            return []

        # Process through LLM
        processed = await self._llm.process_congress_trades(new_trades)

        # Convert to FeedEvents
        events = []
        for trade, llm_result in zip(new_trades, processed):
            event = self._build_congress_event(trade, llm_result)
            if event:
                events.append(event)

        return events

    async def _process_insider_data(
        self,
        tickers: list[str],
        window: dict[str, datetime],
    ) -> list[FeedEvent]:
        """Process insider trading data."""
        logger.info("Processing insider trading data")

        # Fetch insider trades from FMP
        raw_trades = await self._fmp.get_batch_insider_trading(tickers, days_back=7)

        all_new_trades: list[dict[str, Any]] = []
        for symbol, trades in raw_trades.items():
            for trade in trades:
                eid = compute_insider_event_id(
                    symbol=symbol,
                    insider_name=trade.get("insiderName", ""),
                    filing_date=trade.get("filingDate", ""),
                    securities_transacted=str(trade.get("securitiesTransacted", "")),
                    transaction_type=trade.get("transactionType", ""),
                )
                if eid not in window:
                    trade["_eventId"] = eid
                    trade["_symbol"] = symbol
                    all_new_trades.append(trade)

        if not all_new_trades:
            return []

        # Process through LLM
        processed = await self._llm.process_insider_trades(all_new_trades)

        # Convert to FeedEvents
        events = []
        for trade, llm_result in zip(all_new_trades, processed):
            event = self._build_insider_event(trade, llm_result)
            if event:
                events.append(event)

        return events

    async def _process_article_data(
        self,
        tickers: list[str],
        window: dict[str, datetime],
    ) -> list[FeedEvent]:
        """Process news article data."""
        logger.info("Processing news article data")

        # Fetch articles from FMP
        raw_articles = await self._fmp.get_batch_stock_news(tickers, days_back=7)

        all_new_articles: list[dict[str, Any]] = []
        for symbol, articles in raw_articles.items():
            for article in articles:
                eid = compute_article_event_id(
                    title=article.get("title", ""),
                    pub_date=article.get("publishedDate", ""),
                )
                if eid not in window:
                    article["_eventId"] = eid
                    article["_symbol"] = symbol
                    all_new_articles.append(article)

        if not all_new_articles:
            return []

        # Process through LLM
        processed = await self._llm.process_articles(all_new_articles)

        # Convert to FeedEvents
        events = []
        for article, llm_result in zip(all_new_articles, processed):
            event = self._build_article_event(article, llm_result)
            if event:
                events.append(event)

        return events

    async def _fetch_congress_trades(
        self, tickers: list[str]
    ) -> list[dict[str, Any]]:
        """Fetch Congress trading data.

        This is a placeholder implementation. In production, this would
        connect to the Senate/House Electronic Filing System or use
        a third-party API like Quiver Quantitative.
        """
        # Placeholder: In production, implement actual Congress data fetching
        logger.info("Congress data fetching not yet implemented (placeholder)")
        return []

    def _build_congress_event(
        self, raw: dict[str, Any], llm_result: dict[str, Any]
    ) -> FeedEvent | None:
        """Build a FeedEvent from Congress trade data."""
        try:
            ticker = raw.get("ticker", "")
            event_id = compute_congress_event_id(
                stock_ticker=ticker,
                last_name=raw.get("lastName", ""),
                disclosure_date=raw.get("disclosureDate", ""),
                amount=raw.get("amount", ""),
                transaction_type=raw.get("type", ""),
            )

            actor = Actor(
                nameEn=f"{raw.get('firstName', '')} {raw.get('lastName', '')}".strip(),
                nameZh=llm_result.get("titleZh", "").split(" - ")[0] if " - " in llm_result.get("titleZh", "") else raw.get("lastName", ""),
                identityEn=raw.get("office", ""),
                identityZh=llm_result.get("identityZh", raw.get("office", "")),
            )

            action = ActionType.BUY if raw.get("type", "").upper() == "P" else ActionType.SELL

            financials = Financials(
                action=action,
                valueRange=raw.get("amount", ""),
            )

            content = Content(
                titleEn=raw.get("assetDescription", ""),
                titleZh=llm_result.get("titleZh", ""),
                bodyEn="",
                bodyZh=llm_result.get("bodyZh", ""),
            )

            event_time = datetime.now(timezone.utc)
            if raw.get("disclosureDate"):
                try:
                    event_time = datetime.fromisoformat(raw["disclosureDate"])
                except (ValueError, TypeError):
                    pass

            return FeedEvent(
                eventId=event_id,
                source=EventSource.CONGRESS,
                ticker=ticker,
                eventTimestamp=event_time,
                actor=actor,
                financials=financials,
                content=content,
                sourceUrl=raw.get("link", ""),
            )
        except Exception as e:
            logger.error(f"Failed to build Congress event: {e}")
            return None

    def _build_insider_event(
        self, raw: dict[str, Any], llm_result: dict[str, Any]
    ) -> FeedEvent | None:
        """Build a FeedEvent from insider trade data."""
        try:
            symbol = raw.get("_symbol", raw.get("symbol", ""))
            event_id = raw.get("_eventId", "")

            insider_name = raw.get("insiderName", "")
            actor = Actor(
                nameEn=insider_name,
                nameZh=llm_result.get("titleZh", "").split(" - ")[0] if " - " in llm_result.get("titleZh", "") else insider_name,
                identityEn=raw.get("typeOfOwner", ""),
                identityZh=llm_result.get("identityZh", raw.get("typeOfOwner", "")),
            )

            tx_type = raw.get("transactionType", "S")
            action = ActionType.BUY if tx_type.upper() in ("P", "PURCHASE") else ActionType.SELL

            shares = float(raw.get("securitiesTransacted", 0))
            price = float(raw.get("price", 0))
            financials = Financials(
                action=action,
                price=price,
                volume=shares,
            )

            content = Content(
                titleEn=f"{insider_name} {action.value} {shares} shares of {symbol}",
                titleZh=llm_result.get("titleZh", ""),
                bodyEn="",
                bodyZh=llm_result.get("bodyZh", ""),
            )

            event_time = datetime.now(timezone.utc)
            if raw.get("filingDate"):
                try:
                    event_time = datetime.fromisoformat(raw["filingDate"])
                except (ValueError, TypeError):
                    pass

            return FeedEvent(
                eventId=event_id,
                source=EventSource.INSIDER,
                ticker=symbol,
                eventTimestamp=event_time,
                actor=actor,
                financials=financials,
                content=content,
                sourceUrl=raw.get("link", ""),
            )
        except Exception as e:
            logger.error(f"Failed to build insider event: {e}")
            return None

    def _build_article_event(
        self, raw: dict[str, Any], llm_result: dict[str, Any]
    ) -> FeedEvent | None:
        """Build a FeedEvent from news article data."""
        try:
            symbol = raw.get("_symbol", raw.get("symbol", ""))
            event_id = raw.get("_eventId", "")

            actor = Actor(
                nameEn=raw.get("author", "Unknown"),
                nameZh=raw.get("author", "未知"),
                identityEn="Financial News",
                identityZh="金融新闻",
            )

            content = Content(
                titleEn=raw.get("title", ""),
                titleZh=llm_result.get("titleZh", ""),
                bodyEn=raw.get("text", "")[:500],
                bodyZh=llm_result.get("bodyZh", ""),
            )

            event_time = datetime.now(timezone.utc)
            if raw.get("publishedDate"):
                try:
                    event_time = datetime.fromisoformat(raw["publishedDate"])
                except (ValueError, TypeError):
                    pass

            return FeedEvent(
                eventId=event_id,
                source=EventSource.ARTICLE,
                ticker=symbol,
                eventTimestamp=event_time,
                actor=actor,
                content=content,
                sourceUrl=raw.get("url", ""),
            )
        except Exception as e:
            logger.error(f"Failed to build article event: {e}")
            return None

    def _store_feeds(
        self,
        all_events: list[FeedEvent],
        congress_events: list[FeedEvent],
        insider_events: list[FeedEvent],
    ) -> None:
        """Store feeds to R2 storage."""
        # Store latest_feeds.json
        feeds_data = [event.model_dump(by_alias=True) for event in all_events]
        self._r2.put_object("feeds/latest_feeds.json", feeds_data)

        # Generate and store RSS feeds
        congress_rss = generate_congress_rss(congress_events)
        self._r2.put_xml_object("feeds/rss_congress.xml", congress_rss)

        insider_rss = generate_insider_rss(insider_events)
        self._r2.put_xml_object("feeds/rss_insider.xml", insider_rss)

        # Store per-ticker feeds
        ticker_events: dict[str, list[FeedEvent]] = {}
        for event in all_events:
            if event.ticker not in ticker_events:
                ticker_events[event.ticker] = []
            ticker_events[event.ticker].append(event)

        for ticker, events in ticker_events.items():
            ticker_data = [e.model_dump(by_alias=True) for e in events]
            self._r2.put_object(f"symbols/{ticker}.json", ticker_data)

    def _update_sliding_window(
        self,
        window: dict[str, datetime],
        events: list[FeedEvent],
    ) -> None:
        """Update the sliding window with new events."""
        now = datetime.now(timezone.utc)
        for event in events:
            window[event.event_id] = now


async def run_pipeline() -> dict[str, Any]:
    """Entry point for running the ETL pipeline."""
    pipeline = ETLPipeline()
    return await pipeline.run()
