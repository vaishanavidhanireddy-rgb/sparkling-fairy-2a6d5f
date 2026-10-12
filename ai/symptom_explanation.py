"""Generate cautious, bilingual plain-language symptom information with Groq."""
import json
from pathlib import Path
import urllib.error
import urllib.request


SYSTEM_PROMPT = """You provide general health information, not medical care. Reply in two sections,
English and Telugu, with friendly, simple language. Acknowledge the symptom without frightening
the person. Explain a few common possible causes as possibilities only; never diagnose, prescribe,
or claim certainty. Give safe, general self-care only when appropriate, and say when to contact a
clinician. Mention emergency help for severe or sudden symptoms, trouble breathing, chest pain,
fainting, severe bleeding, or signs of stroke. Ask at most two useful follow-up questions. Do not
ask for names, addresses, or other identifying details. Clearly state that this is AI information,
not a diagnosis, and a clinician should be consulted for personal medical advice. Use accurate,
natural Telugu in the Telugu section."""


def read_local_groq_key(project_root):
    """Read GROQ_API_KEY from .env as a fallback for servers started before key setup."""
    env_file = Path(project_root) / ".env"
    if not env_file.is_file():
        return ""
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("GROQ_API_KEY="):
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return ""


def explain_symptom(symptom, api_key, model="llama-3.3-70b-versatile"):
    if not api_key:
        raise RuntimeError("Symptom explanations need GROQ_API_KEY. See AI_UPLOAD_SETUP.md.")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Explain this symptom in English and Telugu: {symptom}"},
        ],
        "temperature": 0.3,
        "max_tokens": 1200,
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Groq could not create an explanation. Check GROQ_API_KEY and try again.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("The AI service is unavailable right now. Please try again.") from exc
    try:
        answer = result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        answer = ""
    if not answer:
        raise RuntimeError("AI did not return an explanation. Please try again.")
    return answer
