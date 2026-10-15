# Patch 12 — Mandatory length/flow filtering and cascading controls

## Result

Mandatory filters now use one ordered eligibility pipeline for both widget options and the final candidate set. Switching drain form, manufacturer or solution type reconciles downstream selections. Activated requirements with no supported values return no products rather than silently becoming inactive.

Primary-flow bounds come from eligible upstream products, with a stable 0.01 l/s step. This remains the primary declared flow; the separate ranking metric at 20 mm head is unchanged and no hydraulic head conversion is introduced.

## Length semantics

- Approved family length rules retain priority, including deliberately blocked families.
- When no family rule applies, an explicit standalone drain length or integrated system's explicit channel length supports its exact declared size only. This is labelled `declared_exact_only`, without inferring shortening or asserting that the product is fixed.
- Integrated shower-element overall dimensions never substitute for missing channel length.
- The leaderboard and details show **Supported drain length** next to the declared size. A 1500 mm profile with a verified 800–1500 mm interval can satisfy 800 mm, and the displayed interval explains that result.
- An intentionally empty multiselect remains empty in the result and audit. It is no longer exported as `all`.

## Validation — 2026-10-15

Base: `ab9a9a29187d63491c1026cf5cb2966f19a90f50`.

- `python -m unittest -v`: **57/57 PASS** (41 existing + 16 filter regressions).
- Python compilation: PASS.
- `git diff --check`: PASS.
- Bundled Excel masters and configuration CSVs: unchanged against the base commit.
- Runtime: Python 3.12, Streamlit 1.39.0, pandas 2.2.3, openpyxl 3.1.5.
- Streamlit AppTest exercised the unmodified full application entrypoint and real bundled workbooks, in addition to focused UI tests that isolate eligibility from ranking presentation.

Default complete-system linear scope: **6159** source records. Supported lengths: **5970**; unsupported: **189**. The exact-length fallback enables all **720** WEDI linear records with explicit channel length. The remaining WEDI integrated rows do not inherit an overall shower-element length.

| Independent or combined mandatory requirement | Eligible source records |
|---|---:|
| Length 700–800 mm | 1703 |
| Primary flow 0.8–1.0 l/s, length disabled | 2322 |
| Length 700–800 mm and primary flow 0.8–1.0 l/s | 729 |

These counts precede ranking, missing-ranking-data exclusions, presentation grouping and Top-N. Full-app interactions completed without an exception. The displayed primary flows stayed within the requested interval. Longer declared profiles admitted by the length rule displayed their verified shortening intervals.

## Deployment verification

The public Streamlit URL loaded its password gate. The deployed authenticated session was not used for testing and production has not been updated by this patch. After merging/deploying, sign in and repeat the independent length, independent flow, combined-filter and manufacturer-switch scenarios. No password or authentication code was changed.
