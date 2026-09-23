# Shower Drainage Comparator — User Guide

## What the application does

The application first applies mandatory eligibility requirements and then benchmarks the remaining technical products. Exact articles, finishes, and cosmetic variants can be grouped behind one technical product while the exact source records remain available for audit.

The current application supports both linear and point drainage. Integrated shower elements are classified on two axes: their solution type and their physical drain form.

## Quick start

1. In **Mandatory requirements**, choose the **Drain form**: linear, point, or a retained legacy class.
2. Optionally choose a **Solution type**, manufacturer, hydraulic, dimensional, material, standard, or sealing requirements.
3. For point drains, use the point-specific geometry filters that appear when explicit data is available.
4. Choose a ranking method.
5. Open product details to review exact articles, BOM/package contents, technical and hydraulic observations, price observations, evidence, lifecycle status, and controlled gaps.

## Drain form vs. solution type

These are intentionally separate.

Examples:

- a Fundo Riolito-style integrated shower element can be `linear` + `integrated_shower_element`;
- a Fundo Primo-style integrated shower element can be `point` + `integrated_shower_element`;
- a conventional floor drain can be `point` + `drainage_system`.

This avoids treating all integrated shower elements as one drain geometry.

## Linear-drain length

The comparison field is **Drain element length**. It represents the drainage element, not automatically the overall shower-board or tray dimension.

For v2 integrated linear systems, explicit channel length is preferred when available. Verified legacy adjustable ranges remain controlled by `config/length_rules.csv`.

## Point-drain parameters

Depending on the current data, the point filter/detail view may expose:

- top shape,
- visible grate diameter,
- overall body diameter,
- drain position/location,
- outlet DN,
- outlet orientation,
- installation height,
- water seal,
- hydraulic values.

A missing value remains missing. The application does not infer a point-drain dimension from unrelated product dimensions.

## Mandatory requirements

Mandatory requirements determine eligibility only. They do not award points.

A product with no explicit value for an active mandatory field is normally excluded from that constrained result set rather than being treated as zero.

## Ranking modes

### Single-parameter ranking

Use when one parameter is the principal criterion, for example maximum flow or minimum installation height.

### Multi-parameter ranking

Select multiple criteria and set their relative weights. Products missing required selected metrics are handled according to the ranking mode's existing policy.

### Reference-product comparison

The reference creates a technically comparable candidate set; it does not receive a scoring bonus.

- drain form is always matched;
- standardised solution type is matched by default when known;
- source product category is optional because source labels can differ by manufacturer;
- outlet DN and V4A status can be required;
- length tolerance uses **drain-element length**, not overall product length;
- flow, installation height, and water seal can be constrained independently.

For a point drain with no meaningful drain-element length, the length constraint is disabled rather than using a shower-board dimension.

### Advanced weighted scoring

The existing advanced scoring framework remains available for flow, installation height, V4A, price, and finish/colour count, including its missing-data policies.

## Product detail tabs

The v2-aware detail view can show:

- **BOM / package** — component relationships and package contents;
- **Technical** — record-level technical observations;
- **Hydraulics** — hydraulic observations and declared bases;
- **Prices** — exact price observations;
- **Evidence** — source evidence;
- **Lifecycle / gaps** — lifecycle/currentness, system technical audit, and controlled gaps;
- **Raw record** — the consolidated flat source record.

## Data architecture status

The main page contains a **Loaded data architecture** expander. Use it to verify how many records and logical v2 layers were loaded from each workbook and whether a workbook was read from physical sheets or its compressed secondary archive.

## Data updates

Normal manufacturer updates should be made by replacing/adding the canonical FINAL Excel master under `data/`. The app should not require conversion to the combined SQLite database for Streamlit deployment.
