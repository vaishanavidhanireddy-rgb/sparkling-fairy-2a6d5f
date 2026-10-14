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

Open http://127.0.0.1:5000. Set a long random `SECRET_KEY` and `NVIDIA_NIM_API_KEY` in `.env`. AI features use NVIDIA NIM with `meta/llama-3.2-11b-vision-instruct` by default; choose another supported model with `NVIDIA_NIM_MODEL` if needed. Google sign-in is optional: set the Firebase web configuration values shown in `.env.example` to enable it.

PDF text extraction uses pypdf. Image OCR uses the Tesseract executable; install Tesseract OCR separately and ensure `tesseract.exe` is on PATH. The AI provider may still read image or PDF files when local extraction returns no text.

Uploads are limited to 2 MB and PDF/JPG/PNG file signatures are checked. When `DATABASE_URL` is set, account records, reports, and app data use PostgreSQL; without it, local development uses `quantum_healthcare.sqlite3`. Keep database credentials private and configure backups and appropriate privacy/security controls before storing real patient records.

AI explanations are educational and may be wrong. They do not diagnose conditions or prescribe treatment. Discuss reports with a qualified clinician.

## Deploy to Vercel and Render

Deploy both services from the same repository and branch. The repository root is the directory containing `healthcare.py`, `package.json`, and `render.yaml`.

### Vercel frontend

Import the GitHub repository into Vercel and set **Root Directory** to the repository root. Use:

- Framework preset: **Vite**
- Build command: `npm run build`
- Output directory: `dist`

Vercel proxies all application pages, assets, login, and API routes to `https://healthcare-backend-0s3d.onrender.com` using `vercel.json`. If Render gives the backend a different URL, update both rewrite destinations in `vercel.json` and redeploy Vercel.

### Render backend

Create/sync a Render Blueprint from `render.yaml`, connected to the correct GitHub repository and `main` branch. Confirm the service root is the repository root and that the build and start commands are:

```text
pip install -r requirements.txt && npm ci && npm run build
gunicorn healthcare:app
```

Create a Supabase project, then add the project's PostgreSQL connection string to Render as the `DATABASE_URL` secret. Use Supabase's **Session pooler** connection string for a long-running Render web service; require SSL and do not use the Supabase anon key or service-role key as the database password. Keep this value in Render's environment settings and never commit it. The app creates and migrates its tables on startup. The production database starts empty, so register accounts again on the deployed app; local SQLite accounts are not copied.

Add your NVIDIA NIM API key to Render as the `NVIDIA_NIM_API_KEY` secret. The default model is `meta/llama-3.2-11b-vision-instruct`; Set `NVIDIA_NIM_MODEL` to a currently listed vision-capable model; update the Render value and redeploy if it is already set. Never put the API key in source control or frontend variables.

Wait for Render to report a successful deployment. Open the backend's base URL, such as `https://healthcare-backend-0s3d.onrender.com/`. The base URL should show the Healthcare page and `/assets/app.js` should load successfully. Vercel proxies all paths to this Render app.

### Sign-in errors: what they mean

| What you see | Meaning and next step |
|---|---|
| Opening `/login` directly | Redirects to the login form at `/account#login`; submit credentials on that form. |
| Submitting login or registration returns `404` | A Vercel proxy destination is wrong, or the Render service is not serving this Flask app. Check the destinations in `vercel.json`, then check the Render service's **Events** and **Logs**. |
| The Render base URL itself shows `404 Not Found` | The configured Render URL/service does not currently serve this Flask app. Confirm the service is deployed from this repository's root and `main` branch. A Vercel log page cannot diagnose Render startup failures. |
| The form says `Invalid email or password.` | The backend received the request, but that email/password pair is not in its current database. Check spelling/password and whether registration completed on this same deployed backend. Passwords are case-sensitive. |
| Registration says the account could not be created | The email may already exist, or the backend database write failed. Check Render logs; do not assume account creation succeeded unless the form redirects to the dashboard. |
| Login succeeds but the dashboard fails to load | Check the Render deployment logs and confirm the frontend assets were built (`npm ci && npm run build`). |
| Account works, then disappears after a redeploy/restart | If `DATABASE_URL` is not configured, Render may use ephemeral local SQLite storage. Set the Supabase PostgreSQL connection string in Render and redeploy. |

After deployment, register with a password of at least 10 characters containing uppercase and lowercase letters, a number, and a symbol; an international phone number such as `+919876543210`; and the required country, state, and area. Confirm the Vercel URL reaches `/welcome`, log out, then submit the login form with the same email and password. Do not use real patient information with the current non-persistent deployment.

## Validation

Build the frontend with `npm.cmd run build` on Windows or `npm run build` on Linux/macOS. Check Python syntax with `python -m compileall -q healthcare.py routes database ai`. This repository checkout currently contains no automated `tests/` suite, so the test commands from older versions of this README are not available.
