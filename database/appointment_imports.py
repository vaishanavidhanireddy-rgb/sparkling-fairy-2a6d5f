"""Validated, transaction-safe import helpers for appointment directory CSVs."""
import csv
import io
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


LGD_URBAN_SOURCE = "https://www.data.gov.in/resource/local-government-directory-lgd-local-bodies-pin-codes"
LGD_STATES_SOURCE = "https://www.data.gov.in/resource/local-government-directory-lgd-states"
LGD_DISTRICTS_SOURCE = "https://www.data.gov.in/resource/local-government-directory-lgd-districts"
OGD_HOSPITAL_SOURCE = "https://www.data.gov.in/resource/national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month"
NMC_DOCTOR_SOURCE = "https://nmr.nmc.org.in/search-doctor"
MAX_ROWS = 250_000
UNSPECIFIED_LOCALITY = "Locality not reported by source"


def normalize_header(value):
    value = (value or "").strip().casefold()
    return "_".join("".join(char if char.isalnum() else " " for char in value).split())


def clean(value):
    value = (value or "").strip()
    return "" if value.casefold() in {"0", "na", "n/a", "null", "none", "-"} else value


def _read_csv(path):
    try:
        if hasattr(path, "read"):
            stream = path
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                raise ValueError("CSV has no header row.")
            headers = {normalize_header(item): item for item in reader.fieldnames if item}
            rows = list(reader)
        else:
            with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames:
                    raise ValueError("CSV has no header row.")
                headers = {normalize_header(item): item for item in reader.fieldnames if item}
                rows = list(reader)
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must use UTF-8 or UTF-8 with BOM encoding.") from exc
    except csv.Error as exc:
        raise ValueError(f"CSV could not be parsed: {exc}") from exc
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError(f"CSV must contain between 1 and {MAX_ROWS:,} records.")
    return headers, rows


def _value(row, headers, *names):
    for name in names:
        original = headers.get(normalize_header(name))
        if original:
            value = clean(row.get(original))
            if value:
                return value
    return ""


def read_states_csv(path):
    headers, rows = _read_csv(path)
    state_fields = ("state", "state_name", "state_name_en", "state_name_english", "state_name_in_english", "state_ut_name")
    code_fields = ("state_code", "lgd_state_code", "lgd_code", "state_id")
    if not any(normalize_header(name) in headers for name in state_fields):
        raise ValueError("LGD states CSV needs an English state/UT name column.")
    states = {}
    for line, row in enumerate(rows, start=2):
        name = _value(row, headers, *state_fields)
        code = _value(row, headers, *code_fields)
        if not name or len(name) > 120:
            raise ValueError(f"LGD states CSV row {line} has a missing or overlong state/UT name.")
        states[name.casefold()] = (name, code)
    return list(states.values())


def read_districts_csv(path, state_code_names=None):
    headers, rows = _read_csv(path)
    state_fields = ("state", "state_name", "state_name_en", "state_name_english", "state_name_in_english", "state_ut_name")
    district_fields = ("district", "district_name", "district_name_en", "district_name_english", "district_name_in_english")
    state_code_fields = ("state_code", "lgd_state_code", "state_id")
    code_fields = ("district_code", "lgd_district_code", "lgd_code", "district_id")
    if not any(normalize_header(name) in headers for name in district_fields):
        raise ValueError("LGD districts CSV needs an English district name column.")
    rows_out = {}
    for line, row in enumerate(rows, start=2):
        state = _value(row, headers, *state_fields)
        if not state:
            state_code = _value(row, headers, *state_code_fields)
            state = (state_code_names or {}).get(state_code, "")
        district = _value(row, headers, *district_fields)
        code = _value(row, headers, *code_fields)
        if not state or not district:
            raise ValueError(f"LGD districts CSV row {line} needs a state name/code and district name.")
        if any(len(value) > 120 for value in (state, district)):
            raise ValueError(f"LGD districts CSV row {line} has a location name longer than 120 characters.")
        rows_out[(state.casefold(), district.casefold())] = (state, district, code)
    return list(rows_out.values())


