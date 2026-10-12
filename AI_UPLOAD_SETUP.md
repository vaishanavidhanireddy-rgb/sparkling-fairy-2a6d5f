# Bilingual report upload setup

The dashboard accepts JPG, PNG, WEBP, and PDF files up to 2 MB. The app sends the uploaded file to Google's Gemini API and saves the returned English and Telugu explanation with the report. The original upload is processed in memory and is not saved by this app.

## Where to put API keys

Open the `.env` file in the project folder and paste each key after `=` with no extra spaces, for example:

```text
GROQ_API_KEY=your-actual-groq-key
GEMINI_API_KEY=your-actual-gemini-key
```

Save the file and restart the Flask app. `.env` is excluded from Git so your keys are not added to source control. Do not paste keys into chat or commit them.

Set a Gemini API key in the environment before starting the Flask app:

```powershell
# Set the Google API key in your local .env file; do not commit a real key.
python app.py
```

Create a key in [Google AI Studio](https://aistudio.google.com/app/apikey). Without this setting, photo and PDF explanations are unavailable; pasted report text and other dashboard features continue to work.

For the symptom question feature, set your Groq API key as well:

```powershell
# Set the Groq API key in your local .env file; do not commit a real key.
python app.py
```

Create a key in [Groq Console](https://console.groq.com/keys). Symptom questions are sent to Groq to generate a response and are not saved by this app.

AI explanations can misread medical documents. They are for understanding only and do not replace advice from a qualified clinician.

