"""Lightweight scoring engine mapping signal counts to risk bands."""
from __future__ import annotations

from ..models.enums import RiskLevel


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def score_to_level(score: int) -> RiskLevel:
    """Map a 0-100 score to a risk band."""
    return RiskLevel.from_score(clamp(score))


def weighted_score(signals: dict[str, int]) -> int:
    """Sum weighted signal contributions into a 0-100 score.

    ``signals`` maps a label -> point contribution. Caller decides weights.
    """
    return clamp(sum(signals.values()))


def aggregate_band(levels: list[RiskLevel]) -> RiskLevel:
    """Return the highest band across a set of levels (empty -> Low)."""
    if not levels:
        return RiskLevel.LOW
    return max(levels, key=lambda lvl: lvl.weight)
