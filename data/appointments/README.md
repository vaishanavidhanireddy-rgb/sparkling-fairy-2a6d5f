# Appointment directory location and source data

`hospital_finder_locations.json` contains only the state, district, and city/town arrays extracted from the supplied `find-hospital-final` HTML, supplemented by the project's `states` list for the one missing Indian union territory. The Bangladesh region was excluded. The HTML also contains a hospital list with unclear provenance; those hospital entries and its doctor list were not imported.

The extracted location lists are user-provided and are not represented as an official or complete government geography source. Import or reactivate them in the existing appointment database from the project root:

```powershell
python -m scripts.import_hospital_finder_locations --input data/appointments/hospital_finder_locations.json
```

This adds or reactivates matching locations and preserves other database records. To re-extract the arrays from the original file, pass its path after `--input` instead. The importer reads only the JSON data object; it does not execute JavaScript in the HTML.

For official monthly geography snapshots, use the Government of India's [LGD States](https://www.data.gov.in/resource/local-government-directory-lgd-states), [LGD Districts](https://www.data.gov.in/resource/local-government-directory-lgd-districts), and [LGD Urban Local Bodies with PIN Codes](https://www.data.gov.in/resource/local-government-directory-lgd-local-bodies-pin-codes) datasets and the normal `scripts.import_appointment_data` importer. Hospital listings must come from the [National Hospital Directory](https://www.data.gov.in/resource/national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month); the supplied HTML's embedded hospital rows are deliberately excluded. Doctors are imported separately after their hospital association is checked in the [NMC public register](https://nmr.nmc.org.in/search-doctor).

`India_States_Districts_Hospitals.xlsx` is a user-provided workbook. Import it with `python -m scripts.import_appointment_workbook --input data/appointments/India_States_Districts_Hospitals.xlsx`. It supplies state/UTs, districts, district-HQ/main-city names, and hospital-name suggestions to the appointment dropdown. The workbook itself says many entries require local verification; imported hospitals are labeled unverified. It includes no doctor records, addresses, contacts, or booking availability.
