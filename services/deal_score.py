
def calculate_deal(
    listing_total,
    market_value,
    seller_feedback=None,
    comparable_count=0,
    confidence_score=0,
    condition_flags=None,
    quantity=1,
):
    condition_flags = condition_flags or []

    try:
        listing_total = float(listing_total)
    except (TypeError, ValueError):
        return None, 0, "UNPRICED"

    try:
        market_value = float(market_value) if market_value is not None else None
    except (TypeError, ValueError):
        market_value = None

    try:
        seller_feedback = float(seller_feedback) if seller_feedback is not None else None
    except (TypeError, ValueError):
        seller_feedback = None

    try:
        comparable_count = int(comparable_count or 0)
    except (TypeError, ValueError):
        comparable_count = 0

    try:
        confidence_score = float(confidence_score or 0)
    except (TypeError, ValueError):
        confidence_score = 0

    try:
        quantity = int(quantity or 1)
    except (TypeError, ValueError):
        quantity = 1

    if not market_value or market_value <= 0:
        return None, 0, "UNPRICED"

    discount = ((market_value - listing_total) / market_value) * 100.0
    if abs(float(listing_total) - float(market_value)) < 0.005:
        discount = 0.0

    score = 50 + discount * 1.45

    if comparable_count >= 8:
        score += 6
    elif comparable_count >= 5:
        score += 4
    elif comparable_count >= 3:
        score += 2

    if confidence_score >= 85:
        score += 5
    elif confidence_score >= 65:
        score += 2
    else:
        score -= 10

    if seller_feedback is not None:
        if seller_feedback >= 99.5:
            score += 5
        elif seller_feedback >= 99:
            score += 3
        elif seller_feedback >= 98:
            score += 1
        elif seller_feedback < 95:
            score -= 40
        elif seller_feedback < 97:
            score -= 20

    if condition_flags:
        score -= 35
    if quantity > 1:
        score -= 15

    score = max(0, min(100, round(score)))

    if condition_flags:
        verdict = "RISK"
    elif seller_feedback is not None and seller_feedback < 95:
        verdict = "RISK"
    elif quantity > 1:
        verdict = "PASS"
    elif discount >= 25 and score >= 85:
        verdict = "BUY"
    elif discount >= 15 and score >= 72:
        verdict = "GOOD"
    elif discount >= 5 and score >= 60:
        verdict = "FAIR"
    else:
        verdict = "PASS"

    return round(discount, 1), score, verdict
