# Patch 11 — Universal Point-Drain Geometry & Parameter Registry

## Scope

Patch 11 implements Q1 only: a manufacturer-neutral point-drain geometry model for the Excel-backed Streamlit comparator. It does not yet add the Q2 coverage dashboard or the Q3 manufacturer-by-manufacturer audit.

## Main changes

- Added `point_geometry.py` as the single registry for point-drain parameters used by the data layer and UI.
- Added explicit support for rectangular/square and round point-drain geometry:
  - nominal top length / width / diameter
  - visible grate length / width / diameter
  - grate diameter
  - visible cover length / width / diameter
  - body diameter
  - frame / tray-hole / installation / outlet geometry fields
- Added canonical application fields:
  - `point_grate_length_mm`
  - `point_grate_width_mm`
  - `point_grate_diameter_mm`
  - `point_cover_length_mm`
  - `point_cover_width_mm`
  - `point_cover_diameter_mm`
  - `point_body_diameter_mm`
- Added compact display fields:
  - `point_top_size`
  - `point_grate_size`
  - `point_cover_size`
  - `point_body_size`
- Round geometry uses explicit diameter when available (`Ø120 mm`) instead of displaying a misleading `120 × 120 mm` bounding box.
- Generic `length_mm` / `width_mm` are never reinterpreted as grate or top geometry.
- Equivalent source fields are coalesced only when their explicit numeric values agree. Conflicts stay blank and are traceable through `*_source` columns.
- Expanded point-drain mandatory filters dynamically from the registry. Filters appear only when the active selection contains explicit values.
- Ranking, technical-product tables, exact variant tables, reference comparison and advanced scoring now show point geometry through manufacturer-neutral summary fields.
- Reference-product comparison now exposes optional point geometry tolerances and optional exact point-top-shape matching.
- Point-product selector labels prefer explicit grate/top size instead of generic overall length.
- Expanded technical-observation projection to recognise the registry fields and `value_raw` in addition to the previous value columns.
- Point geometry is included in derived technical hierarchy identity so physically different point variants are not silently collapsed when explicit database hierarchy keys are absent.

## Explicit-only rule

Patch 11 does not infer geometry from product-family names or unrelated dimensions. In particular:

- `100 × 100 mm` in generic product dimensions is not automatically called a visible grate size.
- a square shape is not inferred from equal length and width;
- a central drain position is not inferred from the fact that a product is a point drain;
- conflicting equivalent source fields are not resolved by choosing one silently.

## Dallmer v2 validation

Validated against `DALLMER_FINAL_Master_Complete_v2_TECHNICAL_LOCK.xlsx`:

- point-drain systems: 392
- explicit visible grate length: 356 / 392
- explicit visible grate width: 356 / 392
- explicit grate diameter: 16 / 392
- explicit point-top shape: 38 / 392
- canonical/display `point_top_size`: 38 / 392
- canonical/display `point_grate_size`: 358 / 392
- 34 systems have generic declared length/width but no explicit point-grate geometry; these correctly remain without `point_grate_size`.

## Regression validation

- Dallmer + WEDI mixed-load smoke test: PASS
- WEDI point systems preserved: 671
- Dallmer point systems preserved: 392
- Python syntax compilation: PASS
- Unit/integration tests: 41 / 41 PASS
- Existing WEDI archive-layer regression tests remain PASS.

## Data handling

No source Excel workbook is modified by Patch 11. The patch is code-only and is safe to apply over a repository whose `data/` folder already contains the selected canonical v2 masters.
