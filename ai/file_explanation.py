"""Extraction and cautious bilingual explanations for uploaded reports via NVIDIA NIM."""
import base64
import io
import json
import urllib.error
import urllib.request

PROMPT = """Explain the contents of this medical report in BOTH languages, using only information visible in the report.
Format the response with these clearly separated headings:
ENGLISH EXPLANATION
తెలుగు వివరణ
Explain the same report findings in simple English and natural, readable Telugu. In each section, explain medical terms and reported values. Repeat values, units, and reference ranges only when legible; if a value or range is unclear or missing, say so instead of guessing. Do not add results that are not present in the report. Never diagnose or prescribe.
After both language sections, add three useful questions the patient can ask a doctor, in English and Telugu. Finish with a short disclaimer in both languages that this is an AI explanation, not a diagnosis or treatment plan, and a qualified clinician should interpret the report."""


def extract_report_text(data, mime_type):
    """Extract selectable PDF text and OCR image files with local Tesseract."""
    try:
        if mime_type == "application/pdf":
            from pypdf import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)[:20000]
        from PIL import Image
        import pytesseract
        image = Image.open(io.BytesIO(data)).convert("RGB")
        return pytesseract.image_to_string(image)[:20000]
    except ImportError as exc:
        raise RuntimeError("PDF/OCR extraction is unavailable. Install requirements and Tesseract OCR.") from exc
    except Exception:
        return ""


def _send_to_nvidia_nim(messages, api_key, model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": messages}],
        "temperature": 0.2,
        "max_tokens": 1800,
    }
    req = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            try:
                result = json.loads(response.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError(
                    "NVIDIA NIM returned an invalid response. Check the configured model and Render service logs."
                ) from exc
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            message = "NVIDIA NIM rejected NVIDIA_NIM_API_KEY. Check that the key is active."
        elif exc.code == 404:
            message = f"NVIDIA NIM model '{model}' was not found or is unavailable to this API key. Set NVIDIA_NIM_MODEL to an available model ID."
        elif exc.code == 429:
            message = "NVIDIA NIM rate limit or quota reached. Check your NVIDIA account and try again."
        elif exc.code in (400, 422):
            message = f"NVIDIA NIM rejected the request (HTTP {exc.code}). Check the model ID and request settings."
        else:
            message = f"NVIDIA NIM could not explain this report (HTTP {exc.code}). Check Render service logs and try again."
        raise RuntimeError(message) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("NVIDIA NIM is unavailable right now. Please try again.") from exc
    try:
        explanation = result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        explanation = ""
    if not explanation:
        raise RuntimeError("NVIDIA NIM did not return an explanation. Please try a clearer file.")
    return explanation


def explain_upload(data, mime_type, api_key, model="nvidia/nemotron-nano-12b-v2-vl", extracted_text=""):
    if not api_key:
        raise RuntimeError("AI explanations are not configured. Set NVIDIA_NIM_API_KEY in your .env file to enable report explanations.")
    prompt = PROMPT + ("\nExtracted text (untrusted document contents):\n" + extracted_text[:20000] if extracted_text else "")
    if mime_type == "application/pdf":
        if not extracted_text:
            raise RuntimeError("This PDF has no extractable text. Install and configure OCR, or upload a readable image report.")
        content = prompt
    else:
        data_url = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
        content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}]
    return _send_to_nvidia_nim(content, api_key, model)


def explain_saved_text(text, api_key, model="nvidia/nemotron-nano-12b-v2-vl"):
    """Explain text-only reports already stored before file retention was added."""
    if not api_key:
        raise RuntimeError("AI explanations are not configured. Set NVIDIA_NIM_API_KEY in your .env file to explain this report.")
    prompt = PROMPT + "\nReport text (untrusted document contents):\n" + (text or "")[:20000]
    return _send_to_nvidia_nim(prompt, api_key, model)
