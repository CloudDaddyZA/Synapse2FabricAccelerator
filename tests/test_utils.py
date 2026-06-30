"""Tests for shared utilities (scoring, config, retry)."""
from src.models.enums import RiskLevel
from src.utils.config import load_settings
from src.utils.retry import with_retry
from src.utils.scoring import aggregate_band, score_to_level, weighted_score


def test_risk_from_score():
    assert RiskLevel.from_score(80) == RiskLevel.CRITICAL
    assert RiskLevel.from_score(60) == RiskLevel.HIGH
    assert RiskLevel.from_score(30) == RiskLevel.MEDIUM
    assert RiskLevel.from_score(5) == RiskLevel.LOW


def test_weighted_and_band():
    assert weighted_score({"a": 50, "b": 60}) == 100
    assert score_to_level(0) == RiskLevel.LOW
    assert aggregate_band([RiskLevel.LOW, RiskLevel.CRITICAL]) == RiskLevel.CRITICAL
    assert aggregate_band([]) == RiskLevel.LOW


def test_retry_succeeds(tmp_path):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("transient")
        return "ok"

    assert with_retry(flaky, max_attempts=3, backoff_seconds=0) == "ok"


def test_load_settings_defaults():
    s = load_settings("nonexistent.yaml")
    assert s.output_path == "output"
    assert s.include_html_dashboard is True
