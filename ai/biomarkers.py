"""Conservatively extract numeric lab results with explicit reference ranges."""
import re

NUMBER = r"[-+]?\d+(?:\.\d+)?"
RESULT_LINE = re.compile(
    rf"^\s*(?P<name>[A-Za-z][A-Za-z0-9 ()/_-]{{1,48}}?)\s*[:=]?\s*"
    rf"(?P<value>{NUMBER})\s*(?P<unit>[A-Za-z\u00b5\u03bc/%^0-9._-]{{0,18}})\s*"
    rf"(?:\(?\s*(?:ref(?:erence)?(?: range)?\s*[:=]?\s*)?"
    rf"(?P<range>(?:{NUMBER}\s*(?:-|\u2013|to)\s*{NUMBER}|[<>\u2264\u2265]\s*{NUMBER}))\s*\)?)\s*$",
    re.IGNORECASE,
)
RANGE_NUMBERS = re.compile(NUMBER)


def parse_range(value):
    """Return an inclusive numeric range from an explicit interval or bound."""
    value = (value or "").strip()
    if value.startswith(("<", "\u2264")):
        numbers = RANGE_NUMBERS.findall(value)
        return (None, float(numbers[0]), value.startswith("\u2264")) if numbers else None
    if value.startswith((">", "\u2265")):
        numbers = RANGE_NUMBERS.findall(value)
        return (float(numbers[0]), None, value.startswith("\u2265")) if numbers else None
    numbers = RANGE_NUMBERS.findall(value)
    if len(numbers) != 2:
        return None
    lower, upper = map(float, numbers)
    return (min(lower, upper), max(lower, upper), True)


def extract_biomarkers(reports):
    """Extract report lines that contain both a result and its printed range."""
    measurements = []
    for report in reports:
        text = report["content"] if hasattr(report, "keys") else report.get("content", "")
        report_id = report["id"] if hasattr(report, "keys") else report.get("id")
        title = report["title"] if hasattr(report, "keys") else report.get("title", "Report")
        created_at = report["created_at"] if hasattr(report, "keys") else report.get("created_at", "")
        for line in (text or "").splitlines():
            match = RESULT_LINE.match(line)
            if not match:
                continue
            bounds = parse_range(match.group("range"))
            if not bounds:
                continue
            value = float(match.group("value"))
            lower, upper, inclusive = bounds
            low_out = lower is not None and (value < lower if inclusive else value <= lower)
            high_out = upper is not None and (value > upper if inclusive else value >= upper)
            measurements.append({
                "report_id": report_id,
                "report_title": title,
                "date": (created_at or "")[:10],
                "name": " ".join(match.group("name").split()).strip(" :-"),
                "value": value,
                "unit": match.group("unit").strip(),
                "reference_range": match.group("range").strip(),
                "abnormal": low_out or high_out,
            })
    return measurements
