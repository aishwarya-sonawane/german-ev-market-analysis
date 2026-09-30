-- Schema for the German new-car registrations analysis (SQLite).
-- One row per month x brand x model series x fuel category.
-- fuel_key: bev | phev | hev | diesel | petrol_other
--   "petrol_other" is derived: total - diesel - BEV - PHEV - HEV
--   (also contains small volumes of gas, hydrogen and other drives).

CREATE TABLE registrations (
    month          TEXT    NOT NULL,   -- first day of the month, 'YYYY-MM-01'
    brand          TEXT    NOT NULL,   -- KBA brand name, upper case; SsangYong merged into KGM
    model          TEXT    NOT NULL,   -- KBA model series ('SONSTIGE' = other models)
    fuel_key       TEXT    NOT NULL,
    fuel_category  TEXT    NOT NULL,
    registrations  INTEGER NOT NULL CHECK (registrations >= 0),
    PRIMARY KEY (month, brand, model, fuel_key)
);

CREATE INDEX idx_reg_month ON registrations (month);
CREATE INDEX idx_reg_brand ON registrations (brand, month);

-- Brand -> parent-company origin. Judgement-based, editable (data/reference/brand_origin.csv).
CREATE TABLE dim_brand (
    brand        TEXT PRIMARY KEY,
    origin_group TEXT NOT NULL,
    note         TEXT
);
