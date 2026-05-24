from config.settings import SIGNAL_THRESHOLD


def compute_signal(
    credibility_score: float,
    llm_confidence: float,
    impact_score: float,
    direction: str,
) -> dict:
    score = credibility_score * llm_confidence * impact_score

    if score >= 0.8:
        level = "STRONG"
    elif score >= SIGNAL_THRESHOLD:
        level = "MEDIUM"
    else:
        level = "NONE"

    return {
        "score": score,
        "level": level,
        "direction": direction,
    }
