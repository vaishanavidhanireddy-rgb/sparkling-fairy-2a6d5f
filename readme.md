# Healthcare - AI-Powered Personal Health Copilot

This project is a Flask application with a React/Vite interface. Flask handles accounts, sessions, reports, and database operations. The Vite frontend is built from `src/main.jsx`; its production assets are written to `dist/`.

The dashboard includes private report uploads, optional AI explanations, medication reminders, wellness logs, and an appointment directory. AI-generated content is educational only; it does not diagnose conditions or replace advice from a qualified clinician. Medicine names and schedules must come from the user's clinician. Browser medication reminders work only while the dashboard is open and browser notifications are allowed.

## Appointment directory status

The appointment page supports state, district, city/town, hospital, and doctor selection. However, this repository checkout does **not** include the location-import scripts or the source datasets, so the state/district/city selectors may be empty until the corresponding database tables are populated. The CSV upload tools in the signed-in appointment page are only available to addresses configured in `HOSPITAL_ADMIN_EMAILS`; they upload hospital and doctor records, not the missing geographic state/district/city data.

Hospital listings are not live availability. Doctor names are not supplied by the Government of India's [National Hospital Directory](https://www.data.gov.in/resource/national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month). Doctor CSV rows must match an existing hospital by `hospital_name,state,district,city`. The doctor CSV template is available from the admin tools. Imported doctor records are marked unverified; check registrations in the [NMC public register](https://nmr.nmc.org.in/search-doctor). Date/time submissions save **demo requests only**; they are not sent to a hospital and do not confirm an appointment.

## Run in VS Code (PowerShell terminal)

```powershell
cd "C:\path\to\healthcare AI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm.cmd install
npm.cmd run build
Copy-Item .env.example .env
python healthcare.py
```

Open http://127.0.0.1:5000. Set a long random `SECRET_KEY` in `.env`. AI features require `MISTRAL_API_KEY`; the default model is `ministral-14b-latest` and can be changed with `MISTRAL_MODEL`. Google sign-in is optional: set the Firebase web configuration values shown in `.env.example` to enable it.

PDF text extraction uses pypdf. Image OCR uses the Tesseract executable; install Tesseract OCR separately and ensure `tesseract.exe` is on PATH. The AI provider may still read image or PDF files when local extraction returns no text.

Uploads are limited to 2 MB and PDF/JPG/PNG file signatures are checked. Report contents, account records, and AI explanations are stored in the local SQLite database at `quantum_healthcare.sqlite3`, scoped to the signed-in account. Keep this database private and back it up securely. The Render configuration does not attach persistent storage; data saved to its local SQLite file may be lost when the service restarts or is redeployed. Do not use this deployment for real patient records until persistent storage and appropriate privacy/security controls are configured.

AI explanations are educational and may be wrong. They do not diagnose conditions or prescribe treatment. Discuss reports with a qualified clinician.

## Deploy to Vercel and Render

Deploy both services from the same repository and branch. The repository root is the directory containing `healthcare.py`, `package.json`, and `render.yaml`.

### Vercel frontend

Import the GitHub repository into Vercel and set **Root Directory** to the repository root. Use:

- Framework preset: **Vite**
- Build command: `npm run build`
- Output directory: `dist`

The frontend defaults to `https://healthcare-backend.onrender.com` as its Flask URL. If Render gives the backend a different URL, set `VITE_BACKEND_URL` to that URL (no trailing slash) in the Vercel project's **Production** environment variables and redeploy.

### Render backend

Create/sync a Render Blueprint from `render.yaml`, connected to the correct GitHub repository and `main` branch. Confirm the service root is the repository root and that the build and start commands are:

```text
pip install -r requirements.txt && npm ci && npm run build
gunicorn healthcare:app
```

Wait for Render to report a successful deployment. Open the backend's base URL, such as `https://healthcare-backend.onrender.com/`. The base URL should show the Healthcare page. Registration and login forms submitted from the Vercel frontend navigate to the Flask backend, where the authenticated dashboard is served.

### Sign-in errors: what they mean

| What you see | Meaning and next step |
|---|---|
| Opening `/login` directly shows `404 Not Found` | Expected for a direct browser visit: the login route accepts a form `POST`, not a page `GET`. Test by submitting the login form on the Vercel page. |
| Submitting login or registration returns `404` | The backend URL is wrong, or the Render service is not serving this Flask app. Confirm the Vercel `VITE_BACKEND_URL`; then check the Render service's **Events** and **Logs**. |
| The Render base URL itself shows `404 Not Found` | The configured Render URL/service does not currently serve this Flask app. Confirm the service is deployed from this repository's root and `main` branch. A Vercel log page cannot diagnose Render startup failures. |
| The form says `Invalid email or password.` | The backend received the request, but that email/password pair is not in its current database. Check spelling/password and whether registration completed on this same deployed backend. Passwords are case-sensitive. |
| Registration says the account could not be created | The email may already exist, or the backend database write failed. Check Render logs; do not assume account creation succeeded unless the form redirects to the dashboard. |
| Login succeeds but the dashboard fails to load | Check the Render deployment logs and confirm the frontend assets were built (`npm ci && npm run build`). |
| Account works, then disappears after a redeploy/restart | Expected risk with the current Render setup: SQLite is stored on the instance and no persistent disk/database is configured. Add persistent storage before relying on accounts or records. |

After deployment, register with a valid email, a password of at least 10 characters, an international phone number such as `+919876543210`, and the required country, state, and area. Confirm it reaches `/dashboard`, log out, then submit the login form with the same email and password. Do not use real patient information with the current non-persistent deployment.

## Validation

Build the frontend with `npm.cmd run build` on Windows or `npm run build` on Linux/macOS. Check Python syntax with `python -m compileall -q healthcare.py routes database ai`. This repository checkout currently contains no automated `tests/` suite, so the test commands from older versions of this README are not available.
