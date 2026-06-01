"""Tests for trade direction parsing."""

import pytest

from src.models.feed import ActionType
from src.utils.trading import parse_action_type


class TestParseActionType:
    def test_fmp_purchase_code(self):
        assert parse_action_type("P-Purchase") == ActionType.BUY

    def test_fmp_sale_code(self):
        assert parse_action_type("S-Sale") == ActionType.SELL

    def test_congress_purchase_word(self):
        assert parse_action_type("Purchase") == ActionType.BUY

    def test_congress_sale_word(self):
        assert parse_action_type("Sale") == ActionType.SELL

    def test_single_letter_codes(self):
        assert parse_action_type("P") == ActionType.BUY
        assert parse_action_type("S") == ActionType.SELL

    def test_acquisition_disposition_fallback(self):
        assert parse_action_type("M-Exempt", "A") == ActionType.BUY
        assert parse_action_type("M-Exempt", "D") == ActionType.SELL

    def test_unknown_defaults_to_sell(self):
        assert parse_action_type("") == ActionType.SELL
