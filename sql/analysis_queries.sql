-- Analysis queries. Each block starts with "-- name: <query_name>".
-- They run in SQLite via  python src/run_analysis.py  (or open the .sqlite in any SQL tool).
-- "Latest month" is always taken from the data, so nothing is hard-coded.

-- name: monthly_fuel_mix
-- Registrations and share by fuel category for each month, plus two useful groupings.
SELECT
    month,
    SUM(registrations)                                                       AS total,
    SUM(CASE WHEN fuel_key = 'bev'          THEN registrations END)          AS bev,
    SUM(CASE WHEN fuel_key = 'phev'         THEN registrations END)          AS phev,
    SUM(CASE WHEN fuel_key = 'hev'          THEN registrations END)          AS hev,
    SUM(CASE WHEN fuel_key = 'diesel'       THEN registrations END)          AS diesel,
    SUM(CASE WHEN fuel_key = 'petrol_other' THEN registrations END)          AS petrol_other,
    ROUND(100.0 * SUM(CASE WHEN fuel_key = 'bev'  THEN registrations END) / SUM(registrations), 1) AS bev_share_pct,
    ROUND(100.0 * SUM(CASE WHEN fuel_key = 'phev' THEN registrations END) / SUM(registrations), 1) AS phev_share_pct,
    ROUND(100.0 * SUM(CASE WHEN fuel_key = 'hev'  THEN registrations END) / SUM(registrations), 1) AS hev_share_pct,
    ROUND(100.0 * SUM(CASE WHEN fuel_key IN ('bev','phev') THEN registrations END) / SUM(registrations), 1) AS plug_in_share_pct,
    ROUND(100.0 * SUM(CASE WHEN fuel_key IN ('diesel','petrol_other') THEN registrations END) / SUM(registrations), 1) AS combustion_only_share_pct
FROM registrations
GROUP BY month
ORDER BY month;

