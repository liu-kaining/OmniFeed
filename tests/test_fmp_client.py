"""Tests for FMP response normalization."""

from src.services.fmp_client import normalize_insider_record, normalize_news_record


class TestNormalizeInsiderRecord:
    def test_maps_stable_v4_fields(self):
        raw = {
            "symbol": "AAPL",
            "reportingName": "LEVINSON ARTHUR D",
            "transactionDate": "2021-02-02",
            "transactionType": "S-Sale",
            "securitiesTransacted": 3416,
            "price": 225.5,
            "securityName": "Common Stock",
            "acquistionOrDisposition": "D",
            "link": "https://sec.gov/example",
        }
        normalized = normalize_insider_record(raw)
        assert normalized["insiderName"] == "LEVINSON ARTHUR D"
        assert normalized["filingDate"] == "2021-02-02"
        assert normalized["transactionType"] == "S-Sale"
        assert normalized["typeOfOwner"] == "Common Stock"
        assert normalized["acquisitionOrDisposition"] == "D"


class TestNormalizeNewsRecord:
    def test_maps_stable_fields(self):
        raw = {
            "symbol": "AAPL",
            "title": "Apple rises",
            "publishedDate": "2020-09-08 09:25:00",
            "text": "Market update",
            "url": "https://example.com/news",
            "site": "seekingalpha.com",
        }
        normalized = normalize_news_record(raw)
        assert normalized["symbol"] == "AAPL"
        assert normalized["publishedDate"] == "2020-09-08 09:25:00"
        assert normalized["author"] == "seekingalpha.com"
        assert normalized["url"] == "https://example.com/news"
