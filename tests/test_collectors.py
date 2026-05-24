import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from collectors.credibility import source_score, consistency_score, calculate_credibility


def test_source_score_tdnet():
    assert source_score("tdnet") == 0.9

def test_source_score_unknown():
    assert source_score("unknown_source") == 0.3

def test_consistency_score_no_match():
    item = {"title": "トヨタが増配発表"}
    assert consistency_score(item, []) == 0.0

def test_consistency_score_match():
    item = {"title": "トヨタが増配発表"}
    seen = ["トヨタが増配発表", "別のニュース"]
    assert consistency_score(item, seen) == 0.1

def test_calculate_credibility_reliable():
    item = {"title": "テスト", "source": "tdnet", "credibility": 0.9}
    result = calculate_credibility(item, [])
    assert result["is_reliable"] is True
    assert 0.0 <= result["credibility"] <= 1.0

def test_calculate_credibility_unreliable():
    item = {"title": "テスト", "source": "unknown_source", "credibility": 0.3}
    result = calculate_credibility(item, [])
    assert result["is_reliable"] is False
