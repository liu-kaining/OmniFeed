"""RSS feed generator for OmniFeed.

This module generates RSS 2.0 feeds for Congress trades and insider transactions,
following the XML structure specified in the OmniFeed specification.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from xml.dom import minidom

from src.models.feed import EventSource, FeedEvent


def _format_rss_date(dt: datetime) -> str:
    """Format datetime to RSS date format (RFC 822)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _create_item_element(event: FeedEvent) -> ET.Element:
    """Create an RSS item element from a FeedEvent."""
    item = ET.SubElement(ET.Element("dummy"), "item")

    # Title with source emoji and action
    emoji = {
        EventSource.CONGRESS: "🏛️国会山",
        EventSource.INSIDER: "💼管理层",
        EventSource.ARTICLE: "📰舆情",
    }.get(event.source, "")

    action = ""
    if event.financials:
        action = f"/{event.financials.action.value}"

    title_text = f"[{emoji}{action}] {event.ticker}.US - {event.actor.name_zh}"

    if event.source == EventSource.ARTICLE:
        title_text = f"[📰舆情] {event.content.title_zh[:50]}..."

    title = ET.SubElement(item, "title")
    title.text = title_text

    # Link
    link = ET.SubElement(item, "link")
    link.text = f"https://omnifeed.pages.dev/symbol/{event.ticker}"

    # GUID
    guid = ET.SubElement(item, "guid")
    guid.set("isPermaLink", "false")
    guid.text = event.event_id

    # Publication date
    pub_date = ET.SubElement(item, "pubDate")
    pub_date.text = _format_rss_date(event.event_timestamp)

    # Description with CDATA
    description = ET.SubElement(item, "description")
    description_text = _build_description(event)
    description.text = description_text

    return item


def _build_description(event: FeedEvent) -> str:
    """Build HTML description for RSS item."""
    parts = []

    if event.source == EventSource.CONGRESS:
        parts.append(f"<p><strong>交易议员：</strong>{event.actor.name_zh} ({event.actor.identity_zh})</p>")
        if event.financials and event.financials.value_range:
            parts.append(f"<p><strong>披露金额：</strong>{event.financials.value_range}</p>")
        parts.append(f"<p><strong>🤖 AI 深度简评：</strong>{event.content.body_zh}</p>")

    elif event.source == EventSource.INSIDER:
        parts.append(f"<p><strong>内部人：</strong>{event.actor.name_zh} ({event.actor.identity_zh})</p>")
        if event.financials:
            action_emoji = "🟢" if event.financials.action.value == "BUY" else "🔴"
            parts.append(
                f"<p><strong>{action_emoji} 交易：</strong>"
                f"{event.financials.action.value} "
                f"{event.financials.volume:,.0f}股 @ ${event.financials.price:,.2f}</p>"
            )
        parts.append(f"<p><strong>分析：</strong>{event.content.body_zh}</p>")

    else:  # ARTICLE
        parts.append(f"<p><strong>来源：</strong>{event.content.title_en}</p>")
        parts.append(f"<p><strong>摘要：</strong>{event.content.body_zh}</p>")

    return "\n".join(parts)


def generate_congress_rss(events: list[FeedEvent], build_time: Optional[datetime] = None) -> str:
    """Generate RSS feed for Congress trades.

    Args:
        events: List of Congress trade events.
        build_time: Build timestamp for the feed.

    Returns:
        XML string of the RSS feed.
    """
    if build_time is None:
        build_time = datetime.now(timezone.utc)

    rss = ET.Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = ET.SubElement(rss, "channel")

    title = ET.SubElement(channel, "title")
    title.text = "OmniFeed - 国会山政治异动追踪源"

    link = ET.SubElement(channel, "link")
    link.text = "https://omnifeed.pages.dev"

    description = ET.SubElement(channel, "description")
    description.text = "AI驱动的美国国会议员及其配偶最新美股交易披露流"

    language = ET.SubElement(channel, "language")
    language.text = "zh-cn"

    last_build = ET.SubElement(channel, "lastBuildDate")
    last_build.text = _format_rss_date(build_time)

    # Add items (most recent first)
    for event in sorted(events, key=lambda e: e.event_timestamp, reverse=True):
        item = _create_item_element(event)
        channel.append(item)

    # Pretty print
    rough_string = ET.tostring(rss, encoding="unicode", xml_declaration=True)
    parsed = minidom.parseString(rough_string)
    return parsed.toprettyxml(indent="  ", encoding=None)


def generate_insider_rss(events: list[FeedEvent], build_time: Optional[datetime] = None) -> str:
    """Generate RSS feed for insider transactions.

    Args:
        events: List of insider transaction events.
        build_time: Build timestamp for the feed.

    Returns:
        XML string of the RSS feed.
    """
    if build_time is None:
        build_time = datetime.now(timezone.utc)

    rss = ET.Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = ET.SubElement(rss, "channel")

    title = ET.SubElement(channel, "title")
    title.text = "OmniFeed - 公司管理层内幕交易追踪源"

    link = ET.SubElement(channel, "link")
    link.text = "https://omnifeed.pages.dev"

    description = ET.SubElement(channel, "description")
    description.text = "AI驱动的美股上市公司高管内幕交易实时监控与智能分析流"

    language = ET.SubElement(channel, "language")
    language.text = "zh-cn"

    last_build = ET.SubElement(channel, "lastBuildDate")
    last_build.text = _format_rss_date(build_time)

    # Add items (most recent first)
    for event in sorted(events, key=lambda e: e.event_timestamp, reverse=True):
        item = _create_item_element(event)
        channel.append(item)

    # Pretty print
    rough_string = ET.tostring(rss, encoding="unicode", xml_declaration=True)
    parsed = minidom.parseString(rough_string)
    return parsed.toprettyxml(indent="  ", encoding=None)
