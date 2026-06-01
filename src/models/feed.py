"""Feed event data models for OmniFeed.

This module defines the data structures for all feed events including
Congress trades, insider transactions, and news articles.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventSource(str, Enum):
    """Data source type for feed events."""
    CONGRESS = "CONGRESS"
    INSIDER = "INSIDER"
    ARTICLE = "ARTICLE"


class ActionType(str, Enum):
    """Transaction action type."""
    BUY = "BUY"
    SELL = "SELL"


class Actor(BaseModel):
    """Actor information with bilingual support."""
    name_en: str = Field(..., alias="nameEn")
    name_zh: str = Field(..., alias="nameZh")
    identity_en: str = Field(..., alias="identityEn")
    identity_zh: str = Field(..., alias="identityZh")

    class Config:
        populate_by_name = True


class Financials(BaseModel):
    """Financial transaction details."""
    action: ActionType
    price: float = 0.0
    volume: float = 0.0
    value_range: str = Field(default="", alias="valueRange")

    class Config:
        populate_by_name = True


class Content(BaseModel):
    """Event content with bilingual support and AI insights."""
    title_en: str = Field(..., alias="titleEn")
    title_zh: str = Field(..., alias="titleZh")
    body_en: str = Field(..., alias="bodyEn")
    body_zh: str = Field(..., alias="bodyZh")

    class Config:
        populate_by_name = True


class FeedEvent(BaseModel):
    """Main feed event model matching the specification schema.

    This is the unified data structure for all event types,
    stored in latest_feeds.json and per-ticker JSON files.
    """
    event_id: str = Field(..., alias="eventId")
    source: EventSource
    ticker: str
    event_timestamp: datetime = Field(..., alias="eventTimestamp")
    disclosure_timestamp: Optional[datetime] = Field(None, alias="disclosureTimestamp")
    actor: Actor
    financials: Optional[Financials] = None
    content: Content
    source_url: str = Field(..., alias="sourceUrl")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z" if v.tzinfo is None else v.isoformat()
        }


class WhitelistConfig(BaseModel):
    """Whitelist configuration stored in config/whitelist.json."""
    tickers: list[str] = Field(default_factory=list)
    last_updated: Optional[datetime] = Field(None, alias="lastUpdated")

    class Config:
        populate_by_name = True


class SlidingWindow(BaseModel):
    """Sliding window for deduplication stored in snapshot/sliding_window.json."""
    events: dict[str, datetime] = Field(default_factory=dict)

    class Config:
        populate_by_name = True