-- name: bev_trend
-- BEV share with a 3-month moving average and the change vs the same month a year earlier
-- (window functions). Year-on-year is used because car sales are seasonal.
WITH m AS (
    SELECT month,
           SUM(registrations) AS total,
           SUM(CASE WHEN fuel_key = 'bev' THEN registrations END) AS bev
    FROM registrations
    GROUP BY month
), s AS (
    SELECT month, total, bev, 100.0 * bev / total AS share FROM m
)
SELECT
    month, total, bev,
    ROUND(share, 1)                                                                AS bev_share_pct,
    ROUND(AVG(share) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS bev_share_3m_avg_pct,
    ROUND(share - LAG(share, 12) OVER (ORDER BY month), 1)                         AS bev_share_yoy_change_pp,
    ROUND(100.0 * (bev - LAG(bev, 12) OVER (ORDER BY month)) / LAG(bev, 12) OVER (ORDER BY month), 1) AS bev_units_yoy_pct
FROM s
ORDER BY month;

-- name: brand_bev_ranking_ltm
-- Last 12 months: which brands sell the most electric cars, and how electric is each brand?
WITH latest AS (SELECT MAX(month) AS m FROM registrations),
b AS (
    SELECT r.brand,
           SUM(r.registrations)                                            AS total,
           SUM(CASE WHEN r.fuel_key = 'bev'  THEN r.registrations END)     AS bev,
           SUM(CASE WHEN r.fuel_key = 'phev' THEN r.registrations END)     AS phev
    FROM registrations r, latest
    WHERE r.month > date(latest.m, '-12 months')
      AND r.brand <> 'SONSTIGE'
    GROUP BY r.brand
), t AS (SELECT SUM(bev) AS all_bev FROM b)
SELECT
    RANK() OVER (ORDER BY b.bev DESC)                    AS rank_bev,
    b.brand,
    d.origin_group,
    b.bev,
    ROUND(100.0 * b.bev / t.all_bev, 1)                  AS share_of_all_bev_pct,
    b.total,
    ROUND(100.0 * b.bev / b.total, 1)                    AS bev_share_in_brand_pct,
    ROUND(100.0 * (b.bev + b.phev) / b.total, 1)         AS plug_in_share_in_brand_pct
FROM b
JOIN t
LEFT JOIN dim_brand d ON d.brand = b.brand
WHERE b.bev > 0
ORDER BY b.bev DESC
LIMIT 20;

-- name: brand_electrification_shift
-- Who has become more electric? BEV share of each brand in the latest 6 months vs the same
-- 6 months one year earlier. Brands need at least 3,000 registrations in both windows,
-- so tiny volumes do not create noise.
WITH latest AS (SELECT MAX(month) AS m FROM registrations),
w AS (
    SELECT r.brand,
           CASE WHEN r.month >  date(latest.m, '-6 months')  THEN 'now'
                WHEN r.month >  date(latest.m, '-18 months')
                 AND r.month <= date(latest.m, '-12 months') THEN 'prev' END AS win,
           r.registrations, r.fuel_key
    FROM registrations r, latest
    WHERE r.brand <> 'SONSTIGE'
), agg AS (
    SELECT brand, win,
           SUM(registrations) AS total,
           SUM(CASE WHEN fuel_key = 'bev' THEN registrations END) AS bev
    FROM w WHERE win IS NOT NULL
    GROUP BY brand, win
)
SELECT
    n.brand,
    d.origin_group,
    p.total                                            AS total_prev_6m,
    n.total                                            AS total_now_6m,
    ROUND(100.0 * p.bev / p.total, 1)                  AS bev_share_prev_pct,
    ROUND(100.0 * n.bev / n.total, 1)                  AS bev_share_now_pct,
    ROUND(100.0 * n.bev / n.total - 100.0 * p.bev / p.total, 1) AS change_pp
FROM agg n
JOIN agg p ON p.brand = n.brand AND p.win = 'prev'
LEFT JOIN dim_brand d ON d.brand = n.brand
WHERE n.win = 'now' AND n.total >= 3000 AND p.total >= 3000
ORDER BY change_pp DESC;

-- name: bev_by_origin
-- Monthly BEV registrations by brand origin group (parent-company view) and each group's
-- share of all BEVs that month.
WITH x AS (
    SELECT r.month, COALESCE(d.origin_group, 'Other / JV') AS origin_group,
           SUM(r.registrations) AS bev
    FROM registrations r
    LEFT JOIN dim_brand d ON d.brand = r.brand
    WHERE r.fuel_key = 'bev'
    GROUP BY r.month, origin_group
)
SELECT month, origin_group, bev,
       ROUND(100.0 * bev / SUM(bev) OVER (PARTITION BY month), 1) AS share_of_month_bev_pct
FROM x
ORDER BY month, bev DESC;

-- name: top_bev_models_ltm
-- Best-selling electric model series over the last 12 months.
WITH latest AS (SELECT MAX(month) AS m FROM registrations)
SELECT
    RANK() OVER (ORDER BY SUM(r.registrations) DESC) AS rank_bev,
    r.brand, r.model,
    SUM(r.registrations) AS bev_registrations
FROM registrations r, latest
WHERE r.fuel_key = 'bev'
  AND r.month > date(latest.m, '-12 months')
  AND r.model <> 'SONSTIGE'
GROUP BY r.brand, r.model
ORDER BY bev_registrations DESC
LIMIT 15;

-- name: brand_fuel_mix_latest_month
-- Fuel mix of every brand with at least 1,000 registrations in the latest month.
WITH latest AS (SELECT MAX(month) AS m FROM registrations)
SELECT
    r.brand,
    SUM(r.registrations) AS total,
    ROUND(100.0 * SUM(CASE WHEN r.fuel_key = 'bev'          THEN r.registrations END) / SUM(r.registrations), 1) AS bev_pct,
    ROUND(100.0 * SUM(CASE WHEN r.fuel_key = 'phev'         THEN r.registrations END) / SUM(r.registrations), 1) AS phev_pct,
    ROUND(100.0 * SUM(CASE WHEN r.fuel_key = 'hev'          THEN r.registrations END) / SUM(r.registrations), 1) AS hev_pct,
    ROUND(100.0 * SUM(CASE WHEN r.fuel_key = 'diesel'       THEN r.registrations END) / SUM(r.registrations), 1) AS diesel_pct,
    ROUND(100.0 * SUM(CASE WHEN r.fuel_key = 'petrol_other' THEN r.registrations END) / SUM(r.registrations), 1) AS petrol_other_pct
FROM registrations r, latest
WHERE r.month = latest.m AND r.brand <> 'SONSTIGE'
GROUP BY r.brand
HAVING SUM(r.registrations) >= 1000
ORDER BY total DESC;
