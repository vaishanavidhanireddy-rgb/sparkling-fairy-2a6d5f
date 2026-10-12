"""Import the location arrays from the supplied hospital finder HTML.

Only states, districts, and cities/towns are read. The HTML also embeds hospital
records whose provenance is unclear; those are deliberately not imported.
Existing directory data is preserved and matching active geography is reused.
"""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from database.models import connection, init_db

SOURCE_LABEL = "user-provided hospital finder location data"
DATA_PATTERN = re.compile(r"const DATA = (\{.*?\});\s*\n\s*const \$ =", re.DOTALL)


def read_location_data(html_path):
    path = Path(html_path)
    source = path.read_text(encoding="utf-8-sig")
    if path.suffix.casefold() == ".json":
        try:
            data = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ValueError("The supplied location data is not valid JSON.") from exc
    else:
        match = DATA_PATTERN.search(source)
        if not match:
            raise ValueError("Could not find the embedded DATA object in the supplied HTML.")
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError("The embedded location data is not valid JSON.") from exc

    raw_states = data.get("states")
    raw_districts = data.get("districts")
    raw_cities = data.get("cities")
    if not all(isinstance(rows, list) for rows in (raw_states, raw_districts, raw_cities)):
        raise ValueError("The HTML must contain states, districts, and cities arrays.")

    states_by_id = {}
    states = {}
    for row in raw_states:
        if not isinstance(row, dict) or not isinstance(row.get("id"), int):
            raise ValueError("A state record is missing its integer id.")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError("A state record has an invalid name.")
        name = name.strip()
        # The attached file also has one Bangladesh region; appointment
        # locations in this application are for India only.
        if "bangladesh" in name.casefold():
            continue
        if name.casefold() in states:
            raise ValueError(f"Duplicate state name in attached HTML: {name}")
        states[name.casefold()] = name
        states_by_id[row["id"]] = name
    if not states:
        raise ValueError("No Indian state/UT names were found in the attached HTML.")

    districts_by_id = {}
    districts = {}
    for row in raw_districts:
        if not isinstance(row, dict) or not isinstance(row.get("id"), int):
            raise ValueError("A district record is missing its integer id.")
        state = states_by_id.get(row.get("stateId"))
        name = row.get("name")
        if state is None:
            continue
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError("A district record has an invalid name.")
        name = name.strip()
        districts[(state.casefold(), name.casefold())] = (state, name)
        districts_by_id[row["id"]] = (state, name)
    if not districts:
        raise ValueError("No Indian districts were found in the attached HTML.")

    locations = {}
    for row in raw_cities:
        if not isinstance(row, dict):
            raise ValueError("A city record is invalid.")
        parent = districts_by_id.get(row.get("districtId"))
        name = row.get("name")
        if parent is None:
            continue
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError("A city/town record has an invalid name.")
        state, district = parent
        city = name.strip()
        locations[(state.casefold(), district.casefold(), city.casefold())] = (state, district, city)
    if not locations:
        raise ValueError("No Indian cities/towns were found in the attached HTML.")

    return list(states.values()), list(districts.values()), list(locations.values())


def import_locations(database_path, html_path):
    states, districts, locations = read_location_data(html_path)
    init_db(database_path)
    imported_at = datetime.now().isoformat(timespec="seconds")
    with connection(database_path) as db:
        db.executemany(
            """INSERT INTO appointment_states(state,source_code,source_url,active,imported_at)
               VALUES(?,'',?,1,?) ON CONFLICT(state) DO UPDATE SET active=1,imported_at=excluded.imported_at""",
            [(name, SOURCE_LABEL, imported_at) for name in states],
        )
        db.executemany(
            """INSERT INTO appointment_districts(state,district,source_code,source_url,active,imported_at)
               VALUES(?,?,'',?,1,?) ON CONFLICT(state,district) DO UPDATE SET active=1,imported_at=excluded.imported_at""",
            [(state, district, SOURCE_LABEL, imported_at) for state, district in districts],
        )
        db.executemany(
            """INSERT INTO appointment_locations
               (state,district,city,source_code,pincodes,source_url,active,imported_at)
               VALUES(?,?,?,'','',?,1,?)
               ON CONFLICT(state,district,city) DO UPDATE SET active=1,imported_at=excluded.imported_at""",
            [(state, district, city, SOURCE_LABEL, imported_at) for state, district, city in locations],
        )
    return {"states": len(states), "districts": len(districts), "cities": len(locations)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to the extracted location JSON or original finder HTML.")
    parser.add_argument("--database", type=Path, default=Path(__file__).resolve().parents[1] / "quantum_healthcare.sqlite3")
    args = parser.parse_args(argv)
    try:
        counts = import_locations(args.database, args.input)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Imported/reused {states} states/UTs, {districts} districts, and {cities} cities/towns from the supplied location data.".format(**counts))
    print("No hospital or doctor records were imported. Add those from independently verified directories.")


if __name__ == "__main__":
    main()
