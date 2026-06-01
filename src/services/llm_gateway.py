"""LLM Gateway for AI processing.

This module implements the array-packed prompting strategy for efficient
LLM batch processing, with support for both SDK and direct HTTP modes.
Includes circuit breaker for graceful degradation.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI

from src.models.feed import Actor, Content, EventSource, FeedEvent, Financials, ActionType
from src.utils.config import LLMConfig

logger = logging.getLogger(__name__)

_circuit_open = False
_failure_count = 0
_max_failures = 3
_CIRCUIT_R2_KEY = "snapshot/circuit_breaker.json"
_r2_client: Any = None  # Will be set by ETL pipeline


def set_r2_client(r2_client: Any) -> None:
    """Set R2 client for circuit breaker persistence."""
    global _r2_client
    _r2_client = r2_client


def configure_circuit_breaker(max_failures: int) -> None:
    """Configure circuit breaker threshold from app config."""
    global _max_failures
    _max_failures = max(1, max_failures)


def _load_circuit_state() -> None:
    """Load circuit breaker state from R2."""
    global _circuit_open, _failure_count
    if _r2_client is None:
        return
    try:
        data = _r2_client.get_object(_CIRCUIT_R2_KEY)
        if data:
            _circuit_open = data.get("circuit_open", False)
            _failure_count = data.get("failure_count", 0)
            logger.info(f"Loaded circuit state: open={_circuit_open}, failures={_failure_count}")
    except Exception as e:
        logger.warning(f"Failed to load circuit state: {e}")


def _save_circuit_state() -> None:
    """Save circuit breaker state to R2."""
    if _r2_client is None:
        return
    try:
        data = {
            "circuit_open": _circuit_open,
            "failure_count": _failure_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _r2_client.put_object(_CIRCUIT_R2_KEY, data)
    except Exception as e:
        logger.warning(f"Failed to save circuit state: {e}")


def reset_circuit_breaker() -> None:
    """Reset the circuit breaker state."""
    global _circuit_open, _failure_count
    _circuit_open = False
    _failure_count = 0
    _save_circuit_state()


def is_circuit_open() -> bool:
    """Check if the circuit breaker is open."""
    _load_circuit_state()
    return _circuit_open


def _record_failure() -> None:
    """Record a failure and potentially open the circuit."""
    global _circuit_open, _failure_count
    _failure_count += 1
    if _failure_count >= _max_failures:
        _circuit_open = True
        logger.warning("LLM circuit breaker opened due to repeated failures")
    _save_circuit_state()


def _record_success() -> None:
    """Record a success and reset failure count / close circuit."""
    global _failure_count, _circuit_open
    _failure_count = 0
    _circuit_open = False
    _save_circuit_state()


# Prompt templates for different event types
CONGRESS_PROMPT = """You are a financial analyst specializing in US Congress trading activities.
Analyze the following Congress trade data and provide a bilingual response.

For each trade, provide:
1. Chinese translation of the congress member's name, party, and committee
2. A concise AI investment insight in Chinese (max 60 characters)
3. Highlight the transaction amount range

Input data (JSON array):
{data}

Respond with a JSON object containing a "results" array where each element has:
- "titleZh": Chinese title for the trade
- "bodyZh": Chinese body with AI insight starting with "🤖 AI 投资洞察："
- "identityZh": Chinese identity including party and committee
"""

INSIDER_PROMPT = """You are a financial analyst specializing in insider trading analysis.
Analyze the following insider trading data and provide bilingual responses.

For each trade, provide:
1. Chinese translation of the insider's name and title
2. Calculate total transaction value (shares × price)
3. BUY highlighted in neon green, SELL highlighted in neon red

Input data (JSON array):
{data}

Respond with a JSON object containing a "results" array where each element has:
- "titleZh": Chinese title for the trade
- "bodyZh": Chinese body with transaction analysis
- "identityZh": Chinese identity/role
"""

ARTICLE_PROMPT = """You are a financial news analyst.
Analyze the following news articles and extract key investment signals.

For each article, provide:
1. Structured Chinese translation of the title
2. Filter out low-value content
3. Extract core bullish/bearish sentiment and reasoning

Input data (JSON array):
{data}

