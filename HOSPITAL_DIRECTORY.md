# Hospital directory

Patients enter their phone, country, state, and area/city during email account creation. Existing and Google sign-in users can add or update these fields on the dashboard. The directory matches the patient's country, state, and area against approved hospital registrations.

Hospitals submit their listing at `/hospitals/register`. New listings remain pending until the app administrator reviews them at `/hospitals/admin` and approves them. Set an administrator key in the PowerShell session before starting the app:

```powershell
$env:HOSPITAL_ADMIN_KEY = "choose-a-long-private-review-key"
python app.py
```

Then open `http://127.0.0.1:5000/hospitals/admin` and enter that key. Review the hospital's contact and location details before approving. Approved listings appear only for matching patient locations.

This is a user-submitted directory, so it will not automatically contain every hospital. It starts empty; hospitals must submit listings and the administrator must approve them. The patient phone number is not shown in the directory.
