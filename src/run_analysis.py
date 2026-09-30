"""Run the SQL analysis, draw the charts, export Power BI files and write the findings.

    python src/run_analysis.py

Reads  data/processed/registrations.sqlite   (built by src/build_dataset.py)
Writes images/*.png                          charts used in the README
       reports/findings.md                   every number is computed from the data
       reports/query_results/*.csv           result of each SQL query
       dashboard/data/*.csv                  clean tables for Power BI
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "registrations.sqlite"
IMG = ROOT / "images"
REPORTS = ROOT / "reports"
QOUT = REPORTS / "query_results"
PBI = ROOT / "dashboard" / "data"

# ---- palette: validated categorical order, fixed per entity (never cycled) -----------------
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
FUEL_COLORS = {                      # slot 1..5 of the reference palette
    "Electric (BEV)": "#2a78d6",
    "Plug-in hybrid": "#eb6834",
    "Hybrid (no plug-in)": "#1baf7a",
    "Diesel": "#eda100",
    "Petrol & other": "#e87ba4",
}
ORIGIN_COLORS = {
    "Germany": "#2a78d6", "Other Europe": "#eb6834", "Japan/Korea": "#1baf7a",
    "China": "#eda100", "USA": "#e87ba4",
}
BLUE = "#2a78d6"


def style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "font.size": 10, "axes.titlesize": 13, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "legend.frameon": False,
    })


def run_queries(con: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    sql = (ROOT / "sql" / "analysis_queries.sql").read_text()
    parts = re.split(r"^-- name:\s*(\w+)\s*$", sql, flags=re.M)
    out = {}
    QOUT.mkdir(parents=True, exist_ok=True)
    for name, body in zip(parts[1::2], parts[2::2]):
        df = pd.read_sql(body, con)
        df.to_csv(QOUT / f"{name}.csv", index=False)
        out[name] = df
    return out


def month_label(m: str) -> str:
    return pd.Timestamp(m).strftime("%b %Y")


def source_note(ax_or_fig, latest: str) -> None:
    txt = (f"Source: Kraftfahrt-Bundesamt (KBA), FZ 10.1, new passenger-car registrations in Germany, "
           f"Sep 2024 - {month_label(latest)}. Own calculation.")
    plt.gcf().text(0.01, 0.005, txt, fontsize=7.5, color=INK2, ha="left", va="bottom")


# ------------------------------------------------------------------------ charts ------
def chart_bev_share(trend: pd.DataFrame) -> None:
    t = trend.copy()
    t["m"] = pd.to_datetime(t["month"])
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(t["m"], t["bev_share_pct"], color=BLUE, lw=2, marker="o", ms=4.5,
            markeredgecolor=SURFACE, markeredgewidth=1.5, label="BEV share, monthly")
    ax.plot(t["m"], t["bev_share_3m_avg_pct"], color=INK2, lw=1.5, ls=(0, (4, 3)),
            label="3-month average")
    last = t.iloc[-1]
    ax.annotate(f"{last['bev_share_pct']:.1f}%", (last["m"], last["bev_share_pct"]),
                textcoords="offset points", xytext=(0, 9), ha="center", color=INK, fontweight="bold")
    first = t.iloc[0]
    ax.annotate(f"{first['bev_share_pct']:.1f}%", (first["m"], first["bev_share_pct"]),
                textcoords="offset points", xytext=(0, 9), ha="center", color=INK)
    ax.set_ylim(0, max(40, t["bev_share_pct"].max() + 6))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%Y"))
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=(1, 3, 5, 7, 9, 11)))
    ax.grid(axis="x", visible=False)
    ax.set_title("Battery-electric cars: share of new registrations in Germany")
    ax.legend(loc="upper left", ncols=2)
    source_note(ax, t["month"].iloc[-1])
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(IMG / "01_bev_share_trend.png", dpi=170)
    plt.close(fig)


def chart_fuel_mix(mix: pd.DataFrame) -> None:
    m = mix.copy()
    m["m"] = pd.to_datetime(m["month"])
    cols = [("bev", "Electric (BEV)"), ("phev", "Plug-in hybrid"), ("hev", "Hybrid (no plug-in)"),
            ("diesel", "Diesel"), ("petrol_other", "Petrol & other")]
    fig, ax = plt.subplots(figsize=(10, 5.4))
    bottom = pd.Series(0.0, index=m.index)
    x = range(len(m))
    for key, label in cols:
        share = 100 * m[key] / m["total"]
        ax.bar(x, share, bottom=bottom, color=FUEL_COLORS[label], label=label,
               width=0.82, edgecolor=SURFACE, linewidth=1.5)
        bottom += share
    ax.set_xticks(list(x))
    ax.set_xticklabels([d.strftime("%b\n%y") if (i % 2 == 0) else "" for i, d in enumerate(m["m"])])
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.grid(axis="x", visible=False)
    ax.set_title("Fuel mix of new registrations in Germany")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncols=5, fontsize=9)
    source_note(ax, m["month"].iloc[-1])
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(IMG / "02_fuel_mix.png", dpi=170)
    plt.close(fig)


def chart_top_brands(rank: pd.DataFrame) -> None:
    r = rank.head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.barh(r["brand"], r["bev"], color=BLUE, height=0.62)
    for y, (bev, sh) in enumerate(zip(r["bev"], r["bev_share_in_brand_pct"])):
        ax.text(bev + r["bev"].max() * 0.01, y, f"{bev:,.0f}  ({sh:.0f}% of the brand's sales)",
                va="center", fontsize=9, color=INK)
    ax.set_xlim(0, r["bev"].max() * 1.45)
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    ax.grid(axis="y", visible=False)
    ax.set_title("Top 12 brands by electric-car registrations, last 12 months")
    source_note(ax, pd.read_csv(QOUT / "bev_trend.csv")["month"].iloc[-1])
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(IMG / "03_top_brands_bev.png", dpi=170)
    plt.close(fig)


def chart_shift(shift: pd.DataFrame, latest: str) -> None:
    # drop brands that are fully electric in both windows (nothing to compare), then show
    # the biggest risers plus the brands that moved the other way
    shift = shift[~((shift["bev_share_prev_pct"] >= 99) & (shift["bev_share_now_pct"] >= 99))]
    s = pd.concat([shift.head(9), shift[shift["change_pp"] < -1].tail(3)]).drop_duplicates("brand").sort_values("change_pp")
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.hlines(s["brand"], s["bev_share_prev_pct"], s["bev_share_now_pct"], color=GRID, lw=3, zorder=1)
    ax.scatter(s["bev_share_prev_pct"], s["brand"], color=INK2, s=55, zorder=2,
               edgecolor=SURFACE, linewidth=1.5, label="6 months, one year earlier")
    ax.scatter(s["bev_share_now_pct"], s["brand"], color=BLUE, s=70, zorder=3,
               edgecolor=SURFACE, linewidth=1.5, label="latest 6 months")
    for b, prev, now, ch in zip(s["brand"], s["bev_share_prev_pct"], s["bev_share_now_pct"], s["change_pp"]):
        ax.text(max(prev, now) + 1.2, b, f"{ch:+.1f} pp", va="center", fontsize=9, color=INK)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_xlim(0, max(s["bev_share_now_pct"].max(), s["bev_share_prev_pct"].max()) + 12)
    ax.grid(axis="y", visible=False)
    ax.set_title("Which brands became more electric? BEV share of each brand's sales")
    ax.legend(loc="upper right")
    source_note(ax, latest)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(IMG / "04_electrification_shift.png", dpi=170)
    plt.close(fig)


def chart_origin(orig: pd.DataFrame, latest: str) -> None:
    o = orig[orig["origin_group"].isin(ORIGIN_COLORS)].copy()
    o["m"] = pd.to_datetime(o["month"])
    piv = o.pivot(index="m", columns="origin_group", values="share_of_month_bev_pct")
    # 3-month average smooths month-to-month noise
    piv = piv.rolling(3, min_periods=1).mean()
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for grp, color in ORIGIN_COLORS.items():
        if grp in piv:
            ax.plot(piv.index, piv[grp], color=color, lw=2, label=grp)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%Y"))
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=(1, 3, 5, 7, 9, 11)))
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, None)
    ax.set_title("Who sells the electric cars? Share of all BEV registrations by brand origin")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncols=5)
    plt.gcf().text(0.01, 0.045, "3-month average. Origin = country of the brand's parent company "
                   "(see data/reference/brand_origin.csv).", fontsize=7.5, color=INK2)
    source_note(ax, latest)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(IMG / "05_bev_by_origin.png", dpi=170)
    plt.close(fig)


# ---------------------------------------------------------------------- findings ------
def write_findings(q: dict[str, pd.DataFrame]) -> str:
    mix, trend = q["monthly_fuel_mix"], q["bev_trend"]
    rank, shift = q["brand_bev_ranking_ltm"], q["brand_electrification_shift"]
    orig, models = q["bev_by_origin"], q["top_bev_models_ltm"]

    latest = mix.iloc[-1]
    ly = mix[mix["month"] == (pd.Timestamp(latest["month"]) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")]
    ly = ly.iloc[0] if len(ly) else None
    end = pd.Timestamp(latest["month"])
    ytd_now = mix[(pd.to_datetime(mix["month"]).dt.year == end.year)]
    ytd_prev = mix[(pd.to_datetime(mix["month"]).dt.year == end.year - 1)
                   & (pd.to_datetime(mix["month"]).dt.month <= end.month)]

    def share(df, col):
        return 100 * df[col].sum() / df["total"].sum()

    lines = [f"# Findings (auto-generated from the data, latest month {month_label(latest['month'])})", ""]
    lines.append(f"1. **Electric share of new cars.** BEVs made up {latest['bev_share_pct']:.1f}% of new "
                 f"registrations in {month_label(latest['month'])}"
                 + (f", up from {ly['bev_share_pct']:.1f}% a year earlier "
                    f"({latest['bev_share_pct'] - ly['bev_share_pct']:+.1f} percentage points)." if ly is not None else "."))
    if len(ytd_prev):
        lines.append(f"2. **Year to date.** Jan-{end.strftime('%b')} {end.year}: BEV share "
                     f"{share(ytd_now, 'bev'):.1f}% vs {share(ytd_prev, 'bev'):.1f}% in the same months of "
                     f"{end.year - 1}; BEV units {100 * (ytd_now['bev'].sum() / ytd_prev['bev'].sum() - 1):+.0f}%, "
                     f"while total registrations changed {100 * (ytd_now['total'].sum() / ytd_prev['total'].sum() - 1):+.1f}%.")
        lines.append(f"3. **Combustion-only cars** (diesel + petrol/other, no electrification) fell from "
                     f"{100 * (ytd_prev['diesel'].sum() + ytd_prev['petrol_other'].sum()) / ytd_prev['total'].sum():.1f}% to "
                     f"{100 * (ytd_now['diesel'].sum() + ytd_now['petrol_other'].sum()) / ytd_now['total'].sum():.1f}% "
                     f"of registrations (same months). Plug-in hybrids: {share(ytd_prev, 'phev'):.1f}% -> {share(ytd_now, 'phev'):.1f}%.")
    top3 = rank.head(3)
    lines.append("4. **Who sells the most BEVs (last 12 months):** " + "; ".join(
        f"{r.brand} {r.bev:,.0f} ({r.share_of_all_bev_pct:.1f}% of all BEVs)" for r in top3.itertuples()) + ".")
    mixed = rank[(rank["total"] >= 20000) & (rank["bev_share_in_brand_pct"] < 99)]
    best_share = mixed.sort_values("bev_share_in_brand_pct", ascending=False).iloc[0]
    pure = rank[rank["bev_share_in_brand_pct"] >= 99]
    pure_txt = (f" Pure-electric makers in the top 20: {', '.join(pure['brand'])}." if len(pure) else "")
    lines.append(f"5. **Most electric volume brand that also sells combustion cars** (at least 20,000 sales): "
                 f"{best_share['brand']} with {best_share['bev_share_in_brand_pct']:.0f}% BEVs.{pure_txt}")
    if len(shift):
        up = shift.iloc[0]
        lines.append(f"6. **Biggest jump in BEV share** (latest 6 months vs a year earlier, brands with >= 3,000 sales "
                     f"in both windows): {up['brand']} {up['bev_share_prev_pct']:.1f}% -> {up['bev_share_now_pct']:.1f}% "
                     f"({up['change_pp']:+.1f} pp).")
    ch_now = orig[(orig["month"] == latest["month"]) & (orig["origin_group"] == "China")]
    ch_prev = orig[(orig["month"] == (end - pd.DateOffset(years=1)).strftime("%Y-%m-%d")) & (orig["origin_group"] == "China")]
    if len(ch_now) and len(ch_prev):
        lines.append(f"7. **Chinese-parent brands** (incl. MG, Volvo/Polestar via Geely, BYD) delivered "
                     f"{ch_now['share_of_month_bev_pct'].iloc[0]:.1f}% of BEVs in {month_label(latest['month'])} vs "
                     f"{ch_prev['share_of_month_bev_pct'].iloc[0]:.1f}% a year earlier.")
    m1 = models.iloc[0]
    lines.append(f"8. **Best-selling electric model series (last 12 months):** {m1['brand']} {m1['model']} "
                 f"with {m1['bev_registrations']:,.0f} registrations.")

    lines += ["", "## How to read these numbers", "",
              "- Source: KBA table FZ 10.1, monthly files. Each month's total was checked against KBA's own "
              "'NEUZULASSUNGEN INSGESAMT' line; all months match.",
              "- Fuel categories are built to not overlap: BEV, plug-in hybrid, hybrid without plug-in, diesel, and "
              "'petrol & other' (= total minus the other four, because the file has no petrol column).",
              "- KBA counts mild hybrids as hybrids, so 'Hybrid (no plug-in)' includes 48V mild hybrids.",
              "- Brand origin is judged by the parent company and is editable in data/reference/brand_origin.csv.",
              "- Registrations are not sales: fleet, dealer and self-registrations are included, and figures for a "
              "month can be revised later by KBA."]
    text = "\n".join(lines) + "\n"
    (REPORTS / "findings.md").write_text(text)
    return text


# ------------------------------------------------------------------ power bi export ---
def export_powerbi(con: sqlite3.Connection) -> None:
    PBI.mkdir(parents=True, exist_ok=True)
    fact = pd.read_sql("select month, brand, model, fuel_key, fuel_category, registrations from registrations", con)
    fact.to_csv(PBI / "fact_registrations.csv", index=False)
    pd.read_sql("select * from dim_brand", con).to_csv(PBI / "dim_brand.csv", index=False)
    months = pd.date_range(fact["month"].min(), fact["month"].max(), freq="MS")
    pd.DataFrame({
        "month": months.strftime("%Y-%m-%d"), "month_index": range(len(months)),
        "year": months.year, "month_number": months.month,
        "month_name": months.strftime("%b"), "year_month": months.strftime("%Y-%m"),
    }).to_csv(PBI / "dim_month.csv", index=False)
    order = {"Electric (BEV)": 1, "Plug-in hybrid": 2, "Hybrid (no plug-in)": 3, "Diesel": 4, "Petrol & other": 5}
    pd.DataFrame({"fuel_category": list(order), "sort_order": list(order.values()),
                  "color": [FUEL_COLORS[k] for k in order]}).to_csv(PBI / "dim_fuel.csv", index=False)


def main() -> None:
    if not DB.exists():
        raise SystemExit("Run  python src/build_dataset.py  first.")
    style()
    IMG.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    q = run_queries(con)
    latest = q["monthly_fuel_mix"]["month"].iloc[-1]
    chart_bev_share(q["bev_trend"])
    chart_fuel_mix(q["monthly_fuel_mix"])
    chart_top_brands(q["brand_bev_ranking_ltm"])
    chart_shift(q["brand_electrification_shift"], latest)
    chart_origin(q["bev_by_origin"], latest)
    export_powerbi(con)
    print(write_findings(q))
    print("Charts in images/, findings in reports/findings.md, Power BI tables in dashboard/data/")


if __name__ == "__main__":
    main()
