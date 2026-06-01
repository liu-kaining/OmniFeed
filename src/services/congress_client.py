"""Congress trading data client.

This module provides a client for fetching US Congress trading data
from various sources including Quiver Quantitative API.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from src.utils.config import AppConfig

logger = logging.getLogger(__name__)


class CongressClient:
    """Client for fetching Congress trading data."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._config = config
        # Quiver Quantitative API (requires API key)
        # Alternative: Use Senate EFD scraper or House XML feed
        self._quiver_base = "https://api.quiverquant.com/beta"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "CongressClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def get_congress_trades(
        self,
        tickers: Optional[list[str]] = None,
        days_back: int = 7,
    ) -> list[dict[str, Any]]:
        """Fetch Congress trading data.

        This implementation fetches from Quiver Quantitative API.
        In production, you may also use:
        - Senate Electronic Filing System (EFD)
        - House XML Disclosure Feed
        - Capitol Trades API

        Args:
            tickers: Optional list of ticker symbols to filter.
            days_back: Number of days to look back.

        Returns:
            List of Congress trade records in standardized format.
        """
        try:
            # Try Quiver Quantitative API first
            trades = await self._fetch_from_quiver(tickers, days_back)
            if trades:
                return self._normalize_quiver_trades(trades)
        except Exception as e:
            logger.warning(f"Quiver API failed: {e}")

        try:
            # Fallback to Capitol Trades (free, no API key required)
            trades = await self._fetch_from_capitol_trades(tickers, days_back)
            if trades:
                return self._normalize_capitol_trades(trades)
        except Exception as e:
            logger.warning(f"Capitol Trades API failed: {e}")

        logger.warning("All Congress data sources failed, returning empty list")
        return []

    async def _fetch_from_quiver(
        self,
        tickers: Optional[list[str]],
        days_back: int,
    ) -> list[dict[str, Any]]:
        """Fetch from Quiver Quantitative API.

        Requires QUIVER_API_KEY environment variable.
        """
        api_key = self._config.fmp.api_key if self._config else None
        if not api_key:
            raise ValueError("API key not configured for Quiver")

        headers = {"X-API-KEY": api_key}
        params: dict[str, Any] = {}

        if tickers:
            # Quiver allows filtering by ticker
            params["tickers"] = ",".join(tickers)

        response = await self._client.get(
            f"{self._quiver_base}/congresstrading",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def _fetch_from_capitol_trades(
        self,
        tickers: Optional[list[str]],
        days_back: int,
    ) -> list[dict[str, Any]]:
        """Fetch from Capitol Trades (free API).

        This is a fallback option that doesn't require API keys.
        """
        # Capitol Trades API endpoint
        base_url = "https://api.capitoltrades.com/trades"
        cutoff_date = datetime.now() - timedelta(days=days_back)

        params: dict[str, Any] = {
            "page": 1,
            "pageSize": 100,
            "sortBy": "transactionDate",
            "sortOrder": "desc",
        }

        if tickers:
            params["ticker"] = ",".join(tickers)

        response = await self._client.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        # Filter by date
        trades = data.get("data", data.get("trades", []))
        filtered = []
        for trade in trades:
            try:
                trade_date = datetime.fromisoformat(
                    trade.get("transactionDate", "").replace("Z", "+00:00")
                )
                if trade_date >= cutoff_date:
                    filtered.append(trade)
            except (ValueError, TypeError):
                # Include trade if date parsing fails
                filtered.append(trade)

        return filtered

    def _normalize_quiver_trades(
        self, trades: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize Quiver Quantitative data to standard format."""
        normalized = []
        for trade in trades:
            normalized.append({
                "ticker": trade.get("Ticker", trade.get("ticker", "")),
                "firstName": trade.get("FirstName", trade.get("firstName", "")),
                "lastName": trade.get("LastName", trade.get("lastName", "")),
                "office": trade.get("Office", trade.get("office", "")),
                "disclosureDate": trade.get("DisclosureDate", trade.get("disclosureDate", "")),
                "transactionDate": trade.get("TransactionDate", trade.get("transactionDate", "")),
                "assetDescription": trade.get("AssetDescription", trade.get("assetDescription", "")),
                "type": trade.get("TransactionType", trade.get("type", "")),
                "amount": trade.get("Amount", trade.get("amount", "")),
                "owner": trade.get("Owner", trade.get("owner", "")),
                "stateDistrict": trade.get("StateDistrict", trade.get("stateDistrict", "")),
                "link": trade.get("DisclosureLink", trade.get("link", "")),
            })
        return normalized

    def _normalize_capitol_trades(
        self, trades: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize Capitol Trades data to standard format."""
        normalized = []
        for trade in trades:
            # Extract first/last name from full name
            full_name = trade.get("politician", trade.get("name", ""))
            name_parts = full_name.split(" ", 1) if full_name else ["", ""]
            first_name = name_parts[0] if len(name_parts) > 0 else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            # Map transaction type
            tx_type = trade.get("type", trade.get("transactionType", ""))
            if tx_type in ("Purchase", "purchase", "Buy", "buy"):
                tx_type = "P"
            elif tx_type in ("Sale", "sale", "Sell", "sell", "Sale (Full)", "Sale (Partial)"):
                tx_type = "S"

            normalized.append({
                "ticker": trade.get("ticker", trade.get("symbol", "")),
                "firstName": first_name,
                "lastName": last_name,
                "office": trade.get("office", trade.get("chamber", "")),
                "disclosureDate": trade.get("disclosureDate", trade.get("publishedAt", "")),
                "transactionDate": trade.get("transactionDate", trade.get("tradedAt", "")),
                "assetDescription": trade.get("assetDescription", trade.get("asset", "")),
                "type": tx_type,
                "amount": trade.get("amount", trade.get("amountRange", "")),
                "owner": trade.get("owner", ""),
                "stateDistrict": trade.get("stateDistrict", trade.get("state", "")),
                "link": trade.get("sourceUrl", trade.get("link", "")),
            })
        return normalized
