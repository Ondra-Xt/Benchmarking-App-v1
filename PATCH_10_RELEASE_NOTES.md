# Patch 10 — V2 Data Architecture + Point Drain Support

## Objective

Preserve the working benchmarking application while removing its dependence on a linear-drain-only flat schema. The app can now consume canonical v2 manufacturer masters directly from GitHub/Streamlit and expose point-drain data without requiring the multi-gigabyte combined SQLite database.

## Main changes

### 1. Universal v2 Excel loader

Added `v2_excel_loader.py`.

It supports:

- legacy physical `01/02/03` sheets;
- physical v2 logical layers when present;
- compressed v2 secondary archive payloads;
- manifest/decoded row-count validation;
- source-workbook provenance;
- compatibility aliases required by existing UI/audit code.

Physical sheets take precedence over archive copies.

### 2. Expanded in-memory master model

`MasterData` now retains prices, hydraulics, technical observations, lifecycle, technical audit, package contents, compatibility, regional provenance, controlled gaps, and workbook metadata in addition to the original flat/BOM/evidence layers.

### 3. Explicit-only v2 application projection

Selected technical/evidence observations are projected to the flat application view only when the record/field value is unambiguous. Existing flat values are preserved. No family-level guess or geometry inference is performed.

### 4. Drain form × solution type

Classification now separates physical drain form from solution type. This is required for products such as integrated shower elements that may contain either linear or point drainage.

### 5. Point-drain UI

Point-specific filters/details were added for fields such as top shape, visible grate diameter, body diameter, drain position/location, water seal, outlet DN, and outlet orientation when supported by the data.

### 6. Drain-element length semantics

The application now uses `drain_element_length_mm` for length comparison. Point drains intentionally have no drain-element length. Integrated linear WEDI systems can use explicit channel length instead of the overall shower-element dimension.

Reference-product comparison was updated to the same semantics.

### 7. V2 detail/audit tabs

Record details now expose BOM/package, technical, hydraulics, prices, evidence, lifecycle/gaps, and raw record tabs.

### 8. Price observation integration

Exact record-level v2 price observations can fill a missing flat price only when currency is unambiguous. Source observations remain visible separately. No FX conversion is performed.

### 9. Backward compatibility

The legacy Viega, Dallmer, and Hansgrohe masters remain loadable alongside WEDI v2. Existing ranking modes, hierarchy grouping, downloads, and reference comparison logic are retained.

## WEDI validation

Using `WEDI_FINAL_v2_TECHNICAL_LOCK.xlsx`:

- 2,142 flat records loaded;
- 1,398 systems and 744 components;
- 3,597 BOM relations;
- 36,117 evidence rows;
- 794 price observations;
- 1,234 hydraulic observations;
- 23,639 technical observations;
- all 1,398 WEDI systems classify to a physical drain form: 727 linear and 671 point;
- WEDI solution types: 1,374 integrated shower elements, 22 drainage systems, 2 heat-recovery shower systems;
- point systems do not receive a false drain-element length;
- 720 WEDI linear systems expose explicit channel length in the app view.

## Regression validation

Mixed-data smoke test with four bundled workbooks:

- 12,076 flat records;
- 30,465 BOM rows;
- 136,854 evidence rows;
- 795 price observations;
- 1,234 hydraulic observations;
- 23,639 technical observations;
- no loader warnings.

Automated tests: **35/35 passed**.

Static Python compilation of `app.py`, `drainage_data.py`, and `v2_excel_loader.py`: **PASS**.

## Runtime note

The execution environment used to build this patch does not have the Streamlit package installed, so a live browser render was not started here. The deployment requirements already pin Streamlit, and the application modules pass compilation plus data/regression tests. A local/Streamlit smoke launch is the final deployment check.
