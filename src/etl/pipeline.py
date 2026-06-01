"""Main ETL pipeline orchestrator.

This module implements the core ETL pipeline that:
1. Fetches data from FMP API
2. Performs MD5 fingerprint deduplication
3. Processes through LLM gateway
4. Stores results in R2
5. Generates RSS feeds
"""

import logging
from datetime import datetime, timezone
from typing import Any

from src.models.feed import (
    Actor,
    Content,
    EventSource,
    FeedEvent,
    Financials,
)
from src.services.congress_client import CongressClient
from src.services.fmp_client import FMPClient
from src.services.llm_gateway import LLMGateway, set_r2_client
from src.services.r2_client import R2Client
from src.services.rss_generator import generate_congress_rss, generate_insider_rss
from src.utils.config import AppConfig, DEFAULT_TICKERS, load_config
from src.utils.fingerprint import (
    compute_article_event_id,
    compute_congress_event_id,
    compute_insider_event_id,
    filter_new_events,
    prune_expired_entries,
)
from src.utils.trading import parse_action_type

logger = logging.getLogger(__name__)


class ETLPipeline:
    """Main ETL pipeline orchestrator."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or load_config()
        self._dry_run = self._config.dry_run
        self._days_back = self._config.etl.days_back
        self._max_feed_items = self._config.etl.max_feed_items
        self._fmp = FMPClient(self._config.fmp)
        self._congress = CongressClient(self._config)
        self._llm = LLMGateway(self._config.llm)
        self._r2 = R2Client(self._config.r2)
        set_r2_client(self._r2)

    async def run(self) -> dict[str, Any]:
        """Execute the full ETL pipeline."""
        logger.info("Starting ETL pipeline execution")
        if self._dry_run:
            logger.info("DRY_RUN enabled — R2 writes will be skipped")

        start_time = datetime.now(timezone.utc)
        whitelist = self._resolve_whitelist()
        window = self._load_sliding_window()

        summary: dict[str, Any] = {
            "start_time": start_time.isoformat(),
            "tickers_processed": len(whitelist),
            "new_congress_events": 0,
            "new_insider_events": 0,
            "new_article_events": 0,
            "dry_run": self._dry_run,
            "errors": [],
        }

        try:
            congress_events = await self._process_congress_data(whitelist, window)
            insider_events = await self._process_insider_data(whitelist, window)
            article_events = await self._process_article_data(whitelist, window)

            summary["new_congress_events"] = len(congress_events)
            summary["new_insider_events"] = len(insider_events)
            summary["new_article_events"] = len(article_events)

            new_events = congress_events + insider_events + article_events
            summary["total_new_events"] = len(new_events)

            if new_events:
                self._update_sliding_window(window, new_events)

            if not self._dry_run:
                self._r2.save_sliding_window(window)
            else:
                logger.info("DRY_RUN: skipping sliding window save")

            if new_events:
                self._store_feeds(new_events)

            end_time = datetime.now(timezone.utc)
            summary["end_time"] = end_time.isoformat()
            summary["duration_seconds"] = (end_time - start_time).total_seconds()

            logger.info(f"ETL pipeline completed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"ETL pipeline failed: {e}")
            summary["errors"].append(str(e))
            raise
        finally:
            await self._fmp.close()
            await self._congress.close()
            await self._llm.close()

    def _resolve_whitelist(self) -> list[str]:
        """Load whitelist from R2, falling back to defaults when empty."""
        whitelist = self._r2.load_whitelist()
        if whitelist:
            return whitelist

        logger.info(f"Whitelist empty, using {len(DEFAULT_TICKERS)} default tickers")
        if not self._dry_run:
            self._r2.save_whitelist(list(DEFAULT_TICKERS))
        return list(DEFAULT_TICKERS)

    def _load_sliding_window(self) -> dict[str, datetime]:
        window_data = self._r2.load_sliding_window()
        window: dict[str, datetime] = {}
        for eid, ts in window_data.items():
            try:
                if isinstance(ts, str):
                    window[eid] = datetime.fromisoformat(ts)
                elif isinstance(ts, datetime):
                    window[eid] = ts
                else:
                    logger.warning(f"Invalid timestamp type for event {eid}: {type(ts)}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse timestamp for event {eid}: {e}")
        return prune_expired_entries(window)

    async def _process_congress_data(
        self,
        tickers: list[str],
        window: dict[str, datetime],
    ) -> list[FeedEvent]:
        logger.info("Processing Congress trading data")
        raw_trades = await self._fetch_congress_trades(tickers)
        if not raw_trades:
            return []

        event_ids = [
            compute_congress_event_id(
                stock_ticker=trade.get("ticker", ""),
                last_name=trade.get("lastName", ""),
                disclosure_date=trade.get("disclosureDate", ""),
                amount=trade.get("amount", ""),
                transaction_type=trade.get("type", ""),
            )
            for trade in raw_trades
        ]
        new_ids = set(filter_new_events(window, event_ids))
        new_trades = [t for t, eid in zip(raw_trades, event_ids) if eid in new_ids]
        if not new_trades:
            return []

        processed = await self._llm.process_congress_trades(new_trades)
        events: list[FeedEvent] = []
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
        logger.info("Processing insider trading data")
        raw_trades = await self._fmp.get_batch_insider_trading(tickers, days_back=self._days_back)

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

        processed = await self._llm.process_insider_trades(all_new_trades)
        events: list[FeedEvent] = []
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
        logger.info("Processing news article data")
        raw_articles = await self._fmp.get_batch_stock_news(tickers, days_back=self._days_back)

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

        processed = await self._llm.process_articles(all_new_articles)
        events: list[FeedEvent] = []
        for article, llm_result in zip(all_new_articles, processed):
            event = self._build_article_event(article, llm_result)
            if event:
                events.append(event)
        return events

    async def _fetch_congress_trades(self, tickers: list[str]) -> list[dict[str, Any]]:
        try:
            raw_trades = await self._congress.get_congress_trades(
                tickers=tickers, days_back=self._days_back
            )
            logger.info(f"Fetched {len(raw_trades)} Congress trades")
            return raw_trades
        except Exception as e:
            logger.error(f"Failed to fetch Congress trades: {e}")
            return []

    def _build_congress_event(
        self, raw: dict[str, Any], llm_result: dict[str, Any]
    ) -> FeedEvent | None:
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
                nameZh=llm_result.get("titleZh", "").split(" - ")[0]
                if " - " in llm_result.get("titleZh", "")
                else raw.get("lastName", ""),
                identityEn=raw.get("office", ""),
                identityZh=llm_result.get("identityZh", raw.get("office", "")),
            )

            action = parse_action_type(raw.get("type", ""))
            financials = Financials(action=action, valueRange=raw.get("amount", ""))
            content = Content(
                titleEn=raw.get("assetDescription", ""),
                titleZh=llm_result.get("titleZh", ""),
                bodyEn="",
                bodyZh=llm_result.get("bodyZh", ""),
            )

            event_time = self._parse_event_time(raw.get("disclosureDate"))
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
        try:
            symbol = raw.get("_symbol", raw.get("symbol", ""))
            event_id = raw.get("_eventId", "")
            insider_name = raw.get("insiderName", "")

            actor = Actor(
                nameEn=insider_name,
                nameZh=llm_result.get("titleZh", "").split(" - ")[0]
                if " - " in llm_result.get("titleZh", "")
                else insider_name,
                identityEn=raw.get("typeOfOwner", ""),
                identityZh=llm_result.get("identityZh", raw.get("typeOfOwner", "")),
            )

            action = parse_action_type(
                raw.get("transactionType", ""),
                raw.get("acquisitionOrDisposition"),
            )
            shares = float(raw.get("securitiesTransacted", 0))
            price = float(raw.get("price", 0) or 0)
            financials = Financials(action=action, price=price, volume=shares)
            content = Content(
                titleEn=f"{insider_name} {action.value} {shares} shares of {symbol}",
                titleZh=llm_result.get("titleZh", ""),
                bodyEn="",
                bodyZh=llm_result.get("bodyZh", ""),
            )

            event_time = self._parse_event_time(raw.get("filingDate"))
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

            event_time = self._parse_event_time(raw.get("publishedDate"))
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

    @staticmethod
    def _parse_event_time(raw_value: Any) -> datetime:
        if raw_value:
            try:
                return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        return datetime.now(timezone.utc)

    def _merge_feed_dicts(
        self,
        existing: list[dict[str, Any]],
        new_events: list[FeedEvent],
    ) -> list[dict[str, Any]]:
        by_id = {item["eventId"]: item for item in existing if item.get("eventId")}
        for event in new_events:
            by_id[event.event_id] = event.model_dump(by_alias=True)
        merged = list(by_id.values())
        merged.sort(key=lambda item: item.get("eventTimestamp", ""), reverse=True)
        return merged[: self._max_feed_items]

    @staticmethod
    def _feed_dicts_to_events(
        feed_dicts: list[dict[str, Any]],
        source: EventSource,
    ) -> list[FeedEvent]:
        events: list[FeedEvent] = []
        for item in feed_dicts:
            if item.get("source") != source.value:
                continue
            try:
                events.append(FeedEvent.model_validate(item))
            except Exception as e:
                logger.warning(f"Skipping invalid feed item {item.get('eventId')}: {e}")
        return events

    def _store_feeds(self, new_events: list[FeedEvent]) -> None:
        """Merge new events into existing feeds and persist snapshots."""
        existing = self._r2.load_latest_feeds()
        merged = self._merge_feed_dicts(existing, new_events)

        if self._dry_run:
            logger.info(
                f"DRY_RUN: would store {len(merged)} total feeds "
                f"({len(new_events)} new)"
            )
            return

        self._r2.put_object("feeds/latest_feeds.json", merged)

        congress_events = self._feed_dicts_to_events(merged, EventSource.CONGRESS)
        insider_events = self._feed_dicts_to_events(merged, EventSource.INSIDER)

        self._r2.put_xml_object(
            "feeds/rss_congress.xml",
            generate_congress_rss(congress_events),
        )
        self._r2.put_xml_object(
            "feeds/rss_insider.xml",
            generate_insider_rss(insider_events),
        )

        tickers_with_new_data = {event.ticker for event in new_events if event.ticker}
        for ticker in tickers_with_new_data:
            existing_ticker = self._r2.load_ticker_feeds(ticker)
            ticker_new = [event for event in new_events if event.ticker == ticker]
            merged_ticker = self._merge_feed_dicts(existing_ticker, ticker_new)
            self._r2.put_object(f"symbols/{ticker}.json", merged_ticker)

    def _update_sliding_window(
        self,
        window: dict[str, datetime],
        events: list[FeedEvent],
    ) -> None:
        now = datetime.now(timezone.utc)
        for event in events:
            window[event.event_id] = now


async def run_pipeline() -> dict[str, Any]:
    """Entry point for running the ETL pipeline."""
    pipeline = ETLPipeline()
    return await pipeline.run()
