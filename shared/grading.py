import re
from statistics import median

JUDGES = ("claude", "openai", "gemini")
SPREAD_LIMIT = 1
LOW_READ_CONFIDENCE = 0.6


def cap(marks, limit):
    return min(max(marks, 0), limit)


def combine(judgments, points):
    capped = [{p: cap(j.get(p, 0), points[p]) for p in points} for j in judgments]
    per_point = {p: median(c[p] for c in capped) for p in points}
    totals = [sum(c.values()) for c in capped]
    return per_point, sum(per_point.values()), max(totals) - min(totals)


def flag_reasons(spread, judges, read_confidence=None, contradicts_key=False):
    reasons = []
    if spread > SPREAD_LIMIT:
        reasons.append("judges disagree")
    if judges < len(JUDGES):
        reasons.append(f"graded by {judges} judges")
    if read_confidence is not None and read_confidence < LOW_READ_CONFIDENCE:
        reasons.append("hard to read")
    if contradicts_key:
        reasons.append("web contradicts the key")
    return reasons


def digits(value):
    return re.sub(r"\D", "", value or "")


def match_student(read_id, roster_ids):
    by_digits = {digits(r): r for r in roster_ids}
    return by_digits.get(digits(read_id)) if digits(read_id) else None
