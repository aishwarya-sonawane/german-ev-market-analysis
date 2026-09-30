# Data

## Source
**Kraftfahrt-Bundesamt (KBA)**, table **FZ 10.1** "Neuzulassungen von Personenkraftwagen nach Marken und Modellreihen"
(new passenger-car registrations by brand and model series, split by fuel type), one Excel file per month.

Download page: https://www.kba.de/DE/Statistik/Produktkatalog/produkte/Fahrzeuge/fz10/fz10_gentab.html
(older years are linked from the KBA statistics pages).

This project uses the 24 months **September 2024 to August 2026**.
Files were downloaded by the author in September 2026. Please check KBA's terms of use before republishing.

## Put the raw files here
Save them in `data/raw/` as `fz10_YYYY_MM.xlsx` (for example `fz10_2026_08.xlsx`). They are not committed to git.

## What is committed
| File | Content |
|---|---|
| `processed/registrations_tidy.csv` | Cleaned data: month, brand, model, fuel category, registrations |
| `processed/parse_report.csv` | For each month: parsed total vs KBA's own grand total |
| `reference/brand_origin.csv` | Brand -> parent-company origin (judgement, editable) |

`processed/registrations.sqlite` is rebuilt with `python src/build_dataset.py`.

## Fuel categories
| Category | Source column in FZ 10.1 |
|---|---|
| Electric (BEV) | mit Elektroantrieb (BEV) |
| Plug-in hybrid | Plug-in-Hybridantrieb |
| Hybrid (no plug-in) | Hybridantrieb (ohne Plug-in-Hybrid), includes 48V mild hybrids |
| Diesel | mit Dieselantrieb |
| Petrol & other | derived: total minus the four above (includes small volumes of gas, hydrogen and other drives) |
