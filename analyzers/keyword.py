BULLISH_KEYWORDS = ["増配", "自社株買い", "上方修正", "最高益", "買収", "黒字転換", "特別配当", "業績上方修正", "増益", "新高値"]
BEARISH_KEYWORDS = ["減配", "下方修正", "赤字", "リコール", "破綻", "不正", "損失", "訴訟", "業績下方修正", "減益"]


def analyze_keywords(text: str) -> dict:
    bullish_matched = [kw for kw in BULLISH_KEYWORDS if kw in text]
    bearish_matched = [kw for kw in BEARISH_KEYWORDS if kw in text]
    matched = bullish_matched + bearish_matched

    b = len(bullish_matched)
    be = len(bearish_matched)
    total = b + be

    if total == 0:
        direction = "neutral"
        keyword_score = 0.0
    elif b > be:
        direction = "bullish"
        keyword_score = b / total
    elif be > b:
        direction = "bearish"
        keyword_score = -(be / total)
    else:
        direction = "neutral"
        keyword_score = 0.0

    return {
        "matched_keywords": matched,
        "direction": direction,
        "keyword_score": keyword_score,
    }
