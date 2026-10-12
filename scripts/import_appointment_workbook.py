"""Import Indian appointment locations and unverified listings from the supplied XLSX workbook.

The spreadsheet is user-provided and its hospital entries are not verified.
The importer preserves existing rows and never creates doctor records.
"""
import argparse
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.models import connection, init_db  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
SOURCE_LABEL = "user-provided India_States_Districts_Hospitals.xlsx (unverified)"
MAX_ROWS = 10000


def _cell_value(cell, shared_strings):
    kind = cell.get("t", "")
    if kind == "inlineStr":
        value = "".join(part.text or "" for part in cell.findall(".//m:t", NS))
    else:
        node = cell.find("m:v", NS)
        value = node.text if node is not None else ""
        if kind == "s" and value:
            value = shared_strings[int(value)]
    return value.strip()


def read_workbook(path):
    """Return validated states, districts, city/towns and hospital listings."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("Choose a valid .xlsx workbook.") from exc
    with archive:
        try:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (KeyError, ET.ParseError) as exc:
            raise ValueError("The workbook is missing valid Excel workbook metadata.") from exc
        targets = {item.get("Id"): item.get("Target", "")
                   for item in relationships.findall("p:Relationship", NS)}
        sheet_ref = next((sheet.get("{%(r)s}id" % NS) for sheet in workbook.findall("m:sheets/m:sheet", NS)
                          if sheet.get("name", "").strip().casefold() == "states and districts"), None)
        if not sheet_ref or sheet_ref not in targets:
            raise ValueError("Workbook needs a 'States and Districts' sheet.")
        target = targets[sheet_ref].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        try:
            sheet = ET.fromstring(archive.read(target))
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in archive.namelist() else None
        except (KeyError, ET.ParseError) as exc:
            raise ValueError("Could not read the workbook data sheet.") from exc
        shared_strings = (["".join(node.text or "" for node in item.findall(".//m:t", NS))
                           for item in shared.findall("m:si", NS)] if shared is not None else [])
        rows = []
        for row in sheet.findall(".//m:sheetData/m:row", NS):
            values = {}
            for cell in row.findall("m:c", NS):
                col = re.match(r"[A-Z]+", cell.get("r", ""))
                if col:
                    values[col.group()] = _cell_value(cell, shared_strings)
            rows.append((int(row.get("r", "0")), values))

    if not rows:
        raise ValueError("The States and Districts sheet is empty.")
    header = rows[0][1]
    expected = {"B": "state / ut", "C": "district", "D": "district hq / main city"}
    for col, label in expected.items():
        if header.get(col, "").casefold() != label:
            raise ValueError(f"Expected '{label}' in column {col} of the first row.")
    for col, label in (("E", "hospital 1"), ("F", "hospital 2"), ("G", "hospital 3")):
        if header.get(col, "").casefold() != label:
            raise ValueError("Expected Hospital 1, Hospital 2 and Hospital 3 columns (E-G).")

    states, districts, locations, hospitals = {}, {}, {}, []
    for line, row in rows[1:]:
        state, district, city = (row.get(key, "") for key in ("B", "C", "D"))
        names = [row.get(key, "") for key in ("E", "F", "G")]
        if not any((state, district, city, *names)):
            continue
        if not state or not district or not city:
            raise ValueError(f"Workbook row {line} needs a state, district, and district HQ/main city.")
        if any(len(value) > 120 for value in (state, district, city)):
            raise ValueError(f"Workbook row {line} has a location name longer than 120 characters.")
        states.setdefault(state.casefold(), state)
        districts.setdefault((state.casefold(), district.casefold()), (state, district))
        locations.setdefault((state.casefold(), district.casefold(), city.casefold()), (state, district, city))
        for index, name in enumerate(names, start=1):
            if not name:
                continue
            if len(name) > 160:
                raise ValueError(f"Workbook row {line} has a hospital name longer than 160 characters.")
            hospitals.append((name, state, district, city, f"row-{line}-hospital-{index}"))
        if len(hospitals) > MAX_ROWS * 3:
            raise ValueError(f"Workbook contains more than {MAX_ROWS} rows.")
    if not states or not districts or not locations:
        raise ValueError("No complete Indian state, district, and city rows were found.")
    return list(states.values()), list(districts.values()), list(locations.values()), hospitals


def import_workbook(database_path, workbook_path):
    states, districts, locations, hospitals = read_workbook(workbook_path)
    init_db(database_path)
    imported_at = datetime.now().isoformat(timespec="seconds")
    counts = {"states": len(states), "districts": len(districts), "cities": len(locations), "hospitals": 0}
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
            """INSERT INTO appointment_locations(state,district,city,source_code,pincodes,source_url,active,imported_at)
               VALUES(?,?,?,'','',?,1,?) ON CONFLICT(state,district,city)
               DO UPDATE SET active=1,imported_at=excluded.imported_at""",
            [(state, district, city, SOURCE_LABEL, imported_at) for state, district, city in locations],
        )
        for name, state, district, city, source_id in hospitals:
            cursor = db.execute(
                """INSERT INTO appointment_hospitals
                   (hospital_name,state,district,city,area,category,source_type,source_record_id,source_url,imported_at)
                   VALUES(?,?,?,?,'Not provided by spreadsheet','Unverified - confirm locally',?,?,?,?)
                   ON CONFLICT(hospital_name,state,district,city,area) DO NOTHING""",
                (name, state, district, city, "spreadsheet_unverified", source_id, SOURCE_LABEL, imported_at),
            )
            counts["hospitals"] += max(cursor.rowcount, 0)
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Supplied India_States_Districts_Hospitals.xlsx file.")
    parser.add_argument("--database", type=Path, default=ROOT / "quantum_healthcare.sqlite3")
    args = parser.parse_args(argv)
    try:
        counts = import_workbook(args.database, args.input)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"Import failed; no appointment data was changed: {exc}\n")
    for kind, count in counts.items():
        print(f"Imported/reused {count} {kind} from the workbook.")
    print("Hospital listings are unverified; no doctor records were created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
