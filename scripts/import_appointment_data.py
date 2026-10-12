"""Import LGD geography, official hospitals and manually checked doctors."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.appointment_imports import (  # noqa: E402
    LGD_DISTRICTS_SOURCE,
    LGD_STATES_SOURCE,
    LGD_URBAN_SOURCE,
    NMC_DOCTOR_SOURCE,
    align_hospital_cities,
    read_districts_csv,
    read_doctors_csv,
    read_geography_csv,
    read_hospitals_csv,
    read_states_csv,
)
from database.models import connection, init_db  # noqa: E402


def import_files(database_path, geography_path=None, hospital_path=None, doctor_path=None,
                 states_path=None, districts_path=None):
    """Validate every input first, then apply imports in one SQLite transaction."""
    locations = read_geography_csv(geography_path) if geography_path else None
    states = read_states_csv(states_path) if states_path else None
    state_code_names = {code: name for name, code in states or [] if code}
    districts = read_districts_csv(districts_path, state_code_names) if districts_path else None
    if states is None and districts is not None:
        states = list({state.casefold(): (state, "") for state, _district, _code in districts}.values())
    if districts is None and locations is not None:
        districts = list({(state.casefold(), district.casefold()): (state, district, "")
                          for state, district, _city, _code, _pincodes in locations}.values())
    if states is None and districts is not None:
        states = list({state.casefold(): (state, "") for state, _district, _code in districts}.values())
    hospitals = read_hospitals_csv(hospital_path) if hospital_path else None
    doctors = read_doctors_csv(doctor_path) if doctor_path else None
    init_db(database_path)
    imported = {"states": 0, "districts": 0, "cities": 0, "hospitals": 0, "doctors": 0}
    with connection(database_path) as db:
        imported_at = datetime.now().isoformat(timespec="seconds")
        if states is not None:
            db.execute("UPDATE appointment_states SET active=0 WHERE source_url IN (?,?,?)",
                       (LGD_STATES_SOURCE, LGD_DISTRICTS_SOURCE, LGD_URBAN_SOURCE))
            states_source = LGD_STATES_SOURCE if states_path else LGD_DISTRICTS_SOURCE if districts_path else LGD_URBAN_SOURCE
            db.executemany(
                """INSERT INTO appointment_states(state,source_code,source_url,active,imported_at)
                   VALUES(?,?,?,1,?) ON CONFLICT(state) DO UPDATE SET
                   source_code=excluded.source_code,source_url=excluded.source_url,
                   active=1,imported_at=excluded.imported_at""",
                [(state, code, states_source, imported_at)
                 for state, code in states],
            )
            imported["states"] = len(states)
        if districts is not None:
            db.execute("UPDATE appointment_districts SET active=0 WHERE source_url IN (?,?)",
                       (LGD_DISTRICTS_SOURCE, LGD_URBAN_SOURCE))
            db.executemany(
                """INSERT INTO appointment_districts(state,district,source_code,source_url,active,imported_at)
                   VALUES(?,?,?,?,1,?) ON CONFLICT(state,district) DO UPDATE SET
                   source_code=excluded.source_code,source_url=excluded.source_url,
                   active=1,imported_at=excluded.imported_at""",
                [(state, district, code, LGD_DISTRICTS_SOURCE if districts_path else LGD_URBAN_SOURCE, imported_at)
                 for state, district, code in districts],
            )
            imported["districts"] = len(districts)
        if locations is not None:
            db.execute("UPDATE appointment_locations SET active=0 WHERE source_url=?", (LGD_URBAN_SOURCE,))
            db.executemany(
                """INSERT INTO appointment_locations
                   (state,district,city,source_code,pincodes,source_url,active,imported_at)
                   VALUES(?,?,?,?,?,?,1,?)
                   ON CONFLICT(state,district,city) DO UPDATE SET
                   source_code=excluded.source_code,pincodes=excluded.pincodes,source_url=excluded.source_url,
                   active=1,imported_at=excluded.imported_at""",
                [(state, district, city, code, pincodes, LGD_URBAN_SOURCE, imported_at)
                 for state, district, city, code, pincodes in locations],
            )
            imported["cities"] = len(locations)
        active_locations = locations
        if active_locations is None and hospitals is not None:
            active_locations = [tuple(row) for row in db.execute(
                """SELECT state,district,city,source_code,pincodes FROM appointment_locations
                   WHERE active=1 AND source_url=?""", (LGD_URBAN_SOURCE,)
            )]
        if active_locations is not None:
            # Reconcile previously imported national directory rows when LGD
            # names are refreshed; keep records whose location cannot be
            # unambiguously identified.
            existing_official = db.execute(
                """SELECT id,hospital_name,state,district,city,area,address,phone,category,care_type,
                          specialties,pincode,coordinates,source_type,source_record_id,source_url,imported_at
                   FROM appointment_hospitals WHERE source_type='data.gov.in'"""
            ).fetchall()
            if existing_official:
                existing_values = [tuple(row)[1:] for row in existing_official]
                aligned_existing = _align_hospital_cities(existing_values, active_locations)
                for old, aligned in zip(existing_official, aligned_existing):
                    if old[4] != aligned[3]:
                        db.execute("UPDATE appointment_hospitals SET city=? WHERE id=?", (aligned[3], old[0]))
        if hospitals is not None:
            hospitals = align_hospital_cities(hospitals, active_locations)
            db.executemany(
                """INSERT INTO appointment_hospitals
                   (hospital_name,state,district,city,area,address,phone,category,care_type,specialties,pincode,
                    coordinates,source_type,source_record_id,source_url,imported_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO UPDATE SET
                   address=excluded.address,phone=excluded.phone,category=excluded.category,care_type=excluded.care_type,
                   specialties=excluded.specialties,pincode=excluded.pincode,coordinates=excluded.coordinates,
                   source_type=excluded.source_type,source_record_id=excluded.source_record_id,
                   source_url=excluded.source_url,imported_at=excluded.imported_at""",
                hospitals,
            )
            imported["hospitals"] = len(hospitals)
        if doctors is not None:
            pending = []
            for hospital_name, state, district, city, doctor_name, specialty, registration, verification_url, status, line in doctors:
                hospital = db.execute(
                    """SELECT id FROM appointment_hospitals
                       WHERE hospital_name=? COLLATE NOCASE AND state=? COLLATE NOCASE
                       AND district=? COLLATE NOCASE AND city=? COLLATE NOCASE LIMIT 1""",
                    (hospital_name, state, district, city),
                ).fetchone()
                if not hospital:
                    raise ValueError(f"Doctor CSV row {line} does not match an imported hospital by name, state, district and city.")
                pending.append((hospital["id"], doctor_name, specialty, registration, verification_url,
                                status, "NMC public register" if status == "verified" else "admin_uploaded"))
            db.executemany(
                """INSERT INTO appointment_doctors
                   (hospital_id,doctor_name,specialty,registration_number,verification_url,verification_status,source_type)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(hospital_id,doctor_name,registration_number) DO UPDATE SET
                   specialty=excluded.specialty,verification_url=excluded.verification_url,
                   verification_status=excluded.verification_status,source_type=excluded.source_type""",
                pending,
            )
            imported["doctors"] = len(pending)
    return imported


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "quantum_healthcare.sqlite3",
                        help="SQLite database path (default: project database).")
    parser.add_argument("--geography", type=Path,
                        help="LGD Urban-with-PIN CSV or normalized state,district,city CSV.")
    parser.add_argument("--states", type=Path, help="LGD States CSV (optional; city data can derive state names).")
    parser.add_argument("--districts", type=Path, help="LGD Districts CSV (optional; city data can derive district names).")
    parser.add_argument("--hospitals", type=Path,
                        help="Official OGD National Hospital Directory CSV or admin CSV.")
    parser.add_argument("--doctors", type=Path,
                        help="Doctor CSV tied to exact hospital name/state/district/city fields.")
    args = parser.parse_args(argv)
    if not any((args.geography, args.states, args.districts, args.hospitals, args.doctors)):
        parser.error("provide at least one of --states, --districts, --geography, --hospitals or --doctors")
    try:
        counts = import_files(args.database, args.geography, args.hospitals, args.doctors,
                              args.states, args.districts)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Import failed; no appointment data was changed: {exc}\n")
    for key, count in counts.items():
        if count:
            print(f"Imported {count} {key} records.")
    if args.doctors:
        print(f"Doctor verification records must be manually checked against {NMC_DOCTOR_SOURCE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
