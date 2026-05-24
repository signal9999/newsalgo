_SOURCE_SCORES: dict[str, float] = {
    "tdnet":        0.9,
    "nikkei":       0.7,
    "nhk":          0.7,
    "nhk_top":      0.7,
    "nhk_economy":  0.75,
    "reuters_jp":   0.75,
    "yahoo_biz":    0.65,
    "x_stub":       0.3,
    "macro_calendar": 0.8,
}


def source_score(source: str) -> float:
    return _SOURCE_SCORES.get(source, 0.3)


def consistency_score(item: dict, seen_titles: list) -> float:
    title = item.get("title", "")
    if not title:
        return 0.0
    matches = sum(1 for t in seen_titles if t == title)
    return 0.1 if matches >= 1 else 0.0


def calculate_credibility(item: dict, seen_titles: list = []) -> dict:
    score = source_score(item.get("source", ""))
    score += consistency_score(item, seen_titles)
    score = max(0.0, min(1.0, score))

    result = {**item, "credibility": score, "is_reliable": score >= 0.7}
    return result
