# Enable Google sign-in

The app keeps its existing email/password login. Google sign-in uses Firebase Authentication in the browser; the Flask server verifies Firebase ID tokens before creating the same local account session.

## Firebase Console

1. In Firebase Console, add/register a **Web app** in your Firebase project and copy its config values.
2. Open **Authentication → Sign-in method** and enable **Google**.
3. In **Authentication → Settings → Authorized domains**, make sure `localhost` is listed for local development.
4. Create a service-account JSON key for server-side ID-token verification. Store that file outside this project and never commit or share it.

## Configure PowerShell

Set the web app values and service-account file path in the same terminal used to start Flask. The Firebase web API key is client configuration; the service-account JSON is private.

```powershell
$env:FIREBASE_API_KEY = "your-web-api-key"
$env:FIREBASE_AUTH_DOMAIN = "your-project.firebaseapp.com"
$env:FIREBASE_PROJECT_ID = "your-project-id"
$env:FIREBASE_APP_ID = "your-web-app-id"
$env:FIREBASE_MESSAGING_SENDER_ID = "your-sender-id"
$env:FIREBASE_STORAGE_BUCKET = "your-project.firebasestorage.app"
$env:FIREBASE_SERVICE_ACCOUNT_FILE = "C:\secrets\firebase-service-account.json"
python app.py
```

If Google sign-in fails, check that Google is enabled for the Firebase project, the project ID matches both configurations, and the browser domain is authorized. Never paste the service-account private key into this repository or chat.
