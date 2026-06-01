"""RSS feed generator for OmniFeed.

This module generates RSS 2.0 feeds for Congress trades and insider transactions,
following the XML structure specified in the OmniFeed specification.
"""

from datetime import datetime, timezone
from typing import Optional

from src.models.feed import EventSource, FeedEvent

# CDATA closing sequence that needs special handling
CDATA_END = "]>" + "]"
CDATA_END_ESCAPED = "]]" + ">" + "><![CDATA["


def _escape_cdata(text: str) -> str:
    """Escape text for safe inclusion in CDATA section."""
    return text.replace(CDATA_END, CDATA_END_ESCAPED)


def _format_rss_date(dt: datetime) -> str:
    """Format datetime to RSS date format (RFC 822)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


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

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>OmniFeed - 国会山政治异动追踪源</title>',
        '    <link>https://omnifeed.pages.dev</link>',
        '    <description>AI驱动的美国国会议员及其配偶最新美股交易披露流</description>',
        '    <language>zh-cn</language>',
        f'    <lastBuildDate>{_format_rss_date(build_time)}</lastBuildDate>',
    ]

    for event in sorted(events, key=lambda e: e.event_timestamp, reverse=True):
        action = event.financials.action.value if event.financials else ""
        safe_desc = _escape_cdata(_build_description(event))
        lines.extend([
            '    <item>',
            f'      <title>[🏛️国会山/{action}] {event.ticker}.US - {event.actor.name_zh}</title>',
            f'      <link>https://omnifeed.pages.dev/symbol/{event.ticker}</link>',
            f'      <guid isPermaLink="false">{event.event_id}</guid>',
            f'      <pubDate>{_format_rss_date(event.event_timestamp)}</pubDate>',
            f'      <description><![CDATA[{safe_desc}]]></description>',
            '    </item>',
        ])

    lines.extend(['  </channel>', '</rss>'])
    return '\n'.join(lines)


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

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>OmniFeed - 公司管理层内幕交易追踪源</title>',
        '    <link>https://omnifeed.pages.dev</link>',
        '    <description>AI驱动的美股上市公司高管内幕交易实时监控与智能分析流</description>',
        '    <language>zh-cn</language>',
        f'    <lastBuildDate>{_format_rss_date(build_time)}</lastBuildDate>',
    ]

    for event in sorted(events, key=lambda e: e.event_timestamp, reverse=True):
        action = event.financials.action.value if event.financials else ""
        safe_desc = _escape_cdata(_build_description(event))
        lines.extend([
            '    <item>',
            f'      <title>[💼管理层/{action}] {event.ticker}.US - {event.actor.name_zh}</title>',
            f'      <link>https://omnifeed.pages.dev/symbol/{event.ticker}</link>',
            f'      <guid isPermaLink="false">{event.event_id}</guid>',
            f'      <pubDate>{_format_rss_date(event.event_timestamp)}</pubDate>',
            f'      <description><![CDATA[{safe_desc}]]></description>',
            '    </item>',
        ])

    lines.extend(['  </channel>', '</rss>'])
    return '\n'.join(lines)
