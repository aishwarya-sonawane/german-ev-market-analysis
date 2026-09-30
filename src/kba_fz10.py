"""Parser for KBA "FZ 10.1" monthly Excel files.

KBA publishes new passenger-car registrations in Germany by brand and model
series (Marke / Modellreihe) and by fuel type. The Excel layout is built for
humans, not machines, so this module turns it into a tidy table:

    month | brand | model | fuel_category | registrations

Layout facts this parser relies on (checked on the August 2026 file):
  * Sheet "FZ 10.1" holds the data.
  * A header row has "Marke" in one column and "Modellreihe" in the next.
    Fuel groups sit to the right in that same row ("Insgesamt", "mit
    Dieselantrieb", ...). Each group has 3 columns: the month, the year to
    date ("Jan. - August 2026") and the share in %. Only the month column is used.
  * Brand is written only on the first row of its block -> forward fill.
  * Rows like "AUDI ZUSAMMEN" are brand subtotals -> dropped (used only to
    reconcile the model rows).
  * Zero is written as "-".

Fuel groups OVERLAP in the source (e.g. "Hybrid incl. plug-in" contains
"Plug-in hybrid"). We therefore use only non-overlapping groups and derive the
rest:

    Diesel        = "mit Dieselantrieb"
    BEV           = "mit Elektroantrieb (BEV)"
    PHEV          = "Plug-in-Hybridantrieb"
    HEV           = "Hybridantrieb (ohne Plug-in-Hybrid)"
    Petrol_other  = Insgesamt - Diesel - BEV - PHEV - HEV   (derived)

"Petrol_other" also contains small categories such as gas, hydrogen and
other drives, because the file has no separate petrol column.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SHEET = "FZ 10.1"

MONTHS_DE = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

# normalised header text  ->  internal key
GROUP_KEYS = {
    "insgesamt": "total",
    "mit dieselantrieb": "diesel",
    "hybridantrieb (ohne plug-in-hybrid)": "hev",
    "plug-in-hybridantrieb": "phev",
    "mit elektroantrieb (bev)": "bev",
}
REQUIRED = ["total", "diesel", "hev", "phev", "bev"]

CATEGORY_LABELS = {
    "bev": "Electric (BEV)",
    "phev": "Plug-in hybrid",
    "hev": "Hybrid (no plug-in)",
    "diesel": "Diesel",
    "petrol_other": "Petrol & other",
}
CATEGORY_ORDER = ["bev", "phev", "hev", "diesel", "petrol_other"]


def _norm(text) -> str:
    """Lower-case, collapse whitespace/newlines so header matching is robust."""
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def _to_number(value) -> float:
    """KBA writes zero as '-'. Counts may be real numbers or text ('1191', '1.519')."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if s in {"", "-", "\u2013", "x", "."}:
        return 0.0
    if re.fullmatch(r"\d+", s):
        return float(s)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):        # German thousands separator
        return float(s.replace(".", ""))
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return 0.0


def _month_from_text(text) -> pd.Timestamp | None:
    m = re.search(r"([A-Za-zäöüÄÖÜ]+)\s+(20\d{2})", str(text))
    if m and m.group(1).lower() in MONTHS_DE:
        return pd.Timestamp(year=int(m.group(2)), month=MONTHS_DE[m.group(1).lower()], day=1)
    return None


def _month_from_filename(path: Path) -> pd.Timestamp | None:
    m = re.search(r"(20\d{2})[_\-]?(\d{2})", path.stem)
    if m and 1 <= int(m.group(2)) <= 12:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    return None


@dataclass
class ParseReport:
    file: str
    month: str
    model_rows: int
    reconciliation_gaps: int
    negative_residual_rows: int
    grand_total_parsed: int = 0
    grand_total_official: int = 0


