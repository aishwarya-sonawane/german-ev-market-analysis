"""Build the analysis dataset from the raw KBA FZ 10 Excel files.

    python src/build_dataset.py            # reads data/raw, writes data/processed

Outputs (data/processed):
  registrations_tidy.csv   one row per month x brand x model x fuel category
  registrations.sqlite     same data + dim_brand, ready for SQL
  parse_report.csv         per-file check against KBA's own grand-total row
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from kba_fz10 import load_folder

ROOT = Path(__file__).resolve().parents[1]

# SsangYong was renamed KGM on 1 April 2025 (footnote in the KBA files).
BRAND_ALIASES = {"SSANGYONG": "KGM"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=ROOT / "data" / "raw")
    ap.add_argument("--out", default=ROOT / "data" / "processed")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    data, reports, skipped = load_folder(args.raw)
    data["brand"] = data["brand"].replace(BRAND_ALIASES)
    data["month"] = data["month"].dt.strftime("%Y-%m-%d")
    data = (data.groupby(["month", "brand", "model", "fuel_key", "fuel_category"], as_index=False)
                .registrations.sum())

    # ---- integrity checks: fail loudly instead of publishing wrong numbers -------------
    rep = pd.DataFrame([r.__dict__ for r in reports])
    rep["matches_kba_total"] = rep["grand_total_parsed"] == rep["grand_total_official"]
    rep.to_csv(out / "parse_report.csv", index=False)
    bad = rep[~rep["matches_kba_total"] | (rep["reconciliation_gaps"] > 0)]
    if len(bad):
        raise SystemExit(f"Totals do not match KBA for: {bad['month'].tolist()} - see parse_report.csv")
    if skipped:
        print("Skipped files:\n  " + "\n  ".join(skipped))
    months = sorted(data["month"].unique())
    expected = pd.period_range(months[0][:7], months[-1][:7], freq="M")
    missing = [str(p) for p in expected if f"{p}-01" not in months]
    if missing:
        print("WARNING: months missing from the series:", missing)

    data.to_csv(out / "registrations_tidy.csv", index=False)

    dim = pd.read_csv(ROOT / "data" / "reference" / "brand_origin.csv")
    unknown = sorted(set(data["brand"]) - set(dim["brand"]))
    if unknown:
        print("WARNING: brands missing from data/reference/brand_origin.csv:", unknown)

    db = out / "registrations.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript((ROOT / "sql" / "schema.sql").read_text())
    data.to_sql("registrations", con, if_exists="append", index=False)
    dim.to_sql("dim_brand", con, if_exists="append", index=False)
    con.commit()
    n = con.execute("select count(*), min(month), max(month) from registrations").fetchone()
    con.close()

    print(f"OK  {len(months)} months ({months[0][:7]} to {months[-1][:7]}), "
          f"{n[0]:,} rows, {int(data['registrations'].sum()):,} registrations")
    print(f"    every month matches KBA's official 'NEUZULASSUNGEN INSGESAMT'")
    print(f"    wrote {out}/registrations_tidy.csv, registrations.sqlite, parse_report.csv")


if __name__ == "__main__":
    main()