Respond with a JSON object containing a "results" array where each element has:
- "titleZh": Structured Chinese translation of the title
- "bodyZh": Chinese summary with key investment signals
"""


class LLMGateway:
    """LLM Gateway supporting SDK and direct HTTP modes."""

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self._config = config or LLMConfig()
        configure_circuit_breaker(self._config.max_failures)
        self._sdk_client: Optional[AsyncOpenAI] = None
        self._http_client: Optional[httpx.AsyncClient] = None

        if self._config.mode == "SDK_MODE":
            self._sdk_client = AsyncOpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
            )
        else:
            self._http_client = httpx.AsyncClient(timeout=120.0)

    async def close(self) -> None:
        """Close clients."""
        if self._sdk_client:
            await self._sdk_client.close()
        if self._http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> "LLMGateway":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _call_sdk(self, prompt: str) -> str:
        """Call LLM via SDK mode."""
        if not self._sdk_client:
            raise RuntimeError("SDK client not initialized")
        response = await self._sdk_client.chat.completions.create(
            model=self._config.model,
            messages=[
                {"role": "system", "content": "You are a helpful financial analyst assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "[]"

    async def _call_direct_http(self, prompt: str) -> str:
        """Call LLM via direct HTTP mode."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")
        url = self._config.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        response = await self._http_client.post(
            url,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._config.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful financial analyst assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def process_batch(self, prompt: str) -> str:
        """Process a batch request through the LLM gateway.

        Args:
            prompt: The formatted prompt to send.

        Returns:
            The LLM response as a string.

        Raises:
            Exception: If the circuit breaker is open or the call fails.
        """
        if is_circuit_open():
            logger.warning("Circuit breaker is open, using fallback")
            raise RuntimeError("LLM circuit breaker is open")

        try:
            if self._config.mode == "SDK_MODE":
                result = await self._call_sdk(prompt)
            else:
                result = await self._call_direct_http(prompt)
            _record_success()
            return result
        except Exception as e:
            _record_failure()
            logger.error(f"LLM call failed: {e}")
            raise

    def _chunk_data(self, data: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Split data into chunks for batch processing."""
        chunk_size = self._config.chunk_size
        return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    def _parse_llm_response(self, response: str) -> list[dict[str, Any]]:
        """Parse LLM response with defensive error handling.

        Args:
            response: Raw LLM response string.

        Returns:
            Parsed list of results.
        """
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return []

        # Handle different response formats
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            # Try common response keys
            results = parsed.get("results", parsed.get("items", parsed.get("data", [])))
            if isinstance(results, list):
                return results
            elif results is not None:
                return [results]
            return []
        elif parsed is not None:
            return [parsed]
        return []

    def _align_results(
        self,
        inputs: list[dict[str, Any]],
        results: list[dict[str, Any]],
        fallback_fn: Any,
    ) -> list[dict[str, Any]]:
        """Ensure LLM output count matches input count to prevent zip misalignment."""
        if len(results) >= len(inputs):
            return results[: len(inputs)]
        aligned = list(results)
        if len(results) < len(inputs):
            aligned.extend(fallback_fn(inputs[len(results) :]))
        return aligned

    async def process_congress_trades(
        self, trades: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process Congress trades through LLM for translation and analysis."""
        if not trades:
            return []

        if is_circuit_open():
            return self._fallback_congress(trades)

        chunks = self._chunk_data(trades)
        all_results: list[dict[str, Any]] = []

        for chunk in chunks:
            prompt = CONGRESS_PROMPT.format(data=json.dumps(chunk, default=str))
            try:
                response = await self.process_batch(prompt)
                results = self._parse_llm_response(response)
                if not isinstance(results, list):
                    results = [results] if results else []
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Failed to process congress batch: {e}")
                all_results.extend(self._fallback_congress(chunk))

        return self._align_results(trades, all_results, self._fallback_congress)

    async def process_insider_trades(
        self, trades: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process insider trades through LLM for translation and analysis."""
        if not trades:
            return []

        if is_circuit_open():
            return self._fallback_insider(trades)

        chunks = self._chunk_data(trades)
        all_results: list[dict[str, Any]] = []

        for chunk in chunks:
            prompt = INSIDER_PROMPT.format(data=json.dumps(chunk, default=str))
            try:
                response = await self.process_batch(prompt)
                results = self._parse_llm_response(response)
                if not isinstance(results, list):
                    results = [results] if results else []
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Failed to process insider batch: {e}")
                all_results.extend(self._fallback_insider(chunk))

        return self._align_results(trades, all_results, self._fallback_insider)

    async def process_articles(
        self, articles: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process news articles through LLM for translation and analysis."""
        if not articles:
            return []

        if is_circuit_open():
            return self._fallback_articles(articles)

        chunks = self._chunk_data(articles)
        all_results: list[dict[str, Any]] = []

        for chunk in chunks:
            prompt = ARTICLE_PROMPT.format(data=json.dumps(chunk, default=str))
            try:
                response = await self.process_batch(prompt)
                results = self._parse_llm_response(response)
                if not isinstance(results, list):
                    results = [results] if results else []
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Failed to process article batch: {e}")
                all_results.extend(self._fallback_articles(chunk))

        return self._align_results(articles, all_results, self._fallback_articles)

    def _fallback_congress(self, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fallback for Congress trades when LLM is unavailable."""
        return [
            {
                "titleZh": (
                    f"[暂无AI翻译] {t.get('firstName', '')} {t.get('lastName', '')} - "
                    f"{t.get('assetDescription', '')}"
                ).strip(),
                "bodyZh": "LLM网关瞬时拥堵，AI分析延迟注入。",
                "identityZh": f"{t.get('office', '联邦议员')} ({t.get('stateDistrict', '')})",
            }
            for t in trades
        ]

    def _fallback_insider(self, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fallback for insider trades when LLM is unavailable."""
        return [
            {
                "titleZh": f"[暂无AI翻译] {t.get('insiderName', '')} - {t.get('transactionType', '')}",
                "bodyZh": "LLM网关瞬时拥堵，AI分析延迟注入。",
                "identityZh": t.get("typeOfOwner", ""),
            }
            for t in trades
        ]

    def _fallback_articles(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fallback for articles when LLM is unavailable."""
        return [
            {
                "titleZh": f"[暂无AI翻译] {a.get('title', '')}",
                "bodyZh": "LLM网关瞬时拥堵，AI分析延迟注入。",
            }
            for a in articles
        ]
