# AI and report extraction setup

Add provider keys to the ignored `.env` file in the project root, then restart Flask:

```text
MISTRAL_API_KEY=your-mistral-api-key
MISTRAL_MODEL=ministral-14b-latest
SECRET_KEY=your-long-random-secret
```

`MISTRAL_API_KEY` powers report explanations, bilingual health questions, and optional wellness ideas. `MISTRAL_MODEL` defaults to `ministral-14b-latest`; set it to a model ID available to your Mistral API account if needed. Wellness ideas require a checkbox confirmation and send only the day's self-entered wellness values and focus. When a key is missing, the page displays the required setup message. Do not commit `.env` or place API keys in browser code. Image reports are sent as base64 image data; PDFs use locally extracted text, so scanned PDFs need local OCR to be configured.

Report uploads are saved privately first. Open the saved report from its detail page and choose **Explain this report in English and Telugu** when ready. The selected report file is retained in the private SQLite database so the AI can read it after saving. Older saved reports without retained file data can be explained from extracted text when available.

## Hospital directory and appointment requests

Set `HOSPITAL_ADMIN_EMAILS` in `.env` to the email address(es) allowed to upload directory records. Separate multiple addresses with commas, then restart Flask. The matching signed-in account sees the admin-only import tools on Doctor Appointments. Download a hospital CSV from the [Government of India Open Data hospital directory](https://www.data.gov.in/resource/national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month) and upload it directly. Imports retain a source label and import timestamp. The selectors are populated only from imported records; this is not a live directory and you should confirm contact and location details before travel. Admin-verified entries may also be uploaded with the supplied hospital template (`hospital_name,state,district,city,area`; `address,phone` optional).

The government hospital file does not supply individual doctor names. Optional doctor records use the supplied doctor CSV template (`hospital_name,state,district,city,doctor_name`; `specialty,registration_number` optional), must match an imported hospital, and are always labeled unverified. Check the [NMC public doctor register](https://nmr.nmc.org.in/search-doctor). The app does not call an NMC API.

Date and time selections create a private demo request only. No appointment is transmitted and no live availability is checked. Identical user/hospital/doctor/date/time preference requests are prevented by a database uniqueness key.

Appointment requests are saved privately under the signed-in user's account. This starter app does not transmit requests or notify hospitals, so users must call the listed number to confirm availability. Do not upload hospital data unless you have permission to publish it.

PDFs use pypdf for embedded text extraction. Scanned PDFs and JPG/PNG images are also sent to the configured AI vision provider. Local image OCR uses Tesseract if installed; install its Windows executable and make sure it is on PATH.

AI can misread reports. It should only describe visible values and ranges, must not diagnose or prescribe, and cannot replace a qualified clinician.
