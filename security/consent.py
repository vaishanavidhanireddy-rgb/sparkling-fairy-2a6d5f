"""Consent records for demo report analysis."""
ANALYSIS_PURPOSE = "Use my report text for experimental comparison"
SMS_PURPOSE = "Receive SMS confirmations when I create a report QR share"


def has_analysis_consent(db, user_id):
    row = db.execute(
        "SELECT granted FROM consents WHERE user_id = ? AND purpose = ? ORDER BY id DESC LIMIT 1",
        (user_id, ANALYSIS_PURPOSE),
    ).fetchone()
    return bool(row and row["granted"])


def record_analysis_consent(db, user_id, granted):
    db.execute(
        "INSERT INTO consents (user_id, purpose, granted) VALUES (?, ?, ?)",
        (user_id, ANALYSIS_PURPOSE, int(granted)),
    )


def has_sms_consent(db, user_id):
    row = db.execute(
        "SELECT granted FROM consents WHERE user_id = ? AND purpose = ? ORDER BY id DESC LIMIT 1",
        (user_id, SMS_PURPOSE),
    ).fetchone()
    return bool(row and row["granted"])


def record_sms_consent(db, user_id, granted):
    db.execute(
        "INSERT INTO consents (user_id, purpose, granted) VALUES (?, ?, ?)",
        (user_id, SMS_PURPOSE, int(granted)),
    )
