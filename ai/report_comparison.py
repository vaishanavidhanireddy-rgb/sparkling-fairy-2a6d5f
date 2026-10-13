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


def extract_measurements(first, second):
    """Return only numeric values and units explicitly present in both texts."""
    pattern = re.compile(r"(?i)([a-z][a-z0-9 /()-]{1,35}?)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(mg/dl|mmol/l|g/dl|g/l|%|bpm|mmhg|u/l|iu/l|cells/?ul|10\^\d+/l)?")
    def parse(text):
        values = {}
        for label, value, unit in pattern.findall(text):
            key = re.sub(r"\s+", " ", label.strip().lower())
            if key and len(key) < 32:
                values[key] = (float(value), unit.strip())
        return values
    a, b = parse(first), parse(second)
    result = []
    for key in sorted(a.keys() & b.keys()):
        if a[key][1].lower() != b[key][1].lower():
            continue
        scale = max(abs(a[key][0]), abs(b[key][0]), 0.0001)
        result.append({"label": key, "old": a[key][0], "new": b[key][0], "old_unit": a[key][1], "new_unit": b[key][1],
                       "old_pct": round(abs(a[key][0]) / scale * 100), "new_pct": round(abs(b[key][0]) / scale * 100)})
    return result
