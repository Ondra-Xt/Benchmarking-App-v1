# Shower Drainage System Comparator — v2 data architecture

Interactive Streamlit application for filtering, benchmarking, and auditing shower drainage systems from multiple manufacturer Excel masters.

Patch 10 keeps the existing application workflow but adds a schema-aware v2 data layer so the same app can work with legacy masters and current canonical v2 masters, including point drains and integrated shower elements.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

## Data source strategy

The application reads every `.xlsx` workbook stored in `data/`. The intended production workflow is:

```text
canonical FINAL v2 manufacturer Excel masters in GitHub
                    ↓
              v2_excel_loader.py
                    ↓
       normalised in-memory benchmark model
                    ↓
                Streamlit UI
```

A shared multi-gigabyte SQLite database is not required by the web app.

### Supported legacy layers

Legacy workbooks can continue to expose the historical physical sheets:

- `01_Flat_Input`
- `02_BOM_Components`
- `03_Evidence`

### Supported v2 logical layers

Canonical v2 workbooks may expose these as physical sheets or package secondary layers in `80_Secondary_Archive_Manifest` + `81_Secondary_Archive_Payload`:

- `01_Flat_Input`
- `02_BOM_Components`
- `03_Evidence`
- `04_Price_Observations`
- `05_Missing_Parts`
- `06_Hydraulic_Observations`
- `07_Technical_Observations`
- `08_System_Technical_Audit`
- `09_Exact_Identity_Lifecycle`
- `10_Record_Lifecycle`
- `11_Package_Contents`
- `12_Component_Compat_Graph`
- `13_Regional_Provenance`
- `14_Controlled_Gaps`

Physical sheets take precedence. The compressed archive fills only logical layers that are not already present physically, preventing double loading.

## Product classification

The application now separates two concepts:

- **Drain form** — `linear`, `point`, or the retained legacy `integrated_surface` class.
- **Solution type** — for example `drainage_system`, `integrated_shower_element`, `integrated_shower_surface`, or `heat_recovery_shower_system`.

This allows an integrated shower element to remain an integrated solution while still being benchmarked correctly as either a linear or point drainage system.

Classification is controlled by `config/classification_rules.csv` and does not rewrite source workbooks.

## Category-aware geometry

`drain_element_length_mm` is the application comparison field for drain length:

- linear legacy systems use the verified/normalised drain length already available to the app;
- v2 integrated linear systems prefer explicit `channel_length_mm` when present;
- point drains intentionally receive no drain-element length, preventing a shower-panel dimension from being treated as a drain length.

Point-drain filters and detail views can use explicit v2 fields such as:

- `point_top_shape`
- `visible_grate_diameter_mm`
- `overall_body_diameter_mm`
- `drain_position`
- `drain_location`
- `water_seal_mm`
- outlet DN and orientation

Only explicit, unambiguous record-level observations are projected into the application view. Existing explicit `01_Flat_Input` values are not overwritten.

## Mandatory filter behaviour

Filters follow the sidebar order: drain form and completeness → manufacturer → solution type → length → primary flow → installation height → point geometry → materials/standards. Each control offers values from the candidates admitted by the preceding controls. Ranking uses this same eligibility pipeline.

- Upstream changes retain valid choices and remove stale ones. If none of the previous choices remain available, the control resets to all available options with a caption. An unrestricted selection stays unrestricted as the available options change.
- Intentionally clearing a multiselect selects no products. The audit records `None selected`; it does not describe that selection as `all`.
- A mandatory numeric or length requirement with no supported values returns no products. Activating a requirement never silently disables it.
- Primary flow uses a 0.01 l/s slider step with outward-rounded bounds. The requirement filters `flow_rate_primary_lps`; ranking by flow at 20 mm is a separate metric. No hydraulic head conversion is performed.
- Verified length rules retain priority, including deliberately blocked families. Where no family rule applies, an explicit standalone drain length or integrated system's explicit `channel_length_mm` can match that **exact declared size only**. It is labelled `declared_exact_only`, without asserting a fixed product or inferring a shortening range. An integrated shower element's overall dimension never substitutes for its channel length.

`filter_widgets.py` reconciles control state before rendering the widgets. `test_filter_pipeline.py` covers actual Streamlit control interactions and filtering of the bundled v2 masters.

## Prices

`04_Price_Observations` remains available in full in the record detail view. For the existing leaderboard price field, the adapter only fills a missing flat price when exact record-level observations have a single currency. The minimum exact record-level observed price is then used, matching the application's historical group-price policy. Existing flat prices are preserved.

No currency conversion is performed.

## Reference comparison

Reference comparison is now category-aware:

- drain form is always matched;
- standardised solution type is matched by default when known;
- source `product_category` is optional because manufacturer-specific category labels may differ;
- drain-element length is used instead of overall product length;
- point drains therefore do not get an irrelevant length tolerance unless an explicit comparable drain-element length exists.

## Record detail

The detail view exposes separate tabs for:

1. BOM / package contents
2. Technical observations
3. Hydraulic observations
4. Prices
5. Evidence
6. Lifecycle / controlled gaps
7. Raw record

This keeps the source v2 layers auditable rather than flattening all data irreversibly into one table.

## Configuration

- `config/classification_rules.csv` — product classification and leaderboard visibility.
- `config/length_rules.csv` — verified legacy installable-length rules.

Do not infer new length ranges from family names. Add a rule only when the range is explicitly supported by the source data.

## Tests

Run the regression and v2 integration suite with:

```bash
python -m unittest -v
```

The suite includes ranking/reference regressions, v2 loader/geometry integration and mandatory-filter UI/data regression tests.

## Deployment

See `DEPLOYMENT.md`.
