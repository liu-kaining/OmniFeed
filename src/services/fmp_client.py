"""Financial Modeling Prep API client.

Uses FMP stable API as the primary surface:
- Insider trades: /stable/insider-trading/search
- Stock news: /stable/news/stock

Falls back to legacy v4/v3 endpoints when stable requests fail.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from src.utils.config import FMPConfig

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 5
_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    return _semaphore


def _parse_fmp_list(data: Any) -> list[dict[str, Any]]:
    """Parse list payloads from stable/v3/v4 response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("Error Message"), str):
            logger.error(f"FMP API error: {data['Error Message']}")
            return []
        for key in ("data", "results", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def normalize_insider_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Map FMP stable/v4 insider fields to the internal canonical schema."""
    acquisition = raw.get("acquisitionOrDisposition") or raw.get("acquistionOrDisposition") or ""
    return {
        "symbol": raw.get("symbol", ""),
        "insiderName": raw.get("reportingName") or raw.get("insiderName") or "",
        "filingDate": raw.get("transactionDate") or raw.get("filingDate") or "",
        "transactionType": raw.get("transactionType", ""),
        "securitiesTransacted": raw.get("securitiesTransacted", 0),
        "price": raw.get("price", 0),
        "typeOfOwner": raw.get("typeOfOwner") or raw.get("securityName") or "",
        "link": raw.get("link") or raw.get("url") or "",
        "acquisitionOrDisposition": acquisition,
    }


def normalize_news_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Map FMP stable/v3 news fields to the internal canonical schema."""
    return {
        "symbol": raw.get("symbol", ""),
        "title": raw.get("title", ""),
        "publishedDate": raw.get("publishedDate") or raw.get("date") or "",
        "text": raw.get("text") or raw.get("content") or "",
        "url": raw.get("url") or raw.get("link") or "",
        "author": raw.get("site") or raw.get("author") or "Unknown",
    }


def _filter_records_by_date(
    records: list[dict[str, Any]],
    date_fields: tuple[str, ...],
    from_date: str,
    to_date: str,
) -> list[dict[str, Any]]:
    """Keep records whose date field falls within [from_date, to_date]."""
    filtered: list[dict[str, Any]] = []
    for record in records:
        day = ""
        for field in date_fields:
            raw_date = str(record.get(field, "")).strip()
            if raw_date:
                day = raw_date[:10]
                break
        if not day:
            continue
        if from_date <= day <= to_date:
            filtered.append(record)
    return filtered


class FMPClient:
    """Client for Financial Modeling Prep API."""

    def __init__(self, config: Optional[FMPConfig] = None) -> None:
        self._config = config or FMPConfig()
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "FMPClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _request(
        self,
        base_url: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        query = {"apikey": self._config.api_key, **(params or {})}
        response = await self._client.get(f"{base_url.rstrip('/')}/{path.lstrip('/')}", params=query)
        response.raise_for_status()
        return _parse_fmp_list(response.json())

    async def get_insider_trading(
        self,
        symbol: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch insider trading for one symbol (stable primary, v4 fallback)."""
        request_limit = limit or self._config.insider_limit
        params: dict[str, Any] = {
            "symbol": symbol,
            "page": 0,
            "limit": request_limit,
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        records: list[dict[str, Any]] = []
        try:
            records = await self._request(
                self._config.base_url, "insider-trading/search", params
            )
            logger.debug(f"Fetched {len(records)} insider trades for {symbol} via stable API")
        except Exception as stable_error:
            logger.warning(f"Stable insider API failed for {symbol}: {stable_error}")
            try:
                fallback_params = {"symbol": symbol, "page": 0, "limit": request_limit}
                records = await self._request(
                    self._config.v4_base_url, "insider-trading", fallback_params
                )
                logger.debug(f"Fetched {len(records)} insider trades for {symbol} via v4 fallback")
            except Exception as v4_error:
                logger.error(f"FMP insider trading failed for {symbol}: {v4_error}")
                return []

        if from_date and to_date:
            records = _filter_records_by_date(
                records,
                ("transactionDate", "filingDate"),
                from_date,
                to_date,
            )

        return [normalize_insider_record(record) for record in records]

    async def get_stock_news(
        self,
        tickers: Optional[list[str]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch stock news (stable primary, v3 fallback)."""
        if not tickers:
            return []

        request_limit = limit or self._config.news_limit
        params: dict[str, Any] = {
            "symbols": ",".join(tickers),
            "page": 0,
            "limit": request_limit,
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        records: list[dict[str, Any]] = []
        try:
            records = await self._request(self._config.base_url, "news/stock", params)
            logger.debug(f"Fetched {len(records)} news articles via stable API")
        except Exception as stable_error:
            logger.warning(f"Stable stock news API failed: {stable_error}")
            try:
                fallback_params: dict[str, Any] = {
                    "tickers": ",".join(tickers),
                    "limit": request_limit,
                }
                if from_date:
                    fallback_params["from"] = from_date
                if to_date:
                    fallback_params["to"] = to_date
                records = await self._request(
                    self._config.v3_base_url, "stock_news", fallback_params
                )
                logger.debug(f"Fetched {len(records)} news articles via v3 fallback")
            except Exception as v3_error:
                logger.error(f"FMP stock news failed: {v3_error}")
                return []

        if from_date and to_date:
            records = _filter_records_by_date(
                records,
                ("publishedDate", "date"),
                from_date,
                to_date,
            )

        return [normalize_news_record(record) for record in records]

    async def get_batch_insider_trading(
        self,
        symbols: list[str],
        days_back: int = 7,
    ) -> dict[str, list[dict[str, Any]]]:
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        semaphore = _get_semaphore()

        async def fetch_with_limit(symbol: str) -> tuple[str, list[dict[str, Any]]]:
            async with semaphore:
                records = await self.get_insider_trading(
                    symbol=symbol,
                    from_date=from_date,
                    to_date=to_date,
                    limit=self._config.insider_limit,
                )
                return symbol, records

        tasks = [fetch_with_limit(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch: dict[str, list[dict[str, Any]]] = {}
        for item in results:
            if isinstance(item, Exception):
                logger.error(f"Batch insider trading fetch failed: {item}")
                continue
            symbol, records = item
            if records:
                batch[symbol] = records
        return batch

    async def get_batch_stock_news(
        self,
        symbols: list[str],
        days_back: int = 7,
    ) -> dict[str, list[dict[str, Any]]]:
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        batch_size = 10
        symbol_batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
        semaphore = _get_semaphore()

        async def fetch_batch(batch: list[str]) -> list[dict[str, Any]]:
            async with semaphore:
                return await self.get_stock_news(
                    tickers=batch,
                    from_date=from_date,
                    to_date=to_date,
                    limit=self._config.news_limit,
                )

        tasks = [fetch_batch(batch) for batch in symbol_batches]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in batch_results:
            if isinstance(item, Exception):
                logger.error(f"Batch stock news fetch failed: {item}")
                continue
            for article in item:
                ticker = article.get("symbol", "")
                if ticker:
                    grouped.setdefault(ticker, []).append(article)
        return grouped
