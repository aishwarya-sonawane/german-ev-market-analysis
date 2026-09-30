"""Tests for the FZ 10.1 parser. Run with:  pytest -q

They use FAKE files from make_fixture.py that copy the KBA layout, so the
tests check the logic (subtotals dropped, no double counting, non-overlapping
categories), not any real market numbers.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from kba_fz10 import CATEGORY_LABELS, load_folder, parse_file  # noqa: E402
from make_fixture import make_month_file, make_series          # noqa: E402


@pytest.fixture()
def one_file(tmp_path):
    p = tmp_path / "fz10_2026_08.xlsx"
    grand = make_month_file(p, 2026, 8)
    return p, grand


def test_month_is_read_from_the_header(one_file):
    p, _ = one_file
    tidy, rep = parse_file(p)
    assert rep.month == "2026-08"
    assert set(tidy["month"]) == {pd.Timestamp("2026-08-01")}


def test_subtotals_and_footnotes_are_dropped(one_file):
    p, _ = one_file
    tidy, _ = parse_file(p)
    text = " ".join(tidy["brand"].astype(str)) + " " + " ".join(tidy["model"].astype(str))
    assert "ZUSAMMEN" not in text.upper()
    assert "INSGESAMT" not in text.upper()
    assert "Fußnote" not in text and "Quelle" not in text


def test_brand_is_forward_filled(one_file):
    p, _ = one_file
    tidy, _ = parse_file(p)
    assert set(tidy["brand"]) == {"ALFA ROMEO", "AUDI", "BMW", "SONSTIGE"}
    audi_models = set(tidy.loc[tidy["brand"] == "AUDI", "model"])
    assert audi_models == {"A3", "A6", "Q4", "SONSTIGE"}


def test_other_brands_without_model_rows_are_kept(one_file):
    p, _ = one_file
    tidy, _ = parse_file(p)
    other = tidy[tidy["brand"] == "SONSTIGE"]
    assert other["registrations"].sum() == 500
    assert other.loc[other["fuel_key"] == "bev", "registrations"].iloc[0] == 30


def test_parsed_total_matches_official_grand_total_row(one_file):
    p, grand = one_file
    _, rep = parse_file(p)
    assert rep.grand_total_parsed == rep.grand_total_official == int(grand[0])


def test_no_double_counting_categories_sum_to_the_grand_total(one_file):
    p, grand = one_file
    tidy, _ = parse_file(p)
    assert tidy["registrations"].sum() == int(grand[0])


def test_categories_are_the_five_expected(one_file):
    p, _ = one_file
    tidy, _ = parse_file(p)
    assert set(tidy["fuel_category"]) == set(CATEGORY_LABELS.values())


def test_reconciliation_reports_no_gaps_on_clean_file(one_file):
    p, _ = one_file
    _, rep = parse_file(p)
    assert rep.reconciliation_gaps == 0


def test_dash_means_zero_and_counts_are_ints(one_file):
    p, _ = one_file
    tidy, _ = parse_file(p)
    assert (tidy["registrations"] >= 0).all()
    assert str(tidy["registrations"].dtype).startswith("int")


def test_bad_file_is_skipped_not_fatal(tmp_path):
    make_month_file(tmp_path / "fz10_2026_07.xlsx", 2026, 7)
    (tmp_path / "broken.xlsx").write_bytes(b"not an excel file")
    data, reports, skipped = load_folder(tmp_path)
    assert len(reports) == 1 and len(skipped) == 1


def test_many_months_are_combined_in_order(tmp_path):
    make_series(tmp_path, start=(2024, 9), months=24)
    data, reports, skipped = load_folder(tmp_path)
    assert not skipped
    assert [r.month for r in reports][0] == "2024-09"
    assert [r.month for r in reports][-1] == "2026-08"
    assert data["month"].nunique() == 24
