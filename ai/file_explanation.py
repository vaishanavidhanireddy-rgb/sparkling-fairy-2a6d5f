"""Bilingual, plain-language explanations for uploaded health reports."""
import base64
import json
import urllib.error
import urllib.request


PROMPT = """Read the uploaded medical report or image and explain only what is clearly visible.
Return two clearly labeled sections: English and తెలుగు. In each section use simple language,
describe the document and its key findings/values, explain medical terms, and say when a value's
reference range or context is missing. Do not diagnose, prescribe, infer unseen information, or
state that a finding is normal/abnormal unless the report itself supplies a reference range and
the comparison is clear. If unreadable or not a medical report, say so. End both sections with:
This is an AI explanation for understanding only, not a diagnosis; ask a qualified doctor.
తెలుగు: ఇది అర్థం చేసుకోవడానికి మాత్రమే ఇచ్చిన AI వివరణ; నిర్ధారణ కాదు. వైద్యుడిని సంప్రదించండి."""


def explain_upload(data, mime_type, api_key, model="gemini-2.5-flash"):
    """Send an in-memory file to Gemini and return its bilingual explanation."""
    if not api_key:
        raise RuntimeError("AI explanations are not configured. Set GEMINI_API_KEY to enable uploads.")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")}},
        ]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1800},
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("AI could not read this file. Check the Gemini API key and try again.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("AI service is unavailable right now. Please try again.") from exc
    try:
        explanation = "".join(
            part.get("text", "")
            for part in result["candidates"][0]["content"]["parts"]
            if "text" in part
        ).strip()
    except (KeyError, IndexError, TypeError):
        explanation = ""
    if not explanation:
        raise RuntimeError("AI did not return an explanation. Please try a clearer file.")
    return explanation
