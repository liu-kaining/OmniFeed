"""Financial Modeling Prep API client.

This module provides a client for fetching financial data from FMP API,
including insider trading and stock news.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from src.utils.config import FMPConfig

logger = logging.getLogger(__name__)


class FMPClient:
    """Client for Financial Modeling Prep API."""

    def __init__(self, config: Optional[FMPConfig] = None) -> None:
        self._config = config or FMPConfig()
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            params={"apikey": self._config.api_key},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "FMPClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def get_insider_trading(
        self,
        symbol: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch insider trading data for a given symbol.

        Args:
            symbol: Stock ticker symbol.
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.
            limit: Maximum number of results.

        Returns:
            List of insider trading records.
        """
        params: dict[str, Any] = {"symbol": symbol, "limit": limit}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        try:
            response = await self._client.get("/insider-trading", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"FMP API error for insider trading {symbol}: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch insider trading for {symbol}: {e}")
            return []

    async def get_stock_news(
        self,
        tickers: Optional[list[str]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch stock news articles.

        Args:
            tickers: List of ticker symbols to filter.
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.
            limit: Maximum number of results.

        Returns:
            List of news articles.
        """
        params: dict[str, Any] = {"limit": limit}
        if tickers:
            params["tickers"] = ",".join(tickers)
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        try:
            response = await self._client.get("/stock_news", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"FMP API error for stock news: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch stock news: {e}")
            return []

    async def get_batch_insider_trading(
        self,
        symbols: list[str],
        days_back: int = 7,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch insider trading for multiple symbols.

        Args:
            symbols: List of stock ticker symbols.
            days_back: Number of days to look back.

        Returns:
            Dictionary mapping symbol to list of trading records.
        """
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        result: dict[str, list[dict[str, Any]]] = {}
        for symbol in symbols:
            records = await self.get_insider_trading(
                symbol=symbol,
                from_date=from_date,
                to_date=to_date,
            )
            if records:
                result[symbol] = records
        return result

    async def get_batch_stock_news(
        self,
        symbols: list[str],
        days_back: int = 7,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch stock news for multiple symbols grouped by ticker.

        Args:
            symbols: List of stock ticker symbols.
            days_back: Number of days to look back.

        Returns:
            Dictionary mapping symbol to list of news articles.
        """
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        articles = await self.get_stock_news(
            tickers=symbols,
            from_date=from_date,
            to_date=to_date,
        )

        result: dict[str, list[dict[str, Any]]] = {}
        for article in articles:
            ticker = article.get("symbol", "")
            if ticker:
                if ticker not in result:
                    result[ticker] = []
                result[ticker].append(article)
        return result