def read_geography_csv(path):
    """Read LGD Urban-with-PIN CSV or a normalized state,district,city CSV.

    Each accepted city must be an urban local body (municipality, municipal
    corporation, town panchayat, etc.) from the LGD Urban dataset. An optional
    source-code field is retained for auditable updates.
    """
    headers, rows = _read_csv(path)
    state_fields = ("state", "state_name", "state_name_en", "state_name_english", "state_name_in_english", "state_ut_name")
    district_fields = ("district", "district_name", "district_name_en", "district_name_english", "district_name_in_english")
    city_fields = (
        "city", "town", "ulb_name", "urban_local_body_name", "local_body_name",
        "local_body_name_in_english", "urban_local_body_name_in_english",
        "local_body_name_english", "name_of_urban_local_body",
    )
    if not any(normalize_header(name) in headers for name in state_fields):
        raise ValueError("Geography CSV needs state/state_name, district/district_name, and an urban local body name column.")
    if not any(normalize_header(name) in headers for name in district_fields) or not any(normalize_header(name) in headers for name in city_fields):
        raise ValueError("Geography CSV needs state, district, and urban local body name columns.")
    code_fields = ("lgd_code", "local_body_code", "ulb_code", "urban_local_body_code", "local_body_code_lgd")
    type_fields = ("local_body_type", "local_body_type_name", "local_body_type_name_in_english", "type_of_local_body")
    locations = {}
    for line, row in enumerate(rows, start=2):
        state = _value(row, headers, *state_fields)
        district = _value(row, headers, *district_fields)
        city = _value(row, headers, *city_fields)
        if not state or not district or not city:
            raise ValueError(f"Geography CSV row {line} is missing state, district, or city/ULB name.")
        body_type = _value(row, headers, *type_fields)
        if body_type and any(token in body_type.casefold() for token in ("gram panchayat", "village panchayat", "block panchayat", "rural")):
            raise ValueError(f"Geography CSV row {line} is not an urban local body. Use the LGD Urban dataset.")
        if any(len(value) > 120 for value in (state, district, city)):
            raise ValueError(f"Geography CSV row {line} has a location name longer than 120 characters.")
        code = _value(row, headers, *code_fields)
        pincode = _value(row, headers, "pincode", "pin_code", "postal_code")
        if pincode and (not pincode.isdigit() or len(pincode) != 6):
            pincode = ""
        key = (state.casefold(), district.casefold(), city.casefold())
        existing = locations.get(key, (state, district, city, code, set()))
        pincodes = existing[4]
        if pincode:
            pincodes.add(pincode)
        locations[key] = (state, district, city, code or existing[3], pincodes)
    return [(state, district, city, code, "|".join(sorted(pincodes)))
            for state, district, city, code, pincodes in locations.values()]


def read_hospitals_csv(path):
    """Read the official National Hospital Directory CSV or normalized CSV."""
    headers, rows = _read_csv(path)
    names = set(headers)
    required = {"hospital_name", "state", "district"}
    if not required.issubset(names):
        raise ValueError("Hospital CSV must include hospital_name, state, and district; use the official OGD hospital CSV or the admin template.")
    is_ogd = "sr_no" in names
    if not is_ogd and "city" not in names:
        raise ValueError("Admin hospital CSV also needs a city column.")
    imported_at = datetime.now().isoformat(timespec="seconds")
    source_url = OGD_HOSPITAL_SOURCE if is_ogd else ""
    result = []
    for line, row in enumerate(rows, start=2):
        hospital_name = _value(row, headers, "hospital_name")
        state = _value(row, headers, "state")
        district = _value(row, headers, "district")
        if is_ogd:
            city = _value(row, headers, "town", "subtown", "village") or UNSPECIFIED_LOCALITY
            area = _value(row, headers, "location", "address_original_first_line") or "Not provided by source"
            address = _value(row, headers, "address_original_first_line")
            phone = _value(row, headers, "telephone", "mobile_number")
            category = _value(row, headers, "hospital_category")
            care_type = _value(row, headers, "hospital_care_type")
            specialties = _value(row, headers, "specialties")
            pincode = _value(row, headers, "pincode")
            coordinates = _value(row, headers, "location_coordinates")
            source_type = "data.gov.in"
            source_id = _value(row, headers, "sr_no")
        else:
            city = _value(row, headers, "city")
            area = _value(row, headers, "area") or "Not provided"
            address = _value(row, headers, "address")
            phone = _value(row, headers, "phone")
            category = _value(row, headers, "category")
            care_type = _value(row, headers, "care_type")
            specialties = _value(row, headers, "specialties")
            pincode = _value(row, headers, "pincode")
            coordinates = _value(row, headers, "coordinates")
            source_type = "admin_uploaded"
            source_id = ""
        if not hospital_name or not state or not district:
            raise ValueError(f"Hospital CSV row {line} is missing its hospital name, state, or district.")
        fields = (hospital_name, state, district, city, area, address, phone, category, care_type,
                  specialties, pincode, coordinates, source_type, source_id, source_url, imported_at)
        limits = (160, 100, 100, 120, 200, 400, 50, 120, 120, 500, 12, 80, 30, 100, 300, 40)
        if any(len(value) > maximum for value, maximum in zip(fields, limits)):
            raise ValueError(f"Hospital CSV row {line} has a field longer than the supported limit.")
        result.append(fields)
    return result


