# Healthcare - AI-Powered Personal Health Copilot

Flask-based personal report workspace. Existing SQLite accounts and reports remain in `quantum_healthcare.sqlite3`.

The dashboard also supports user-entered medicine reminders, daily water/sleep/exercise/step logs, a seven-day step view, and optional bilingual AI wellness ideas. Browser medicine reminders work only while the dashboard is open and browser notifications are allowed. Medicine names and schedules must come from the user's clinician. AI wellness ideas require a separate opt-in and send only that day's wellness values and selected focus to Groq.

The Doctor Appointments page provides dependent State → District → City/Town → Hospital → Doctor selectors. State and district options come from the Government of India's monthly [LGD States](https://www.data.gov.in/resource/local-government-directory-lgd-states) and [LGD Districts](https://www.data.gov.in/resource/local-government-directory-lgd-districts) datasets; city/town options come from [LGD Urban Local Bodies with PIN Codes](https://www.data.gov.in/resource/local-government-directory-lgd-local-bodies-pin-codes). City/town therefore means an LGD urban local body, not every village, postal locality, or informal neighborhood. Hospital listings come from the [National Hospital Directory](https://www.data.gov.in/resource/national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month). These sources do not include individual doctor names. Doctor names must be imported separately and tied to an exact hospital/state/district/city match; check registrations in the [NMC public register](https://nmr.nmc.org.in/search-doctor).

Download the LGD States, LGD Districts, LGD Urban-with-PIN, and National Hospital Directory CSVs from those Government of India pages, then place them under `data/appointments/`. The importer accepts English names and LGD codes, validates all rows before writing, associates a hospital to an LGD city only when its town name matches or its PIN identifies exactly one ULB in that district, and applies the selected imports in one transaction. It preserves existing hospitals, doctors, and requests; a geography re-import deactivates removed LGD entries without deleting them. For locality-free hospital rows, the source limitation is shown as “Locality not reported by source” rather than guessed.

To populate state, district, and city/town selectors from the attached hospital finder location lists, import the extracted data with:

```powershell
python -m scripts.import_hospital_finder_locations --input data/appointments/hospital_finder_locations.json
```

This user-provided location list is kept separate from official LGD data. The attachment's hospital records are excluded because their source is unclear; import sourced hospital records separately.

```powershell
python -m scripts.import_appointment_data `
  --states data/appointments/lgd_states.csv `
  --districts data/appointments/lgd_districts.csv `
  --geography data/appointments/lgd_urban_with_pin.csv `
  --hospitals data/appointments/national_hospital_directory.csv
```

Doctor CSV columns are `hospital_name,state,district,city,doctor_name,specialty,registration_number,verification_status,verification_url`. Each row must match one imported hospital by all four location/name fields. `verification_status=verified` is accepted only with a registration number and an HTTPS NMC URL; an admin must check that individual record manually in the [NMC National Medical Register](https://nmr.nmc.org.in/search-doctor). The app has no NMC feed for clinic affiliations, so it never guesses which hospital a doctor works at. Unchecked entries remain `unverified`.

The supplied `data/appointments/India_States_Districts_Hospitals.xlsx` workbook can also populate appointment location and hospital choices. It adds state/UT names, districts and the workbook's district-HQ/main-city values, then adds the hospital names from columns Hospital 1-3. The workbook labels many rows “Partial - verify locally” and does not provide independently verifiable sources, so every hospital imported this way is marked **unverified** in the appointment dropdown. No doctor names, addresses, phone numbers, or live availability are inferred. Existing records are preserved; matching existing hospital rows are left unchanged.

Run this once (and again after updating the workbook) from the project folder in PowerShell:

```powershell
python -m scripts.import_appointment_workbook `
  --input data/appointments/India_States_Districts_Hospitals.xlsx
```

```powershell
python -m scripts.import_appointment_data `
  --doctors data/appointments/checked_doctors.csv
```

Use `python -m scripts.import_appointment_data --help` for options. The script defaults to the existing `quantum_healthcare.sqlite3`; pass `--database` to target a separate database. Run the test suite with `python -m unittest discover -s tests` and `node --test tests/appointments_ui.test.cjs`.

Date and time choices save private **demo requests** only. They are not sent to hospitals and do not represent live appointment availability or a confirmed booking. Duplicate requests for the same user, hospital, doctor, date, and time preference are rejected.

## Run in VS Code (PowerShell terminal)

```powershell
cd "C:\Users\vaish\Desktop\healthcare AI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm.cmd install
npm.cmd run build
Copy-Item .env.example .env
python app.py
```

Open http://127.0.0.1:5000. Set a long random `SECRET_KEY` and your `GROQ_API_KEY` in `.env` before using AI features. The default Groq model is `qwen/qwen3.8-27b`; override it with `GROQ_MODEL` if needed. The app displays an explicit configuration message when the AI key is missing. Google sign-in is optional and requires the Firebase settings described in `FIREBASE_SETUP.md`.

Password reset uses a one-time link that expires after 60 minutes. To deliver reset emails, configure `PUBLIC_BASE_URL`, `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `MAIL_DEFAULT_SENDER` in `.env` with your SMTP provider's values. Without SMTP configuration the UI still responds safely, but no email can be delivered.

PDF text extraction uses pypdf. Image OCR uses the Tesseract executable; install Tesseract OCR separately and ensure `tesseract.exe` is on PATH. The AI provider may still read image or PDF files when local extraction returns no text.

Uploads are limited to 2 MB and PDF/JPG/PNG signatures are checked. Report contents and AI explanations are stored in the existing local SQLite database, scoped to the signed-in user. Keep that database private and back it up securely.

AI explanations are educational and may be wrong. They do not diagnose conditions or prescribe treatment. Discuss reports with a qualified clinician.


The interface is written in React under `frontend/src/`; Flask continues to handle sessions, forms, and database operations. Rebuild `static/react-app.js` after changing React code with `npm.cmd run build`.
