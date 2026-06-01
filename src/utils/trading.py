"""Shared helpers for parsing trade direction from heterogeneous data sources."""

from src.models.feed import ActionType


def parse_action_type(
    tx_type: str,
    acquisition_or_disposition: str | None = None,
) -> ActionType:
    """Infer BUY/SELL from transaction type strings across FMP, Quiver, Capitol Trades."""
    normalized = (tx_type or "").strip().upper()

    if normalized in ("P", "PURCHASE", "BUY"):
        return ActionType.BUY
    if normalized in ("S", "SALE", "SELL"):
        return ActionType.SELL
    if normalized.startswith("P-"):
        return ActionType.BUY
    if normalized.startswith("S-"):
        return ActionType.SELL
    if "PURCH" in normalized:
        return ActionType.BUY
    if "SALE" in normalized:
        return ActionType.SELL

    if acquisition_or_disposition:
        return (
            ActionType.BUY
            if acquisition_or_disposition.strip().upper() == "A"
            else ActionType.SELL
        )

    return ActionType.SELL
