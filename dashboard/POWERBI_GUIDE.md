# Power BI dashboard: build guide

The tables in `dashboard/data/` are ready to load. Build the report in Power BI Desktop (Windows) or the Power BI service.
Nothing in this folder is a finished `.pbix`; follow the steps and save your own file here as `german_ev_market.pbix`.

## 1. Load the tables
Get data -> Text/CSV, load all four files from `dashboard/data/`:

| Table | Rows describe | Key columns |
|---|---|---|
| `fact_registrations` | month x brand x model x fuel | `month`, `brand`, `model`, `fuel_key`, `fuel_category`, `registrations` |
| `dim_month` | one row per month | `month`, `month_index`, `year`, `month_name`, `year_month` |
| `dim_brand` | one row per brand | `brand`, `origin_group`, `note` |
| `dim_fuel` | five fuel categories | `fuel_category`, `sort_order`, `color` |

In Power Query set the data type of `month` (both tables) to **Date**. Sort `dim_fuel[fuel_category]` by `sort_order`.

## 2. Relationships (all many-to-one, single direction)
- `fact_registrations[month]` -> `dim_month[month]`
- `fact_registrations[brand]` -> `dim_brand[brand]`
- `fact_registrations[fuel_category]` -> `dim_fuel[fuel_category]`

## 3. Measures
Create a table called `_Measures` and add:

```DAX
Registrations = SUM ( fact_registrations[registrations] )

BEV Registrations =
CALCULATE ( [Registrations], fact_registrations[fuel_key] = "bev" )

BEV Share % = DIVIDE ( [BEV Registrations], [Registrations] )

-- Same month one year earlier (month_index is 0..23, so this needs no date table tricks)
BEV Share % PY =
VAR _idx = MAX ( dim_month[month_index] )
RETURN
    CALCULATE (
        [BEV Share %],
        ALL ( dim_month ),
        dim_month[month_index] = _idx - 12
    )

BEV Share YoY (pp) = ( [BEV Share %] - [BEV Share % PY] ) * 100

Plug-in Share % =
DIVIDE (
    CALCULATE ( [Registrations], fact_registrations[fuel_key] IN { "bev", "phev" } ),
    [Registrations]
)

Share of All BEVs % =
DIVIDE (
    [BEV Registrations],
    CALCULATE ( [BEV Registrations], ALL ( dim_brand ) )
)
```

Format the `%` measures as percentages with one decimal.

## 4. Pages
**Page 1: Market overview**
- Cards: latest-month `BEV Share %`, `BEV Share YoY (pp)`, `BEV Registrations`.
- Line chart: `dim_month[year_month]` x `BEV Share %` (single line, no second axis).
- 100% stacked column: `year_month` x `Registrations`, legend `fuel_category`. Use the hex colours from `dim_fuel[color]`.

**Page 2: Brands**
- Slicers: `dim_month[year]`, `dim_brand[origin_group]`.
- Bar chart: top 12 `brand` by `BEV Registrations`; add `BEV Share %` in tooltips.
- Table: `brand`, `Registrations`, `BEV Share %`, `Plug-in Share %`. Filter out brand `SONSTIGE` (other brands).

**Page 3: Movers**
- Scatter: x = `Registrations` (last 12 months), y = `BEV Share %`, details = `brand`, size fixed. Small volumes are noisy, so filter to brands with at least 3,000 registrations.

## 5. Finish
- Remove default titles, keep one accent colour, no dual axes, no 3D or pie charts.
- Add a text box: "Source: KBA FZ 10.1, own calculation."
- Export a screenshot of each page to `images/` and link them in the README.