def align_hospital_cities(hospitals, locations):
    """Align official directory rows only on an exact name or unique district PIN."""
    by_name = {}
    by_pin = {}
    for state, district, city, _code, pincodes in locations or []:
        parent = (state.casefold(), district.casefold())
        by_name.setdefault((*parent, city.casefold()), set()).add(city)
        for pincode in pincodes.split("|") if pincodes else ():
            by_pin.setdefault((*parent, pincode), set()).add(city)
    aligned = []
    for row in hospitals:
        values = list(row)
        if values[12] != "data.gov.in":
            aligned.append(tuple(values))
            continue
        _hospital_name, state, district, city = values[:4]
        parent = (state.casefold(), district.casefold())
        names = by_name.get((*parent, city.casefold()), set()) if city != UNSPECIFIED_LOCALITY else set()
        if len(names) == 1:
            values[3] = next(iter(names))
        else:
            pincode = values[10]
            candidates = by_pin.get((*parent, pincode), set()) if pincode else set()
            if len(candidates) == 1:
                values[3] = next(iter(candidates))
        aligned.append(tuple(values))
    return aligned


def read_doctors_csv(path):
    """Read manually checked doctor records tied to full hospital coordinates."""
    headers, rows = _read_csv(path)
    required = {"hospital_name", "state", "district", "city", "doctor_name"}
    if not required.issubset(headers):
        raise ValueError("Doctor CSV needs hospital_name,state,district,city,doctor_name. specialty, registration_number, verification_status and verification_url are optional.")
    result = []
    for line, row in enumerate(rows, start=2):
        values = tuple(_value(row, headers, name) for name in ("hospital_name", "state", "district", "city", "doctor_name"))
        if not all(values):
            raise ValueError(f"Doctor CSV row {line} is missing a hospital match or doctor name.")
        hospital_name, state, district, city, doctor_name = values
        if any(len(value) > 160 for value in values):
            raise ValueError(f"Doctor CSV row {line} has a name longer than 160 characters.")
        specialty = _value(row, headers, "specialty")[:160]
        registration = _value(row, headers, "registration_number")[:80]
        verification_url = _value(row, headers, "verification_url")[:500]
        status = _value(row, headers, "verification_status").casefold() or "unverified"
        if status not in {"verified", "unverified"}:
            raise ValueError(f"Doctor CSV row {line} verification_status must be verified or unverified.")
        if status == "verified":
            parsed_url = urlparse(verification_url)
            host = (parsed_url.hostname or "").casefold()
            if (not registration or parsed_url.scheme != "https"
                    or not (host == "nmc.org.in" or host.endswith(".nmc.org.in"))):
                raise ValueError(f"Doctor CSV row {line} can be marked verified only with a registration number and NMC verification URL.")
        result.append((hospital_name, state, district, city, doctor_name, specialty, registration,
                       verification_url, status, line))
    return result
