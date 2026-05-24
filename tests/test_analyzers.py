import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from analyzers.keyword import analyze_keywords
from analyzers.signal import compute_signal


def test_keyword_bullish():
    result = analyze_keywords("トヨタが増配と自社株買いを発表")
    assert result["direction"] == "bullish"
    assert len(result["matched_keywords"]) >= 2
    assert result["keyword_score"] > 0

def test_keyword_bearish():
    result = analyze_keywords("企業が赤字転落し下方修正を発表")
    assert result["direction"] == "bearish"
    assert result["keyword_score"] < 0

def test_keyword_neutral():
    result = analyze_keywords("本日の天気は晴れです")
    assert result["direction"] == "neutral"
    assert result["keyword_score"] == 0.0

def test_keyword_mixed_prefers_majority():
    result = analyze_keywords("増配、自社株買い、最高益だが一部で赤字")
    assert result["direction"] == "bullish"

def test_signal_strong():
    result = compute_signal(0.9, 0.95, 0.95, "bullish")
    assert result["level"] == "STRONG"
    assert result["score"] >= 0.8

def test_signal_medium():
    result = compute_signal(0.9, 0.8, 0.85, "bearish")
    assert result["level"] in ("STRONG", "MEDIUM")

def test_signal_none():
    result = compute_signal(0.3, 0.2, 0.1, "neutral")
    assert result["level"] == "NONE"

def test_signal_direction_preserved():
    result = compute_signal(0.9, 0.9, 0.9, "bearish")
    assert result["direction"] == "bearish"