def parse_file(path: str | Path) -> tuple[pd.DataFrame, ParseReport]:
    """Parse one monthly FZ 10 file into a tidy DataFrame."""
    path = Path(path)
    raw = pd.read_excel(path, sheet_name=SHEET, header=None, dtype=object)

    # 1. locate the header row: 'Marke' followed by 'Modellreihe'
    header_row = brand_col = None
    for r in range(min(len(raw), 40)):
        for c in range(raw.shape[1] - 1):
            if _norm(raw.iat[r, c]) == "marke" and _norm(raw.iat[r, c + 1]) == "modellreihe":
                header_row, brand_col = r, c
                break
        if header_row is not None:
            break
    if header_row is None:
        raise ValueError(f"{path.name}: could not find the 'Marke | Modellreihe' header row")
    model_col = brand_col + 1

    # 2. find the month column of each fuel group. The group names are either on
    #    the 'Marke' row (files from mid-2026) or one/two rows above it (older files).
    group_cols: dict[str, int] = {}
    for r in range(max(0, header_row - 2), header_row + 1):
        for c in range(model_col + 1, raw.shape[1]):
            key = GROUP_KEYS.get(_norm(raw.iat[r, c]))
            if key and key not in group_cols:
                group_cols[key] = c            # first of the 3 columns = month
    missing = [k for k in REQUIRED if k not in group_cols]
    if missing:
        raise ValueError(f"{path.name}: fuel groups not found in header: {missing}")

    # 3. month: from the sub-header ("August 2026"), else from the file name
    month = None
    for r in range(header_row, min(header_row + 3, len(raw))):
        month = _month_from_text(raw.iat[r, group_cols["total"]])
        if month is not None:
            break
    month = month or _month_from_filename(path)
    if month is None:
        raise ValueError(f"{path.name}: could not determine the month")

    # 4. first data row = first row after the sub-header that has a brand
    first = header_row + 1
    while first < len(raw) and _to_number(raw.iat[first, group_cols["total"]]) == 0 \
            and pd.isna(raw.iat[first, brand_col]) and pd.isna(raw.iat[first, model_col]):
        first += 1
    body = raw.iloc[first:].copy()

    df = pd.DataFrame({
        "brand_raw": body.iloc[:, brand_col].values,
        "model": body.iloc[:, model_col].values,
        **{k: body.iloc[:, c].map(_to_number).values for k, c in group_cols.items()},
    })
    # keep only real data rows (a numeric total cell). Drops title/footnote rows.
    df = df[df["brand_raw"].notna() | df["model"].notna()].copy()

    label_all = df["brand_raw"].astype(str).str.upper()
    is_grand = label_all.str.contains("INSGESAMT", na=False)          # NEUZULASSUNGEN INSGESAMT
    is_sub = label_all.str.contains("ZUSAMMEN", na=False) | is_grand
    # some files put the label in the model column instead
    is_sub |= df["model"].astype(str).str.upper().str.contains("ZUSAMMEN|INSGESAMT", na=False)

    grand_expected = None
    if is_grand.any():
        grand_expected = float(df.loc[is_grand, "total"].iloc[-1])

    # subtotal labels ("AUDI ZUSAMMEN") are used to reconcile the model rows
    sub_rows = {}
    for idx, row in df[is_sub & ~is_grand].iterrows():
        label = row["brand_raw"] if pd.notna(row["brand_raw"]) else row["model"]
        label = re.sub(r"ZUSAMMEN", "", str(label).upper()).strip()
        if label:
            sub_rows[label] = idx

    df.loc[is_sub, "brand_raw"] = pd.NA            # so they never feed the forward fill
    df["brand"] = df["brand_raw"].ffill()
    df.loc[is_grand, "brand"] = pd.NA

    # (a) brand line that carries its own numbers but has no model rows, e.g. "SONSTIGE"
    #     in older files: keep it as a single row with model "SONSTIGE"
    lone_brand = df["model"].isna() & ~is_sub & df["brand_raw"].notna() & (df["total"] > 0)
    df.loc[lone_brand, "model"] = "SONSTIGE"

    models = df[~is_sub & df["model"].notna() & df["brand"].notna()].copy()

    # (b) a subtotal row whose brand has NO model rows underneath (e.g. "SONSTIGE ZUSAMMEN"
    #     in newer files) is the only place those registrations exist -> keep it as a row
    have_models = set(models["brand"].astype(str).str.strip().str.upper())
    extra = []
    for label, idx in sub_rows.items():
        if label not in have_models:
            r = df.loc[idx].copy()
            r["brand"], r["model"] = label, "SONSTIGE"
            extra.append(r)
    if extra:
        models = pd.concat([models, pd.DataFrame(extra)], ignore_index=True)
    sub_expected = {k: float(df.loc[i, "total"]) for k, i in sub_rows.items()}

    models["brand"] = models["brand"].astype(str).str.strip()
    models["model"] = models["model"].astype(str).str.strip()

    # 5. derived category and non-overlap safety net
    models["petrol_other"] = models["total"] - models[["diesel", "bev", "phev", "hev"]].sum(axis=1)
    neg = int((models["petrol_other"] < 0).sum())
    if neg:
        log.warning("%s: %d rows where fuel groups exceed the total (check overlaps)", path.name, neg)
    models["petrol_other"] = models["petrol_other"].clip(lower=0)

    # 6. reconcile model rows against the brand subtotal rows
    gaps = 0
    sums = models.groupby(models["brand"].str.upper())["total"].sum()
    for brand, expected in sub_expected.items():
        if brand in sums.index and abs(sums[brand] - expected) > 0.5:
            gaps += 1
            log.warning("%s: %s model rows sum to %s but the subtotal says %s",
                        path.name, brand, sums[brand], expected)

    if grand_expected is not None and abs(models["total"].sum() - grand_expected) > 0.5:
        gaps += 1
        log.warning("%s: parsed total %s differs from KBA 'NEUZULASSUNGEN INSGESAMT' %s",
                    path.name, models["total"].sum(), grand_expected)

    tidy = models.melt(
        id_vars=["brand", "model"],
        value_vars=CATEGORY_ORDER,
        var_name="fuel_key",
        value_name="registrations",
    )
    tidy["month"] = month
    tidy["fuel_category"] = tidy["fuel_key"].map(CATEGORY_LABELS)
    tidy["registrations"] = tidy["registrations"].astype(int)
    tidy = tidy[["month", "brand", "model", "fuel_key", "fuel_category", "registrations"]]

    report = ParseReport(path.name, month.strftime("%Y-%m"), len(models), gaps, neg,
                         int(models["total"].sum()), int(grand_expected or 0))
    return tidy, report


def load_folder(folder: str | Path) -> tuple[pd.DataFrame, list[ParseReport], list[str]]:
    """Parse every *.xlsx in a folder. Bad files are skipped and reported.

    If the same month appears in two files, the file that sorts last wins.
    """
    parsed: dict[str, tuple[pd.DataFrame, ParseReport]] = {}
    skipped: list[str] = []
    for f in sorted(Path(folder).glob("*.xlsx")):
        if f.name.startswith("~$"):
            continue
        try:
            tidy, rep = parse_file(f)
        except Exception as exc:                       # keep going, report at the end
            skipped.append(f"{f.name}: {exc}")
            log.error("skipped %s: %s", f.name, exc)
            continue
        if rep.month in parsed:
            log.warning("month %s appears twice, using %s", rep.month, f.name)
        parsed[rep.month] = (tidy, rep)
    if not parsed:
        raise SystemExit(f"No usable FZ 10 files found in {folder}")
    months = sorted(parsed)
    data = pd.concat([parsed[m][0] for m in months], ignore_index=True)
    return data, [parsed[m][1] for m in months], skipped
