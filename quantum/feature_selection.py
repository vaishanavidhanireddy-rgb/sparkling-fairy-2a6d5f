"""Classical preparation of candidate report features for the quantum demo."""
from collections import Counter
from ai.report_comparison import terms


def rank_shared_features(first, second, limit=8):
    """Rank overlapping words before encoding a small search problem."""
    left, right = Counter(terms(first)), Counter(terms(second))
    common = set(left) & set(right)
    ranked = sorted(common, key=lambda word: (-min(left[word], right[word]), word))
    return [{"term": word, "score": min(left[word], right[word])}
            for word in ranked[:limit]]


def select_shared_features(first, second, limit=8):
    """Keep the old classical selector available for callers that need it."""
    return [item["term"] for item in rank_shared_features(first, second, limit)]
