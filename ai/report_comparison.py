"""A transparent, rule-based text comparison for prototype reports."""
import re
from collections import Counter

STOP_WORDS = {"the", "and", "for", "with", "from", "this", "that", "was", "were", "are", "is", "to", "of", "in", "on", "a", "an"}


def terms(text):
    return [word for word in re.findall(r"[a-zA-Z]{3,}", text.lower()) if word not in STOP_WORDS]


def compare_reports(first, second):
    left, right = Counter(terms(first)), Counter(terms(second))
    common = sorted(set(left) & set(right))
    union = set(left) | set(right)
    score = round(100 * len(common) / len(union)) if union else 0
    return {"similarity": score, "shared_terms": common[:12],
            "note": "Text overlap only; this is not clinical interpretation."}
