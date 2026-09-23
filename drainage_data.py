"""Data layer for comparing shower drainage systems.

The module does not depend on Streamlit, which makes its rules easy to test
and reuse in another interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from v2_excel_loader import (
    DATASET_SHEETS,
    TEXT_COLUMNS,
    empty_table_map,
    read_workbook_tables,
)
from point_geometry import (
    POINT_DRAIN_CANONICAL_NUMERIC_FIELDS,
    POINT_DRAIN_CANONICAL_SOURCE_FIELDS,
    POINT_DRAIN_COMPOSITE_DISPLAY_FIELDS,
    POINT_DRAIN_NUMERIC_GROUP_FIELDS,
    POINT_DRAIN_OBSERVATION_FIELDS,
    POINT_DRAIN_SEARCH_FIELDS,
    POINT_DRAIN_TEXT_GROUP_FIELDS,
)


# Backward-compatible name used by older tests and documentation.
SHEET_NAMES = DATASET_SHEETS

COMPLETE_CANDIDATE_TYPES = {"assembled_system", "complete_system", "complete_product"}

CLASSIFICATION_ASSIGNMENT_COLUMNS = [
    "mapped_solution_type",
    "mapped_drain_form",
    "mapped_installation_zone",
    "mapped_drainage_mode",
    "mapped_application_scope",
    "leaderboard_visibility",
    "classification_confidence",
]

DRAIN_FORM_LABELS = {
    "linear": "Linear drain",
    "point": "Point drain",
    "integrated_surface": "Integrated shower surface",
}

LENGTH_FILTER_POLICIES = {"yes_range", "yes_exact_only"}

RANKING_REQUEST_SCHEMA_VERSION = "1.1"
RANKING_REQUEST_MODES = {"single_parameter", "multi_parameter"}
RANKING_MISSING_DATA_POLICIES = {"require_complete"}

MANDATORY_FILTER_LABELS = {
    "mapped_drain_form": "Drain type",
    "mapped_solution_type": "Solution type",
    "benchmark_scope": "Benchmark scope",
    "manufacturer_key": "Manufacturer",
    "installable_length_mm": "Drain element length",
    "flow_rate_primary_lps": "Primary flow rate",
    "height_adj_min_mm": "Minimum installation height",
    "material_v4a": "V4A material",
    "din_en_1253_status": "DIN EN 1253",
    "din_en_18534_status": "DIN EN 18534",
    "sealing_fleece_preassembled": "Preassembled sealing fleece",
    "outlet_direction_selectable": "Selectable outlet direction",
    "point_top_shape": "Point-drain top shape",
    "drain_position": "Drain position",
    "drain_location": "Drain location",
    "visible_grate_length_mm": "Visible grate length",
    "visible_grate_width_mm": "Visible grate width",
    "visible_grate_diameter_mm": "Visible grate diameter",
    "grate_diameter_mm": "Grate diameter",
    "point_top_nominal_length_mm": "Nominal top length",
    "point_top_nominal_width_mm": "Nominal top width",
    "point_top_nominal_diameter_mm": "Nominal top diameter",
    "visible_cover_length_mm": "Visible cover length",
    "visible_cover_width_mm": "Visible cover width",
    "cover_diameter_mm": "Cover diameter",
    "overall_body_diameter_mm": "Overall body diameter",
    "body_diameter_mm": "Body diameter",
    "water_seal_mm": "Water seal",
    "outlet_orientation_default": "Outlet orientation",
    "outlet_dn_default": "Outlet DN",
}

ADVANCED_MISSING_DATA_POLICIES = {
    "require_complete",
    "allow_incomplete_zero_score",
    "allow_incomplete_proportional_penalty",
}
REFERENCE_NUMERIC_FIELDS = {
    "drain_element_length_mm": {"label": "Drain element length", "unit": "mm"},
    "nominal_length_mm": {"label": "Overall / legacy nominal length", "unit": "mm"},
    "flow_rate_20mm_lps": {"label": "Flow rate at 20 mm head", "unit": "l/s"},
    "height_adj_min_mm": {"label": "Minimum installation height", "unit": "mm"},
    "water_seal_mm": {"label": "Water seal", "unit": "mm"},
    "point_top_nominal_length_mm": {"label": "Nominal point top length", "unit": "mm"},
    "point_top_nominal_width_mm": {"label": "Nominal point top width", "unit": "mm"},
    "point_top_nominal_diameter_mm": {"label": "Nominal point top diameter", "unit": "mm"},
    "point_grate_length_mm": {"label": "Point grate length", "unit": "mm"},
    "point_grate_width_mm": {"label": "Point grate width", "unit": "mm"},
    "point_grate_diameter_mm": {"label": "Point grate diameter", "unit": "mm"},
    "point_body_diameter_mm": {"label": "Point body diameter", "unit": "mm"},
}

REFERENCE_EXACT_FIELDS = {
    "mapped_drain_form": "Drain form",
    "mapped_solution_type": "Solution type",
    "product_category": "Product category",
    "outlet_dn_default": "Outlet DN",
    "material_v4a": "V4A material",
    "point_top_shape": "Point top shape",
}

ADVANCED_METRIC_DEFINITIONS = (
    ("flow_rate", "flow_rate_primary_lps", "Score_Flow_Rate_%", "higher", "technical group value"),
    ("installation_height", "height_adj_min_mm", "Score_Installation_Height_%", "lower", "technical group value"),
    ("v4a", "material_v4a", "Score_V4A_%", "yes", "technical group value"),
    ("sales_price", "sales_price_value", "Score_Sales_Price_%", "lower", "minimum member price; mixed currencies excluded"),
    ("colours", "colours_count", "Score_Colours_%", "higher", "explicit count or grouped finish fallback"),
)
HIERARCHY_SCHEMA_VERSION = "1.0"
PRESENTATION_GROUPING_POLICY = "explicit_or_derived_hierarchy_v2"

HIERARCHY_KEY_COLUMNS = [
    "technical_model_key",
    "technical_variant_key",
    "presentation_group_key",
    "hierarchy_key_source",
    "hierarchy_schema_version",
]

# Fields that define a technical presentation group. Colour, finish, article
# number, variant name and URLs are deliberately excluded so cosmetic variants
# do not multiply benchmark results. Physical differences remain separate.
PRESENTATION_GROUP_TEXT_FIELDS = [
    # Source-native fields only. Derived classification fields are deliberately
    # excluded so hierarchy keys remain stable when mapping rules are refined.
    "manufacturer_key",
    "product_category",
    "benchmark_entity_type",
    "candidate_type",
    "system_role",
    "outlet_dn_default",
    "outlet_orientation_default",
    "outlet_direction_selectable",
    "point_top_shape",
    "drain_position",
    "drain_location",
    "material_family",
    "material_grade_en",
    "material_grade_aisi",
    "material_v4a",
    "sealing_interface_type",
    "sealing_fleece_preassembled",
]

PRESENTATION_GROUP_NUMERIC_FIELDS = [
    "nominal_length_mm",
    "length_min_mm",
    "length_max_mm",
    "width_mm",
    "height_adj_min_mm",
    "height_adj_max_mm",
    "water_seal_mm",
    "flow_rate_10mm_lps",
    "flow_rate_20mm_lps",
    "flow_rate_unknown_head_lps",
    "flow_rate_primary_lps",
    "flow_rate_primary_head_mm",
]

# Point-drain geometry is part of the physical technical identity.  Registry
# fields are appended once so new explicit dimensions cannot be silently
# collapsed into a cosmetically grouped presentation row.
for _field in POINT_DRAIN_TEXT_GROUP_FIELDS:
    if _field not in PRESENTATION_GROUP_TEXT_FIELDS:
        PRESENTATION_GROUP_TEXT_FIELDS.append(_field)
for _field in (*POINT_DRAIN_NUMERIC_GROUP_FIELDS, *POINT_DRAIN_CANONICAL_NUMERIC_FIELDS):
    if _field not in PRESENTATION_GROUP_NUMERIC_FIELDS:
        PRESENTATION_GROUP_NUMERIC_FIELDS.append(_field)


@dataclass
class MasterData:
    """Merged logical v1/v2 layers and warnings detected during loading."""

    flat: pd.DataFrame
    bom: pd.DataFrame
    evidence: pd.DataFrame
    warnings: list[str]
    source_count: int
    prices: pd.DataFrame = field(default_factory=pd.DataFrame)
    missing_parts: pd.DataFrame = field(default_factory=pd.DataFrame)
    hydraulics: pd.DataFrame = field(default_factory=pd.DataFrame)
    technical: pd.DataFrame = field(default_factory=pd.DataFrame)
    technical_audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    exact_lifecycle: pd.DataFrame = field(default_factory=pd.DataFrame)
    record_lifecycle: pd.DataFrame = field(default_factory=pd.DataFrame)
    package_contents: pd.DataFrame = field(default_factory=pd.DataFrame)
    compatibility: pd.DataFrame = field(default_factory=pd.DataFrame)
    regional_provenance: pd.DataFrame = field(default_factory=pd.DataFrame)
    controlled_gaps: pd.DataFrame = field(default_factory=pd.DataFrame)
    workbook_metadata: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class RankingExecution:
    """Deterministic result of one structured ranking request."""

    request: dict[str, Any]
    ranked_all: pd.DataFrame
    ranking: pd.DataFrame
    grouped: pd.DataFrame
    members: pd.DataFrame


@dataclass
class ReferenceComparisonExecution:
    """Result of reference-based candidate filtering and independent scoring."""

    reference: pd.DataFrame
    comparable_groups: pd.DataFrame
    comparable_members: pd.DataFrame
    ranked_all: pd.DataFrame
    ranked: pd.DataFrame
    unranked: pd.DataFrame
    tolerance_audit: pd.DataFrame


def discover_local_workbooks(data_directory: Path) -> tuple[tuple[str, int, int], ...]:
    """Return a stable signature for all Excel workbooks in the ``data`` directory.

    Modification time and file size are included so the cache detects changes
    to local workbook content.
    """

    if not data_directory.exists():
        return ()

    signatures: list[tuple[str, int, int]] = []
    for workbook_path in sorted(data_directory.glob("*.xlsx")):
        if workbook_path.name.startswith("~$"):
            continue
        stats = workbook_path.stat()
        signatures.append((str(workbook_path), stats.st_mtime_ns, stats.st_size))
    return tuple(signatures)


def load_all_workbooks(
    local_workbooks: tuple[tuple[str, int, int], ...],
    uploaded_workbooks: tuple[tuple[str, bytes], ...] = (),
) -> MasterData:
    """Load legacy v1 and canonical v2 workbooks into one logical dataset.

    Canonical v2 workbooks may expose secondary layers as physical sheets or
    through the compressed secondary-archive contract. Both representations are
    normalised by :mod:`v2_excel_loader` before cross-workbook consolidation.
    """

    sheet_frames: dict[str, list[pd.DataFrame]] = empty_table_map()
    warnings: list[str] = []
    metadata_rows: list[dict[str, Any]] = []

    sources: list[tuple[str, str | BytesIO]] = [
        (Path(path).name, path) for path, _, _ in local_workbooks
    ]
    sources.extend((filename, BytesIO(content)) for filename, content in uploaded_workbooks)

    for source_name, source in sources:
        try:
            tables, source_warnings, metadata = read_workbook_tables(
                source_name, source
            )
            warnings.extend(source_warnings)
            metadata_rows.append(metadata)
            for data_key, frame in tables.items():
                if data_key in sheet_frames and not frame.empty:
                    sheet_frames[data_key].append(frame)
        except Exception as error:  # Another workbook may still load successfully.
            warnings.append(f"{source_name}: could not be loaded ({error}).")

    flat, bom, evidence = concatenate_and_deduplicate(sheet_frames)
    secondary: dict[str, pd.DataFrame] = {}
    for data_key in DATASET_SHEETS:
        if data_key in {"flat", "bom", "evidence"}:
            continue
        secondary[data_key] = _deduplicate_logical_layer(
            _concatenate(sheet_frames.get(data_key, ())), data_key
        )

    flat = enrich_flat_with_v2_layers(
        flat,
        technical=secondary.get("technical", pd.DataFrame()),
        evidence=evidence,
        prices=secondary.get("prices", pd.DataFrame()),
        technical_audit=secondary.get("technical_audit", pd.DataFrame()),
        record_lifecycle=secondary.get("record_lifecycle", pd.DataFrame()),
    )

    return MasterData(
        flat=flat,
        bom=bom,
        evidence=evidence,
        warnings=warnings,
        source_count=len(sources),
        prices=secondary.get("prices", pd.DataFrame()),
        missing_parts=secondary.get("missing_parts", pd.DataFrame()),
        hydraulics=secondary.get("hydraulics", pd.DataFrame()),
        technical=secondary.get("technical", pd.DataFrame()),
        technical_audit=secondary.get("technical_audit", pd.DataFrame()),
        exact_lifecycle=secondary.get("exact_lifecycle", pd.DataFrame()),
        record_lifecycle=secondary.get("record_lifecycle", pd.DataFrame()),
        package_contents=secondary.get("package_contents", pd.DataFrame()),
        compatibility=secondary.get("compatibility", pd.DataFrame()),
        regional_provenance=secondary.get("regional_provenance", pd.DataFrame()),
        controlled_gaps=secondary.get("controlled_gaps", pd.DataFrame()),
        workbook_metadata=pd.DataFrame(metadata_rows),
    )


def _deduplicate_logical_layer(frame: pd.DataFrame, data_key: str) -> pd.DataFrame:
    """Apply stable v2 deduplication keys while preserving legitimate observations."""

    if frame.empty:
        return frame.reset_index(drop=True)

    preferred_keys = {
        "prices": ("price_observation_id",),
        "hydraulics": ("observation_id",),
        "technical": ("observation_id",),
        "technical_audit": ("record_id",),
        "exact_lifecycle": ("manufacturer_article_no",),
        "record_lifecycle": ("record_id",),
        "controlled_gaps": ("gap_id",),
    }
    keys = [key for key in preferred_keys.get(data_key, ()) if key in frame.columns]
    if keys:
        frame = frame.drop_duplicates(subset=keys, keep="first")
    else:
        frame = frame.drop_duplicates()
    return frame.reset_index(drop=True)


APPLICATION_OBSERVATION_FIELDS = {
    # Common geometry / hydraulics / outlet
    "height_mm",
    "height_adj_min_mm",
    "height_adj_max_mm",
    "water_seal_mm",
    "outlet_dn_default",
    "outlet_orientation_default",
    "outlet_direction_selectable",
    "flow_rate_10mm_lps",
    "flow_rate_20mm_lps",
    "flow_rate_unknown_head_lps",
    "flow_rate_primary_lps",
    "flow_rate_primary_head_mm",
    "minimum_foundation_height_mm",
    "height_min_mm",
    "height_max_mm",
    # Linear-drain geometry
    "channel_length_mm",
    "channel_position",
    "max_shortening_inside_channel_mm",
    # Point-drain geometry
    "drain_type",
    "drain_location",
    "drain_position",
    "point_top_shape",
    "visible_grate_diameter_mm",
    "overall_body_diameter_mm",
    "grate_diameter_mm",
    "cover_diameter_mm",
    "grid_size_mm",
    "included_grid_size_mm",
    "fixed_frame_size_mm",
    "connection_side",
    "shape",
    "cover_shape",
    # Material / sealing / standards / finishes
    "material_raw",
    "material_family",
    "material_grade_en",
    "material_grade_aisi",
    "material_v2a",
    "material_v4a",
    "din_en_1253_status",
    "din_en_18534_status",
    "sealing_fleece_preassembled",
    "sealing_interface_type",
    "finish_name",
    "colours_count",
    "colours_list",
    "flow_rate_15mm_lps",
    "flow_rate_published_min_lps",
    "flow_rate_published_max_lps",
    "geometry_semantics",
}
APPLICATION_OBSERVATION_FIELDS.update(POINT_DRAIN_OBSERVATION_FIELDS)


def enrich_flat_with_v2_layers(
    flat: pd.DataFrame,
    *,
    technical: pd.DataFrame,
    evidence: pd.DataFrame,
    prices: pd.DataFrame,
    technical_audit: pd.DataFrame,
    record_lifecycle: pd.DataFrame,
) -> pd.DataFrame:
    """Project explicit v2 observations into the application view.

    A value is projected only when a record/field pair has exactly one distinct
    non-empty value. Existing explicit Flat_Input values are preserved; blank or
    ``unknown`` placeholders may be filled from the v2 observation layers. This
    keeps the UI wide enough for filtering without flattening or guessing
    conflicting observations.
    """

    enriched = flat.copy()
    if enriched.empty or "record_id" not in enriched.columns:
        return enriched

    # Technical observations are the primary projection source. Evidence is a
    # conservative fallback for explicit fields not materialised in technical.
    enriched = _project_observation_values(enriched, technical)
    enriched = _project_observation_values(enriched, evidence)
    enriched = _project_record_prices(enriched, prices)

    if not technical_audit.empty and "record_id" in technical_audit.columns:
        audit_fields = [
            column
            for column in (
                "technical_completeness_flag",
                "geometry_status",
                "outlet_status",
                "hydraulic_status",
                "material_status",
                "sealing_status",
                "standards_status",
                "finish_status",
                "missing_critical_fields",
                "controlled_unknown_fields",
                "blocking_gap_count",
                "audit_status",
            )
            if column in technical_audit.columns
        ]
        enriched = _fill_record_columns(enriched, technical_audit, audit_fields)

    if not record_lifecycle.empty and "record_id" in record_lifecycle.columns:
        lifecycle = record_lifecycle.copy()
        rename = {}
        if "lifecycle_status" in lifecycle.columns:
            rename["lifecycle_status"] = "lifecycle_status_v2"
        lifecycle = lifecycle.rename(columns=rename)
        lifecycle_fields = [
            column
            for column in (
                "lifecycle_status_v2",
                "regional_identity_status",
                "currentness_basis",
                "blocking_for_final_lock",
            )
            if column in lifecycle.columns
        ]
        enriched = _fill_record_columns(enriched, lifecycle, lifecycle_fields)

    return enriched


def _project_record_prices(flat: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Fill blank Flat_Input price fields from exact record-level observations.

    The application uses the lowest explicit price only when all observations
    linked to the record share one currency. Mixed-currency records remain blank
    for scoring, matching the grouped scoring policy. Source observations remain
    available unchanged in ``MasterData.prices``.
    """

    required = {"linked_record_id", "price_value", "currency"}
    if prices.empty or not required.issubset(prices.columns):
        return flat

    working = prices.copy()
    working["linked_record_id"] = working["linked_record_id"].astype("string").str.strip()
    if "sales_price_value" in flat.columns:
        existing_prices = numeric_series(flat["sales_price_value"])
        eligible_record_ids = set(
            flat.loc[existing_prices.isna(), "record_id"].astype("string").str.strip().tolist()
        )
        working = working[working["linked_record_id"].isin(eligible_record_ids)].copy()
    working["_price_numeric"] = numeric_series(working["price_value"])
    working["_currency"] = working["currency"].astype("string").str.strip()
    working = working[working["linked_record_id"].ne("") & working["_price_numeric"].notna()].copy()
    if working.empty:
        return flat

    rows: list[dict[str, Any]] = []
    for record_id, group in working.groupby("linked_record_id", sort=False):
        currencies = [
            value for value in group["_currency"].dropna().unique().tolist() if str(value).strip()
        ]
        if len(currencies) != 1:
            continue
        currency = str(currencies[0])
        same_currency = group[group["_currency"].eq(currency)].copy()
        selected_index = same_currency["_price_numeric"].idxmin()
        selected = same_currency.loc[selected_index]
        rows.append(
            {
                "record_id": record_id,
                "sales_price_value": float(selected["_price_numeric"]),
                "sales_price_currency": currency,
                "sales_price_type": selected.get("price_type"),
                "sales_price_region": selected.get("market_region"),
                "sales_price_observed_at": selected.get("observed_at"),
                "sales_price_basis": "minimum exact record-level price observation",
            }
        )
    if not rows:
        return flat
    return _fill_record_columns(
        flat,
        pd.DataFrame(rows),
        [
            "sales_price_value",
            "sales_price_currency",
            "sales_price_type",
            "sales_price_region",
            "sales_price_observed_at",
            "sales_price_basis",
        ],
    )


def _project_observation_values(flat: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    required = {"linked_record_id", "field_name"}
    if observations.empty or not required.issubset(observations.columns):
        return flat

    working = observations.copy()
    working["linked_record_id"] = working["linked_record_id"].astype("string").str.strip()
    working["field_name"] = working["field_name"].astype("string").str.strip()
    working = working[working["field_name"].isin(APPLICATION_OBSERVATION_FIELDS)].copy()
    if working.empty:
        return flat

    value = pd.Series(pd.NA, index=working.index, dtype="object")
    for candidate in ("normalized_value", "value_raw", "raw_value", "extracted_value"):
        if candidate not in working.columns:
            continue
        candidate_values = working[candidate]
        candidate_text = candidate_values.astype("string").str.strip()
        usable = candidate_values.notna() & candidate_text.ne("")
        value = value.where(value.notna(), candidate_values.where(usable))
    working["_app_value"] = value
    working = working[working["_app_value"].notna()].copy()
    if working.empty:
        return flat

    grouped = working.groupby(["linked_record_id", "field_name"], sort=False)["_app_value"]
    distinct_count = grouped.agg(lambda values: len({str(value).strip() for value in values if str(value).strip()}))
    first_value = grouped.first()
    unambiguous = first_value[distinct_count.eq(1)].reset_index()
    if unambiguous.empty:
        return flat

    projected = unambiguous.pivot(index="linked_record_id", columns="field_name", values="_app_value")
    projected = projected.reset_index().rename(columns={"linked_record_id": "record_id"})
    return _fill_record_columns(flat, projected, [c for c in projected.columns if c != "record_id"])


def _fill_record_columns(
    flat: pd.DataFrame, source: pd.DataFrame, columns: Sequence[str]
) -> pd.DataFrame:
    if not columns or source.empty or "record_id" not in source.columns:
        return flat

    result = flat.copy()
    source_unique = source.drop_duplicates(subset=["record_id"], keep="first").copy()
    source_unique["record_id"] = source_unique["record_id"].astype("string").str.strip()
    lookup = source_unique.set_index("record_id")
    record_ids = result["record_id"].astype("string").str.strip()

    for column in columns:
        if column not in lookup.columns:
            continue
        incoming = record_ids.map(lookup[column])
        if column not in result.columns:
            result[column] = incoming
            continue
        existing = result[column]
        existing_text = existing.astype("string").str.strip().str.casefold()
        replaceable = existing.isna() | existing_text.isin({"", "unknown", "n/a", "na"})
        if pd.api.types.is_numeric_dtype(existing):
            incoming_numeric = numeric_series(incoming)
            usable = replaceable & incoming_numeric.notna()
            result.loc[usable, column] = incoming_numeric.loc[usable]
        else:
            # Use object dtype so explicit numeric/text observations can coexist
            # without pandas emitting incompatible-dtype warnings.
            result[column] = result[column].astype("object")
            usable = replaceable & incoming.notna()
            result.loc[usable, column] = incoming.loc[usable]
    return result


def concatenate_and_deduplicate(
    sheet_frames: Mapping[str, Sequence[pd.DataFrame]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Merge and deduplicate the three sheet types according to the required rules."""

    flat = _concatenate(sheet_frames.get("flat", ()))
    bom = _concatenate(sheet_frames.get("bom", ()))
    evidence = _concatenate(sheet_frames.get("evidence", ()))

    flat = _normalise_identifier_columns(flat, "flat")
    bom = _normalise_identifier_columns(bom, "bom")
    evidence = _normalise_identifier_columns(evidence, "evidence")

    if "record_id" in flat.columns:
        flat = flat.drop_duplicates(subset=["record_id"], keep="first")

    # Preserve multiple evidence rows for the same record. Evidence is field-level
    # audit data, so deduplicating only by linked_record_id would discard valid
    # proof for all but one field. Remove only truly equivalent evidence rows,
    # using whichever identifying columns are present in the workbook.
    evidence_dedup_columns = [
        column
        for column in (
            "linked_record_id",
            "entity_type",
            "field_name",
            "normalized_value",
            "unit",
            "source_url",
            "source_excerpt",
        )
        if column in evidence.columns
    ]
    if evidence_dedup_columns:
        evidence = evidence.drop_duplicates(subset=evidence_dedup_columns, keep="first")
    else:
        evidence = evidence.drop_duplicates()

    bom = bom.drop_duplicates()

    return (
        flat.reset_index(drop=True),
        bom.reset_index(drop=True),
        evidence.reset_index(drop=True),
    )


def _concatenate(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def _normalise_identifier_columns(frame: pd.DataFrame, data_key: str) -> pd.DataFrame:
    """Keep identifiers as text, including any leading zeros."""

    normalised = frame.copy()
    for column in TEXT_COLUMNS[data_key]:
        if column in normalised.columns:
            normalised[column] = normalised[column].astype("string").str.strip()
    return normalised


def string_options(frame: pd.DataFrame, column: str) -> list[str]:
    """Return non-empty text values suitable for a multiselect widget."""

    if column not in frame.columns:
        return []
    values = frame[column].astype("string").str.strip().dropna()
    return sorted({value for value in values.tolist() if value})


def numeric_bounds(frame: pd.DataFrame, column: str) -> tuple[float, float] | None:
    """Determine the minimum and maximum valid numeric values in a column."""

    if column not in frame.columns:
        return None
    values = numeric_series(frame[column]).dropna()
    if values.empty:
        return None
    return float(values.min()), float(values.max())


def numeric_series(series: pd.Series) -> pd.Series:
    """Safely convert Excel numeric values, including decimal commas."""

    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = series.astype("string").str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")



def add_point_drain_geometry_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add manufacturer-neutral point-drain geometry columns.

    The normalisation is deliberately conservative: a canonical value is
    created only from explicit source fields with equivalent semantics.  When
    two explicit source fields disagree, the canonical field remains blank and
    its ``*_source`` column records the conflict.  Generic ``length_mm`` and
    ``width_mm`` are never reinterpreted as grate/top dimensions.
    """

    enriched = frame.copy()
    if enriched.empty:
        for target in POINT_DRAIN_CANONICAL_NUMERIC_FIELDS:
            enriched[target] = pd.Series(dtype="float64")
            enriched[f"{target}_source"] = pd.Series(dtype="string")
        for column in POINT_DRAIN_COMPOSITE_DISPLAY_FIELDS:
            enriched[column] = pd.Series(dtype="string")
        return enriched

    for target, source_fields in POINT_DRAIN_CANONICAL_SOURCE_FIELDS.items():
        values, basis = _coalesce_consistent_numeric_fields(enriched, source_fields)
        enriched[target] = values
        enriched[f"{target}_source"] = basis

    enriched["point_top_size"] = _compose_explicit_point_size(
        numeric_series(enriched.get("point_top_nominal_length_mm", pd.Series(index=enriched.index, dtype="float64"))),
        numeric_series(enriched.get("point_top_nominal_width_mm", pd.Series(index=enriched.index, dtype="float64"))),
        numeric_series(enriched.get("point_top_nominal_diameter_mm", pd.Series(index=enriched.index, dtype="float64"))),
    )
    enriched["point_grate_size"] = _compose_explicit_point_size(
        numeric_series(enriched["point_grate_length_mm"]),
        numeric_series(enriched["point_grate_width_mm"]),
        numeric_series(enriched["point_grate_diameter_mm"]),
    )
    enriched["point_cover_size"] = _compose_explicit_point_size(
        numeric_series(enriched["point_cover_length_mm"]),
        numeric_series(enriched["point_cover_width_mm"]),
        numeric_series(enriched["point_cover_diameter_mm"]),
    )
    enriched["point_body_size"] = _compose_explicit_point_size(
        pd.Series(float("nan"), index=enriched.index, dtype="float64"),
        pd.Series(float("nan"), index=enriched.index, dtype="float64"),
        numeric_series(enriched["point_body_diameter_mm"]),
    )

    if "mapped_drain_form" in enriched.columns:
        point_mask = _normalised_series(enriched, "mapped_drain_form").eq("point")
        for column in (*POINT_DRAIN_CANONICAL_NUMERIC_FIELDS, *POINT_DRAIN_COMPOSITE_DISPLAY_FIELDS):
            enriched.loc[~point_mask, column] = pd.NA
        for target in POINT_DRAIN_CANONICAL_NUMERIC_FIELDS:
            enriched.loc[~point_mask, f"{target}_source"] = pd.NA

    return enriched


def _coalesce_consistent_numeric_fields(
    frame: pd.DataFrame, source_fields: Sequence[str]
) -> tuple[pd.Series, pd.Series]:
    """Coalesce semantically equivalent explicit numeric fields without guessing."""

    available = [field for field in source_fields if field in frame.columns]
    if not available:
        return (
            pd.Series(float("nan"), index=frame.index, dtype="float64"),
            pd.Series(pd.NA, index=frame.index, dtype="string"),
        )

    matrix = pd.DataFrame(
        {field: numeric_series(frame[field]) for field in available},
        index=frame.index,
    )
    result = pd.Series(float("nan"), index=frame.index, dtype="float64")
    basis = pd.Series(pd.NA, index=frame.index, dtype="string")

    for row_index, row in matrix.iterrows():
        explicit = [(field, float(row[field])) for field in available if pd.notna(row[field])]
        if not explicit:
            continue
        distinct = {value for _, value in explicit}
        if len(distinct) == 1:
            result.at[row_index] = explicit[0][1]
            basis.at[row_index] = "+".join(field for field, _ in explicit)
        else:
            basis.at[row_index] = "conflict:" + "+".join(
                f"{field}={value:g}" for field, value in explicit
            )
    return result, basis


def _compose_explicit_point_size(
    length: pd.Series, width: pd.Series, diameter: pd.Series
) -> pd.Series:
    """Format explicit point geometry as ``L × W mm`` or ``ØD mm``.

    Diameter has precedence when it is explicitly available.  This avoids
    displaying a round grate as a square merely because a source also stores a
    bounding length/width.  Shape itself is never inferred from the dimensions.
    """

    result = pd.Series(pd.NA, index=length.index, dtype="string")
    for row_index in length.index:
        d = diameter.get(row_index)
        l = length.get(row_index)
        w = width.get(row_index)
        if pd.notna(d):
            result.at[row_index] = f"Ø{float(d):g} mm"
        elif pd.notna(l) and pd.notna(w):
            result.at[row_index] = f"{float(l):g} × {float(w):g} mm"
    return result


def prepare_benchmark_data(
    frame: pd.DataFrame,
    classification_rules: pd.DataFrame,
    length_rules: pd.DataFrame,
) -> pd.DataFrame:
    """Apply the approved drain-type mapping and length modes.

    Configuration tables remain separate from the source master workbooks.
    This avoids modifying the source files and makes every decision traceable
    through ``classification_rule_id`` and ``length_rule_id``.
    """

    classified = apply_classification_rules(frame, classification_rules)
    length_mapped = apply_length_rules(classified, length_rules)
    point_normalised = add_point_drain_geometry_columns(length_mapped)
    return add_product_hierarchy_keys(point_normalised)


def apply_classification_rules(
    frame: pd.DataFrame, rules: pd.DataFrame
) -> pd.DataFrame:
    """Assign drain type and application scope deterministically.

    Rules are evaluated in ascending priority order. The first match wins, and
    an unclassified record remains safely hidden.
    """

    classified = _ensure_benchmark_entity_type(frame)
    classified["classification_rule_id"] = "UNMATCHED"
    classified["classification_rule_priority"] = pd.NA
    classified["mapped_solution_type"] = "manual_review"
    classified["mapped_drain_form"] = "unknown"
    classified["mapped_installation_zone"] = "unknown"
    classified["mapped_drainage_mode"] = "unknown"
    classified["mapped_application_scope"] = "manual_review"
    classified["leaderboard_visibility"] = "hidden"
    classified["classification_confidence"] = "low"
    classified["classification_rationale"] = "No classification rule matched."

    if classified.empty or rules.empty:
        classified["drain_type_label"] = _drain_type_labels(classified)
        return classified

    prepared_rules = _sorted_enabled_rules(rules)
    unmatched = pd.Series(True, index=classified.index, dtype="bool")

    for _, rule in prepared_rules.iterrows():
        mask = unmatched & _classification_rule_mask(classified, rule)
        if not mask.any():
            continue

        classified.loc[mask, "classification_rule_id"] = _text(rule.get("rule_id"))
        classified.loc[mask, "classification_rule_priority"] = int(rule["_priority"])
        for column in CLASSIFICATION_ASSIGNMENT_COLUMNS:
            classified.loc[mask, column] = _text(rule.get(column)) or "unknown"
        classified.loc[mask, "classification_rationale"] = _text(rule.get("rationale"))
        unmatched.loc[mask] = False

    classified["drain_type_label"] = _drain_type_labels(classified)
    return classified


def apply_length_rules(frame: pd.DataFrame, rules: pd.DataFrame) -> pd.DataFrame:
    """Add the installable length range without unverified estimates."""

    mapped = _ensure_benchmark_entity_type(frame)
    if "length_mm" in mapped.columns:
        mapped["nominal_length_mm"] = numeric_series(mapped["length_mm"])
    else:
        mapped["nominal_length_mm"] = pd.Series(float("nan"), index=mapped.index)

    mapped["length_rule_id"] = "UNMATCHED"
    mapped["length_rule_priority"] = pd.NA
    mapped["length_mode"] = "not_applicable"
    mapped["length_min_mm"] = pd.Series(float("nan"), index=mapped.index)
    mapped["length_max_mm"] = pd.Series(float("nan"), index=mapped.index)
    mapped["strict_filter_eligible"] = "no"
    mapped["length_evidence_status"] = "not_in_active_linear_scope"
    mapped["length_evidence_url"] = pd.NA
    mapped["length_evidence_note"] = pd.NA
    mapped["length_rationale"] = "The length rule does not apply to this record."

    active_linear = (
        _normalised_series(mapped, "leaderboard_visibility").eq("active")
        & _normalised_series(mapped, "mapped_drain_form").eq("linear")
    )
    mapped.loc[active_linear & mapped["nominal_length_mm"].notna(), "length_mode"] = (
        "unclassified_nominal_only"
    )
    mapped.loc[active_linear & mapped["nominal_length_mm"].isna(), "length_mode"] = (
        "missing_length"
    )
    mapped.loc[active_linear, "length_evidence_status"] = "family_rule_missing"
    mapped.loc[
        active_linear,
        "length_rationale",
    ] = "The family does not yet have an approved length rule."

    if not mapped.empty and not rules.empty:
        prepared_rules = _sorted_enabled_rules(rules)
        unmatched = pd.Series(True, index=mapped.index, dtype="bool")

        for _, rule in prepared_rules.iterrows():
            mask = unmatched & _length_rule_mask(mapped, rule)
            if not mask.any():
                continue

            mapped.loc[mask, "length_rule_id"] = _text(rule.get("rule_id"))
            mapped.loc[mask, "length_rule_priority"] = int(rule["_priority"])
            mapped.loc[mask, "length_mode"] = _text(rule.get("length_mode"))
            mapped.loc[mask, "strict_filter_eligible"] = _text(
                rule.get("strict_filter_eligible")
            )
            mapped.loc[mask, "length_evidence_status"] = _text(rule.get("evidence_status"))
            mapped.loc[mask, "length_evidence_url"] = _text(rule.get("evidence_url"))
            mapped.loc[mask, "length_evidence_note"] = _text(rule.get("evidence_note"))
            mapped.loc[mask, "length_rationale"] = _text(rule.get("rationale"))
            mapped.loc[mask, "length_min_mm"] = _compute_length_bound(
                mapped.loc[mask, "nominal_length_mm"],
                _text(rule.get("min_rule")),
                rule.get("min_value_mm"),
            )
            mapped.loc[mask, "length_max_mm"] = _compute_length_bound(
                mapped.loc[mask, "nominal_length_mm"],
                _text(rule.get("max_rule")),
                rule.get("max_value_mm"),
            )
            unmatched.loc[mask] = False

    eligible_policy = mapped["strict_filter_eligible"].isin(LENGTH_FILTER_POLICIES)
    valid_range = (
        mapped["length_min_mm"].notna()
        & mapped["length_max_mm"].notna()
        & mapped["length_min_mm"].le(mapped["length_max_mm"])
    )
    mapped["length_filter_ready"] = "no"
    mapped.loc[eligible_policy & valid_range, "length_filter_ready"] = "yes"

    mapped["length_coverage_status"] = "not_applicable"
    mapped.loc[
        mapped["strict_filter_eligible"].eq("yes_range") & valid_range,
        "length_coverage_status",
    ] = "filter_ready_range"
    mapped.loc[
        mapped["strict_filter_eligible"].eq("yes_exact_only") & valid_range,
        "length_coverage_status",
    ] = "filter_ready_exact"
    mapped.loc[
        mapped["strict_filter_eligible"].eq("no_until_canonical"),
        "length_coverage_status",
    ] = "blocked_wip_source"
    mapped.loc[
        mapped["length_mode"].eq("adjustable_min_unverified"),
        "length_coverage_status",
    ] = "blocked_minimum_unverified"
    mapped.loc[
        mapped["length_mode"].eq("installation_trim_only"),
        "length_coverage_status",
    ] = "excluded_trim_only"
    mapped.loc[
        mapped["length_mode"].eq("unclassified_nominal_only"),
        "length_coverage_status",
    ] = "unclassified_nominal_only"
    mapped.loc[
        mapped["length_mode"].eq("missing_length"),
        "length_coverage_status",
    ] = "missing_nominal_length"
    mapped.loc[
        mapped["length_mode"].eq("false_positive_not_length"),
        "length_coverage_status",
    ] = "not_applicable_false_positive"

    mapped["length_status_label"] = mapped["length_coverage_status"].map(
        {
            "filter_ready_range": "Verified adjustable range",
            "filter_ready_exact": "Verified fixed length",
            "blocked_wip_source": "Verified; awaiting source approval",
            "blocked_minimum_unverified": "Minimum length is not verified",
            "excluded_trim_only": "Installation trim only",
            "unclassified_nominal_only": "Nominal length only",
            "missing_nominal_length": "Length is missing from the data",
            "not_applicable_false_positive": "Length filter does not apply",
            "not_applicable": "Length filter does not apply",
        }
    )
    mapped["drain_type_label"] = _drain_type_labels(mapped)

    # Category-aware display length: for integrated linear shower elements the
    # Flat_Input length is the shower element itself, while channel_length_mm is
    # the actual drain element. Standalone legacy linear drains continue to use
    # nominal_length_mm. Point drains deliberately have no drain-element length.
    mapped["drain_element_length_mm"] = mapped["nominal_length_mm"]
    mapped["drain_element_length_basis"] = "nominal product/drain length"
    linear_mask = _normalised_series(mapped, "mapped_drain_form").eq("linear")
    point_mask = _normalised_series(mapped, "mapped_drain_form").eq("point")
    if "channel_length_mm" in mapped.columns:
        channel_length = numeric_series(mapped["channel_length_mm"])
        use_channel = linear_mask & channel_length.notna()
        mapped.loc[use_channel, "drain_element_length_mm"] = channel_length.loc[use_channel]
        mapped.loc[use_channel, "drain_element_length_basis"] = "explicit channel_length_mm"
    mapped.loc[point_mask, "drain_element_length_mm"] = float("nan")
    mapped.loc[point_mask, "drain_element_length_basis"] = "not applicable to point drain"
    return mapped


def length_filter_bounds(frame: pd.DataFrame) -> tuple[float, float] | None:
    """Return the overall verified installable range for the linear-drain filter."""

    required = {"length_filter_ready", "length_min_mm", "length_max_mm"}
    if not required.issubset(frame.columns):
        return None
    eligible = frame["length_filter_ready"].astype("string").str.casefold().eq("yes")
    minimums = numeric_series(frame.loc[eligible, "length_min_mm"]).dropna()
    maximums = numeric_series(frame.loc[eligible, "length_max_mm"]).dropna()
    if minimums.empty or maximums.empty:
        return None
    return float(minimums.min()), float(maximums.max())


def _ensure_benchmark_entity_type(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    candidate_types = _normalised_series(prepared, "candidate_type")
    inferred = pd.Series("unknown", index=prepared.index, dtype="string")
    inferred.loc[candidate_types.isin(COMPLETE_CANDIDATE_TYPES)] = "system"
    inferred.loc[candidate_types.eq("component")] = "component"

    if "benchmark_entity_type" not in prepared.columns:
        prepared["benchmark_entity_type"] = inferred
    else:
        existing = prepared["benchmark_entity_type"].astype("string").str.strip()
        prepared["benchmark_entity_type"] = existing.mask(existing.isna() | existing.eq(""), inferred)
    return prepared


def _sorted_enabled_rules(rules: pd.DataFrame) -> pd.DataFrame:
    prepared = rules.copy()
    if "enabled" in prepared.columns:
        enabled = prepared["enabled"].astype("string").str.strip().str.casefold().eq("yes")
        prepared = prepared[enabled].copy()
    prepared["_priority"] = pd.to_numeric(prepared.get("priority"), errors="coerce")
    prepared = prepared[prepared["_priority"].notna()].copy()
    prepared["_priority"] = prepared["_priority"].astype(int)
    return prepared.sort_values(["_priority", "rule_id"], kind="stable")


def _classification_rule_mask(frame: pd.DataFrame, rule: pd.Series) -> pd.Series:
    mask = _condition_mask(frame, "benchmark_entity_type", rule.get("benchmark_entity_type"))
    mask &= _condition_mask(frame, "manufacturer_key", rule.get("manufacturer_key"))
    mask &= _condition_mask(frame, "product_category", rule.get("product_category"))
    mask &= _family_rule_mask(frame, rule)
    mask &= _variant_rule_mask(frame, rule)
    return mask


def _length_rule_mask(frame: pd.DataFrame, rule: pd.Series) -> pd.Series:
    mask = _condition_mask(frame, "benchmark_entity_type", rule.get("benchmark_entity_type"))
    mask &= _condition_mask(frame, "manufacturer_key", rule.get("manufacturer_key"))
    mask &= _condition_mask(frame, "mapped_drain_form", rule.get("required_drain_form"))
    mask &= _family_rule_mask(frame, rule)
    mask &= _variant_rule_mask(frame, rule)
    return mask


def _condition_mask(frame: pd.DataFrame, column: str, condition: Any) -> pd.Series:
    condition_text = _text(condition)
    if condition_text in {"", "*"}:
        return pd.Series(True, index=frame.index, dtype="bool")
    allowed = {part.strip().casefold() for part in condition_text.split("|") if part.strip()}
    return _normalised_series(frame, column).isin(allowed)


def _family_rule_mask(frame: pd.DataFrame, rule: pd.Series) -> pd.Series:
    mode = _text(rule.get("family_match")).casefold()
    value = _text(rule.get("family_value"))
    if mode in {"", "any"} or value in {"", "*"}:
        return pd.Series(True, index=frame.index, dtype="bool")

    family = _normalised_series(frame, "product_family_name")
    expected = value.casefold()
    if mode == "exact":
        return family.eq(expected)
    if mode == "prefix":
        return family.str.startswith(expected, na=False)
    if mode == "contains":
        return family.str.contains(expected, regex=False, na=False)
    return pd.Series(False, index=frame.index, dtype="bool")


def _variant_rule_mask(frame: pd.DataFrame, rule: pd.Series) -> pd.Series:
    value = _text(rule.get("variant_contains"))
    if value in {"", "*"}:
        return pd.Series(True, index=frame.index, dtype="bool")
    return _normalised_series(frame, "variant_name").str.contains(
        value.casefold(), regex=False, na=False
    )


def _normalised_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("", index=frame.index, dtype="string")
    return frame[column].astype("string").str.strip().str.casefold().fillna("")


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _drain_type_labels(frame: pd.DataFrame) -> pd.Series:
    forms = _normalised_series(frame, "mapped_drain_form")
    labels = forms.map(DRAIN_FORM_LABELS)
    return labels.fillna(forms.mask(forms.eq(""), "Unclassified"))


def _compute_length_bound(
    nominal: pd.Series, rule_name: str, configured_value: Any
) -> pd.Series:
    nominal_values = numeric_series(nominal)
    rule = rule_name.casefold()
    if rule == "constant":
        value = pd.to_numeric(pd.Series([configured_value]), errors="coerce").iloc[0]
        return pd.Series(value, index=nominal.index, dtype="float64").where(nominal_values.notna())
    if rule == "nominal_minus_100":
        return nominal_values - 100.0
    if rule in {"same_as_nominal", "nominal_length_mm"}:
        return nominal_values
    return pd.Series(float("nan"), index=nominal.index, dtype="float64")


def filter_flat_input(
    frame: pd.DataFrame,
    *,
    include_incomplete: bool,
    manufacturers: Sequence[str] | None,
    flow_range: tuple[float, float] | None,
    height_range: tuple[float, float] | None,
    attribute_filters: Mapping[str, Sequence[str] | None],
    drain_forms: Sequence[str] | None = None,
    solution_types: Sequence[str] | None = None,
    numeric_filters: Mapping[str, tuple[float, float] | None] | None = None,
    length_range: tuple[float, float] | None = None,
    include_unverified_length: bool = False,
) -> pd.DataFrame:
    """Apply hard filters only to ``01_Flat_Input``."""

    filtered = frame.copy()

    if "leaderboard_visibility" in filtered.columns:
        allowed_visibility = {"active", "context_only"} if include_incomplete else {"active"}
        visibility = filtered["leaderboard_visibility"].astype("string").str.strip().str.casefold()
        filtered = filtered[visibility.isin(allowed_visibility)]

    if not include_incomplete:
        if "candidate_type" not in filtered.columns:
            return filtered.iloc[0:0].copy()
        candidate_types = filtered["candidate_type"].astype("string").str.strip().str.casefold()
        filtered = filtered[candidate_types.isin(COMPLETE_CANDIDATE_TYPES)]

    filtered = _filter_text_values(filtered, "manufacturer_key", manufacturers)
    filtered = _filter_text_values(filtered, "mapped_drain_form", drain_forms)
    filtered = _filter_text_values(filtered, "mapped_solution_type", solution_types)

    if flow_range is not None:
        filtered = _filter_numeric_range(filtered, "flow_rate_primary_lps", flow_range)
    if height_range is not None:
        filtered = _filter_numeric_range(filtered, "height_adj_min_mm", height_range)

    for column, selected_values in attribute_filters.items():
        filtered = _filter_text_values(filtered, column, selected_values)

    for column, selected_range in (numeric_filters or {}).items():
        if selected_range is not None:
            filtered = _filter_numeric_range(filtered, column, selected_range)

    if length_range is not None:
        filtered = _filter_length_compatibility(
            filtered,
            length_range,
            include_unverified=include_unverified_length,
        )

    return filtered.reset_index(drop=True)


def _filter_text_values(
    frame: pd.DataFrame, column: str, selected_values: Sequence[str] | None
) -> pd.DataFrame:
    if selected_values is None:
        return frame
    if column not in frame.columns:
        return frame.iloc[0:0].copy()
    values = frame[column].astype("string").str.strip()
    return frame[values.isin(list(selected_values))]


def _filter_numeric_range(
    frame: pd.DataFrame, column: str, selected_range: tuple[float, float]
) -> pd.DataFrame:
    if column not in frame.columns:
        return frame.iloc[0:0].copy()
    values = numeric_series(frame[column])
    lower, upper = selected_range
    return frame[values.notna() & values.between(lower, upper, inclusive="both")]


def _filter_length_compatibility(
    frame: pd.DataFrame,
    selected_range: tuple[float, float],
    *,
    include_unverified: bool,
) -> pd.DataFrame:
    required = {"length_filter_ready", "length_min_mm", "length_max_mm"}
    if not required.issubset(frame.columns):
        return frame.iloc[0:0].copy()

    ready = frame["length_filter_ready"].astype("string").str.strip().str.casefold().eq("yes")
    minimums = numeric_series(frame["length_min_mm"])
    maximums = numeric_series(frame["length_max_mm"])
    selected_minimum, selected_maximum = selected_range
    overlaps = (
        ready
        & minimums.notna()
        & maximums.notna()
        & maximums.ge(selected_minimum)
        & minimums.le(selected_maximum)
    )
    if include_unverified:
        overlaps |= ~ready
    return frame[overlaps]


def score_filtered_systems(
    frame: pd.DataFrame,
    weights: Mapping[str, float | int],
    *,
    missing_data_policy: str = "allow_incomplete_zero_score",
) -> pd.DataFrame:
    """Score products and expose an auditable missing-data treatment.

    ``require_complete`` keeps only rows with explicit values for every active
    metric. ``allow_incomplete_zero_score`` preserves the previous behaviour: a
    missing active metric contributes zero points.
    ``allow_incomplete_proportional_penalty`` first calculates a score from the
    available active metrics and then multiplies it by the unweighted share of
    active criteria that are available.
    """

    if missing_data_policy not in ADVANCED_MISSING_DATA_POLICIES:
        raise ValueError(f"Unsupported advanced missing-data policy: {missing_data_policy}")

    metric_weights = {
        metric: max(float(weights.get(metric, 0)), 0.0)
        for metric, *_ in ADVANCED_METRIC_DEFINITIONS
    }
    active_metrics = [metric for metric, weight in metric_weights.items() if weight > 0]
    total_weight = sum(metric_weights.values())

    prepared = frame.copy()
    availability = _advanced_metric_availability(prepared)
    required_count = len(active_metrics)
    if required_count:
        available_count = sum(availability[metric].astype("int64") for metric in active_metrics)
    else:
        available_count = pd.Series(0, index=prepared.index, dtype="int64")

    if missing_data_policy == "require_complete" and required_count:
        prepared = prepared.loc[available_count.eq(required_count)].copy()

    scored = prepared.copy()
    scored["Score_Flow_Rate_%"] = _normalised_numeric_score(
        scored, "flow_rate_primary_lps", higher_is_better=True
    )
    scored["Score_Installation_Height_%"] = _normalised_numeric_score(
        scored, "height_adj_min_mm", higher_is_better=False
    )
    scored["Score_V4A_%"] = _v4a_score(scored)
    scored["Score_Sales_Price_%"] = _normalised_numeric_score(
        scored, "sales_price_value", higher_is_better=False
    )
    scored["Score_Colours_%"] = _normalised_numeric_score(
        scored, "colours_count", higher_is_better=True
    )

    availability = _advanced_metric_availability(scored)
    if required_count:
        available_count = sum(availability[metric].astype("int64") for metric in active_metrics)
        data_completeness = available_count / required_count * 100.0
        missing_fields = pd.Series(
            [
                "; ".join(
                    source_column
                    for metric, source_column, *_ in ADVANCED_METRIC_DEFINITIONS
                    if metric in active_metrics and not bool(availability[metric].loc[index])
                )
                for index in scored.index
            ],
            index=scored.index,
            dtype="string",
        )
    else:
        available_count = pd.Series(0, index=scored.index, dtype="int64")
        data_completeness = pd.Series(100.0, index=scored.index, dtype="float64")
        missing_fields = pd.Series("", index=scored.index, dtype="string")

    if total_weight > 0:
        available_weight = sum(
            availability[metric].astype("float64") * metric_weights[metric]
            for metric in active_metrics
        )
        weighted_completeness = available_weight / total_weight * 100.0
        weighted_score_sum = sum(
            scored[score_column] * metric_weights[metric]
            for metric, _, score_column, *_ in ADVANCED_METRIC_DEFINITIONS
            if metric in active_metrics
        )
        zero_score_result = weighted_score_sum / total_weight
        score_from_available = weighted_score_sum.div(available_weight.where(available_weight.gt(0))).fillna(0.0)
    else:
        available_weight = pd.Series(0.0, index=scored.index, dtype="float64")
        weighted_completeness = pd.Series(100.0, index=scored.index, dtype="float64")
        zero_score_result = pd.Series(0.0, index=scored.index, dtype="float64")
        score_from_available = pd.Series(0.0, index=scored.index, dtype="float64")

    if missing_data_policy == "allow_incomplete_proportional_penalty":
        score_before_penalty = score_from_available
        penalty_factor = data_completeness / 100.0
        final_score = score_before_penalty * penalty_factor
    else:
        score_before_penalty = zero_score_result
        penalty_factor = pd.Series(1.0, index=scored.index, dtype="float64")
        final_score = zero_score_result

    scored["Available_Criteria"] = available_count.astype("int64")
    scored["Required_Criteria"] = int(required_count)
    scored["Data_Completeness_%"] = data_completeness.astype("float64")
    scored["Weighted_Data_Completeness_%"] = weighted_completeness.astype("float64")
    scored["Missing_Ranking_Fields"] = missing_fields
    scored["Score_Before_Completeness_Penalty_%"] = score_before_penalty.astype("float64")
    scored["Completeness_Penalty_Factor"] = penalty_factor.astype("float64")
    scored["Missing_Data_Policy"] = missing_data_policy
    scored["Final_Score_%"] = final_score.astype("float64")

    return scored


def _advanced_metric_availability(frame: pd.DataFrame) -> dict[str, pd.Series]:
    """Return explicit-data availability masks for all advanced metrics."""

    masks: dict[str, pd.Series] = {}
    for metric, source_column, *_ in ADVANCED_METRIC_DEFINITIONS:
        if metric == "v4a":
            if source_column not in frame.columns:
                masks[metric] = pd.Series(False, index=frame.index, dtype="bool")
            else:
                values = frame[source_column].astype("string").str.strip().str.casefold()
                masks[metric] = values.isin(["yes", "no"])
        elif source_column not in frame.columns:
            masks[metric] = pd.Series(False, index=frame.index, dtype="bool")
        else:
            masks[metric] = numeric_series(frame[source_column]).notna()
    return masks


def score_advanced_product_groups(
    frame: pd.DataFrame,
    weights: Mapping[str, float | int],
    *,
    missing_data_policy: str = "allow_incomplete_zero_score",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score one row per technical presentation group.

    Cosmetic article and finish variants are collapsed before normalisation so
    they cannot multiply the leaderboard. Technical values are inherited from
    the stable presentation group. Price uses the lowest observed member price
    only when the group has at most one known currency. Colour count prefers the
    largest explicit ``colours_count`` and otherwise falls back to the number of
    grouped finish variants. The returned member frame keeps every exact source
    record for drill-down and audit export.
    """

    grouped, members = aggregate_presentation_groups(frame)
    if grouped.empty:
        return (
            score_filtered_systems(
                grouped, weights, missing_data_policy=missing_data_policy
            ),
            members,
        )

    grouped = _apply_advanced_group_aggregates(grouped, members)
    return (
        score_filtered_systems(
            grouped, weights, missing_data_policy=missing_data_policy
        ),
        members,
    )


def _apply_advanced_group_aggregates(
    grouped: pd.DataFrame, members: pd.DataFrame
) -> pd.DataFrame:
    """Add transparent group-level price and colour values used by scoring."""

    aggregated = grouped.copy()
    group_key = "presentation_group_key"
    if group_key not in aggregated.columns or group_key not in members.columns:
        return aggregated

    working = members.copy()
    working["_advanced_price"] = (
        numeric_series(working["sales_price_value"])
        if "sales_price_value" in working.columns
        else pd.Series(float("nan"), index=working.index, dtype="float64")
    )
    working["_advanced_colours"] = (
        numeric_series(working["colours_count"])
        if "colours_count" in working.columns
        else pd.Series(float("nan"), index=working.index, dtype="float64")
    )

    if "sales_price_currency" in working.columns:
        currencies = working["sales_price_currency"].astype("string").str.strip()
        working["_advanced_price_currency"] = currencies.where(
            working["_advanced_price"].notna() & currencies.notna() & currencies.ne("")
        )
    else:
        working["_advanced_price_currency"] = pd.Series(
            pd.NA, index=working.index, dtype="string"
        )

    grouped_members = working.groupby(group_key, sort=False, dropna=False)
    price_min = grouped_members["_advanced_price"].min()
    price_count = grouped_members["_advanced_price"].count()
    currency_count = grouped_members["_advanced_price_currency"].nunique(dropna=True)
    currency_list = grouped_members["_advanced_price_currency"].agg(
        _join_unique_nonempty_text
    )
    explicit_colour_max = grouped_members["_advanced_colours"].max()

    keys = aggregated[group_key]
    mapped_price = keys.map(price_min)
    mapped_price_count = keys.map(price_count).fillna(0).astype("int64")
    mapped_currency_count = keys.map(currency_count).fillna(0).astype("int64")
    mapped_currency_list = keys.map(currency_list).replace("", pd.NA)

    mixed_currency = mapped_currency_count.gt(1)
    aggregated["sales_price_value"] = mapped_price.mask(mixed_currency)
    aggregated["sales_price_variant_count"] = mapped_price_count
    aggregated["sales_price_currency_count"] = mapped_currency_count
    aggregated["sales_price_currency"] = mapped_currency_list.where(
        mapped_currency_count.eq(1)
    )

    price_basis = pd.Series("unknown", index=aggregated.index, dtype="string")
    has_price = mapped_price_count.gt(0)
    price_basis.loc[has_price & mapped_currency_count.eq(1)] = (
        "minimum observed article/finish price"
    )
    price_basis.loc[has_price & mapped_currency_count.eq(0)] = (
        "minimum observed article/finish price; currency unknown"
    )
    price_basis.loc[mixed_currency] = "mixed currencies; excluded from price score"
    aggregated["sales_price_group_basis"] = price_basis

    mapped_explicit_colours = keys.map(explicit_colour_max)
    finish_counts = numeric_series(
        aggregated.get(
            "finish_variant_count",
            pd.Series(float("nan"), index=aggregated.index, dtype="float64"),
        )
    )
    finish_fallback = finish_counts.where(finish_counts.gt(0))
    grouped_colours = pd.concat(
        [mapped_explicit_colours, finish_fallback], axis=1
    ).max(axis=1, skipna=True)
    aggregated["colours_count"] = grouped_colours

    colour_basis = pd.Series("unknown", index=aggregated.index, dtype="string")
    explicit_available = mapped_explicit_colours.notna()
    finish_available = finish_fallback.notna()
    colour_basis.loc[explicit_available & ~finish_available] = "explicit colours_count"
    colour_basis.loc[~explicit_available & finish_available] = (
        "grouped finish variants fallback"
    )
    colour_basis.loc[explicit_available & finish_available] = (
        "maximum of explicit colours_count and grouped finish variants"
    )
    aggregated["colours_count_source"] = colour_basis
    return aggregated


def advanced_scoring_audit_tables(
    scored_groups: pd.DataFrame,
    members: pd.DataFrame,
    weights: Mapping[str, float | int],
    *,
    missing_data_policy: str = "allow_incomplete_zero_score",
) -> dict[str, pd.DataFrame]:
    """Create grouped leaderboard, settings, weights, and exact-variant audit tables."""

    if missing_data_policy not in ADVANCED_MISSING_DATA_POLICIES:
        raise ValueError(f"Unsupported advanced missing-data policy: {missing_data_policy}")

    leaderboard = scored_groups.copy()
    total_weight = sum(
        max(float(weights.get(metric, 0)), 0.0)
        for metric, *_ in ADVANCED_METRIC_DEFINITIONS
    )
    weight_rows: list[dict[str, Any]] = []
    for metric, source_column, score_column, direction, basis in ADVANCED_METRIC_DEFINITIONS:
        raw_weight = max(float(weights.get(metric, 0)), 0.0)
        normalised = raw_weight / total_weight * 100.0 if total_weight > 0 else 0.0
        weight_rows.append(
            {
                "metric": metric,
                "source_column": source_column,
                "direction": direction,
                "raw_weight": raw_weight,
                "normalised_weight_percent": normalised,
                "score_column": score_column,
                "group_value_basis": basis,
                "active_for_completeness": raw_weight > 0,
            }
        )
    weight_profile = pd.DataFrame(weight_rows)

    total_groups = (
        int(members["presentation_group_key"].nunique(dropna=True))
        if not members.empty and "presentation_group_key" in members.columns
        else len(leaderboard)
    )
    completeness_values = (
        numeric_series(leaderboard["Data_Completeness_%"])
        if "Data_Completeness_%" in leaderboard.columns
        else pd.Series(dtype="float64")
    )
    settings = pd.DataFrame(
        [
            {
                "missing_data_policy": missing_data_policy,
                "active_metric_count": int(sum(row["active_for_completeness"] for row in weight_rows)),
                "source_variant_rows": len(members),
                "technical_groups_before_missing_data_policy": total_groups,
                "ranked_technical_groups": len(leaderboard),
                "excluded_technical_groups_due_missing_data": max(total_groups - len(leaderboard), 0),
                "mean_data_completeness_percent": (
                    float(completeness_values.mean()) if not completeness_values.empty else None
                ),
                "minimum_data_completeness_percent": (
                    float(completeness_values.min()) if not completeness_values.empty else None
                ),
            }
        ]
    )

    variants = members.copy()
    if (
        not variants.empty
        and "presentation_group_key" in variants.columns
        and "presentation_group_key" in leaderboard.columns
    ):
        audit_columns = [
            column
            for column in (
                "presentation_group_key",
                "Rank",
                "Final_Score_%",
                "Score_Before_Completeness_Penalty_%",
                "Completeness_Penalty_Factor",
                "Data_Completeness_%",
                "Weighted_Data_Completeness_%",
                "Available_Criteria",
                "Required_Criteria",
                "Missing_Ranking_Fields",
                "Missing_Data_Policy",
                "Score_Flow_Rate_%",
                "Score_Installation_Height_%",
                "Score_V4A_%",
                "Score_Sales_Price_%",
                "Score_Colours_%",
                "sales_price_group_basis",
                "colours_count_source",
            )
            if column in leaderboard.columns
        ]
        variants = variants.merge(
            leaderboard[audit_columns].drop_duplicates(
                subset=["presentation_group_key"], keep="first"
            ),
            on="presentation_group_key",
            how="inner",
            suffixes=("", "_group"),
        )
        if "Rank" in variants.columns:
            variants = variants.sort_values(
                ["Rank", "record_id"] if "record_id" in variants.columns else ["Rank"],
                kind="stable",
            ).reset_index(drop=True)

    return {
        "Advanced_Leaderboard": leaderboard,
        "Advanced_Settings": settings,
        "Advanced_Weights": weight_profile,
        "Ranked_Variants": variants,
    }


def _normalised_numeric_score(
    frame: pd.DataFrame, column: str, *, higher_is_better: bool
) -> pd.Series:
    score = pd.Series(0.0, index=frame.index, dtype="float64")
    if column not in frame.columns:
        return score

    values = numeric_series(frame[column])
    valid_values = values.dropna()
    if valid_values.empty:
        return score

    minimum = valid_values.min()
    maximum = valid_values.max()
    if minimum == maximum:
        score.loc[values.notna()] = 100.0
        return score

    if higher_is_better:
        score.loc[values.notna()] = (values.loc[values.notna()] - minimum) / (maximum - minimum) * 100
    else:
        score.loc[values.notna()] = (maximum - values.loc[values.notna()]) / (maximum - minimum) * 100
    return score.clip(lower=0.0, upper=100.0)


def _v4a_score(frame: pd.DataFrame) -> pd.Series:
    score = pd.Series(0.0, index=frame.index, dtype="float64")
    if "material_v4a" not in frame.columns:
        return score
    is_v4a = frame["material_v4a"].astype("string").str.strip().str.casefold().eq("yes")
    score.loc[is_v4a] = 100.0
    return score



def add_product_hierarchy_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """Add stable product-hierarchy keys while preserving explicit database values.

    The application prefers persisted keys when the input workbook/database already
    contains them. Missing keys are derived deterministically from canonical model
    identity and explicit technical fields. This makes the current Excel-backed app
    compatible with a future PostgreSQL schema without changing ranking behaviour.
    """

    enriched = frame.copy()
    if enriched.empty:
        for column in HIERARCHY_KEY_COLUMNS:
            enriched[column] = pd.Series(dtype="string")
        return enriched

    explicit_model = _existing_hierarchy_key(enriched, "technical_model_key")
    derived_model = _derive_technical_model_keys(enriched)
    model_key = explicit_model.mask(explicit_model.eq(""), derived_model)

    explicit_variant = _existing_hierarchy_key(enriched, "technical_variant_key")
    derived_variant = _derive_technical_variant_keys(enriched, model_key)
    variant_key = explicit_variant.mask(explicit_variant.eq(""), derived_variant)

    explicit_group = _existing_hierarchy_key(enriched, "presentation_group_key")
    derived_group = _derive_presentation_group_keys(variant_key)
    presentation_key = explicit_group.mask(explicit_group.eq(""), derived_group)

    explicit_counts = (
        explicit_model.ne("").astype("int64")
        + explicit_variant.ne("").astype("int64")
        + explicit_group.ne("").astype("int64")
    )
    calculated_source = pd.Series("derived_v2", index=enriched.index, dtype="string")
    calculated_source.loc[explicit_counts.eq(3)] = "explicit"
    calculated_source.loc[explicit_counts.between(1, 2)] = "mixed_explicit_derived"

    # Repeated enrichment must be idempotent. Keys derived earlier in the same
    # application run are not reclassified as explicit database values.
    existing_source = _existing_hierarchy_key(enriched, "hierarchy_key_source")
    key_source = existing_source.mask(existing_source.eq(""), calculated_source)

    enriched["technical_model_key"] = model_key.astype("string")
    enriched["technical_variant_key"] = variant_key.astype("string")
    enriched["presentation_group_key"] = presentation_key.astype("string")
    enriched["hierarchy_key_source"] = key_source
    enriched["hierarchy_schema_version"] = HIERARCHY_SCHEMA_VERSION
    return enriched


def hierarchy_audit_tables(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return database-migration and validation tables for product hierarchy keys."""

    enriched = add_product_hierarchy_keys(frame)
    grouped, members = aggregate_presentation_groups(enriched)

    record_columns = [
        "record_id",
        "system_key",
        "manufacturer_key",
        "manufacturer_name",
        "product_family_key",
        "product_family_name",
        "model_key",
        "model_name",
        "variant_key",
        "variant_name",
        "manufacturer_article_no",
        "finish_name",
        "nominal_length_mm",
        "outlet_dn_default",
        "height_adj_min_mm",
        "flow_rate_20mm_lps",
        "flow_rate_primary_lps",
        *HIERARCHY_KEY_COLUMNS,
    ]
    record_map = members.loc[:, [c for c in record_columns if c in members.columns]].copy()

    group_columns = [
        "presentation_group_key",
        "technical_model_key",
        "technical_variant_key",
        "hierarchy_key_source",
        "manufacturer_key",
        "manufacturer_name",
        "product_family_key",
        "product_family_name",
        "model_key",
        "model_name",
        "nominal_length_mm",
        "outlet_dn_default",
        "height_adj_min_mm",
        "flow_rate_20mm_lps",
        "flow_rate_primary_lps",
        "group_member_count",
        "finish_variant_count",
        "article_variant_count",
        "available_finishes",
        "product_link",
    ]
    group_map = grouped.loc[:, [c for c in group_columns if c in grouped.columns]].copy()

    source_counts = (
        enriched["hierarchy_key_source"].value_counts(dropna=False).to_dict()
        if "hierarchy_key_source" in enriched.columns
        else {}
    )
    model_collisions = _hierarchy_collision_count(
        enriched, "technical_variant_key", "technical_model_key"
    )
    group_collisions = _hierarchy_collision_count(
        enriched, "presentation_group_key", "technical_variant_key"
    )
    validation = pd.DataFrame(
        [
            {"metric": "hierarchy_schema_version", "value": HIERARCHY_SCHEMA_VERSION, "status": "info"},
            {"metric": "source_records", "value": len(enriched), "status": "info"},
            {"metric": "technical_models", "value": enriched["technical_model_key"].nunique(dropna=True), "status": "info"},
            {"metric": "technical_variants", "value": enriched["technical_variant_key"].nunique(dropna=True), "status": "info"},
            {"metric": "presentation_groups", "value": enriched["presentation_group_key"].nunique(dropna=True), "status": "info"},
            {"metric": "hidden_cosmetic_or_article_variants", "value": max(len(enriched) - len(grouped), 0), "status": "info"},
            {"metric": "explicit_key_records", "value": int(source_counts.get("explicit", 0)), "status": "info"},
            {"metric": "mixed_key_records", "value": int(source_counts.get("mixed_explicit_derived", 0)), "status": "review" if source_counts.get("mixed_explicit_derived", 0) else "ok"},
            {"metric": "derived_key_records", "value": int(source_counts.get("derived_v2", 0)), "status": "review" if source_counts.get("derived_v2", 0) else "ok"},
            {"metric": "technical_variant_to_model_collisions", "value": model_collisions, "status": "error" if model_collisions else "ok"},
            {"metric": "presentation_group_to_variant_collisions", "value": group_collisions, "status": "error" if group_collisions else "ok"},
        ]
    )
    return {
        "Hierarchy_Record_Map": record_map,
        "Presentation_Groups": group_map,
        "Hierarchy_Validation": validation,
    }


def hierarchy_summary(frame: pd.DataFrame) -> dict[str, int]:
    """Return compact hierarchy metrics for the Streamlit status panel."""

    enriched = add_product_hierarchy_keys(frame)
    source = enriched.get(
        "hierarchy_key_source", pd.Series(index=enriched.index, dtype="string")
    ).astype("string")
    return {
        "source_records": len(enriched),
        "technical_models": int(enriched["technical_model_key"].nunique(dropna=True)),
        "technical_variants": int(enriched["technical_variant_key"].nunique(dropna=True)),
        "presentation_groups": int(enriched["presentation_group_key"].nunique(dropna=True)),
        "hidden_variants": max(
            len(enriched)
            - int(enriched["presentation_group_key"].nunique(dropna=True)),
            0,
        ),
        "explicit_records": int(source.eq("explicit").sum()),
        "mixed_records": int(source.eq("mixed_explicit_derived").sum()),
        "derived_records": int(source.eq("derived_v2").sum()),
    }


def _existing_hierarchy_key(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("", index=frame.index, dtype="string")
    values = frame[column].astype("string").str.strip()
    return values.fillna("")


def _derive_technical_model_keys(frame: pd.DataFrame) -> pd.Series:
    manufacturer = _coalesced_text(frame, ["manufacturer_key", "manufacturer_name"])
    family = _coalesced_text(frame, ["product_family_key", "product_family_name"])
    model = _coalesced_text(frame, ["model_key", "model_name", "system_key", "record_id"])
    return _stable_hierarchy_key_series("tm", [manufacturer, family, model])


def _derive_technical_variant_keys(
    frame: pd.DataFrame, technical_model_keys: pd.Series
) -> pd.Series:
    parts: list[pd.Series] = [technical_model_keys.astype("string")]
    for column in PRESENTATION_GROUP_TEXT_FIELDS:
        if column in frame.columns:
            values = frame[column].astype("string").str.strip().str.casefold()
            values = values.mask(values.eq(""), "<na>").fillna("<na>")
        else:
            values = pd.Series("<na>", index=frame.index, dtype="string")
        parts.append(values)
    for column in PRESENTATION_GROUP_NUMERIC_FIELDS:
        if column in frame.columns:
            numeric = numeric_series(frame[column])
            values = numeric.map(
                lambda value: "<na>" if pd.isna(value) else f"{float(value):.8g}"
            ).astype("string")
        else:
            values = pd.Series("<na>", index=frame.index, dtype="string")
        parts.append(values)
    return _stable_hierarchy_key_series("tv", parts)


def _derive_presentation_group_keys(technical_variant_keys: pd.Series) -> pd.Series:
    return _stable_hierarchy_key_series(
        "pg", [technical_variant_keys.astype("string")]
    )


def _stable_hierarchy_key_series(prefix: str, parts: Sequence[pd.Series]) -> pd.Series:
    if not parts:
        return pd.Series(dtype="string")
    index = parts[0].index
    normalised_parts = [part.reindex(index).astype("string").fillna("<na>") for part in parts]
    rows = zip(*(part.tolist() for part in normalised_parts))
    return pd.Series(
        [_stable_hierarchy_key(prefix, values) for values in rows],
        index=index,
        dtype="string",
    )


def _stable_hierarchy_key(prefix: str, values: Sequence[Any]) -> str:
    canonical = "|".join(str(value).strip().casefold() or "<na>" for value in values)
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]
    readable_tokens = [
        token for token in (_key_slug(value) for value in values[:3]) if token and token != "na"
    ]
    readable = "-".join(readable_tokens)[:72].strip("-") or "unknown"
    return f"{prefix}-{readable}-{digest}"


def _key_slug(value: Any) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^a-z0-9]+", "-", ascii_text.casefold()).strip("-")
    return token or "na"


def _hierarchy_collision_count(
    frame: pd.DataFrame, key_column: str, parent_column: str
) -> int:
    if key_column not in frame.columns or parent_column not in frame.columns:
        return 0
    pairs = frame[[key_column, parent_column]].dropna().drop_duplicates()
    if pairs.empty:
        return 0
    counts = pairs.groupby(key_column, dropna=False)[parent_column].nunique(dropna=True)
    return int(counts.gt(1).sum())


def aggregate_presentation_groups(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse finish/article variants into technical product groups.

    The returned tuple contains one representative row per technical group and
    all original member rows annotated with the complete technical hierarchy.
    Explicit database keys are preferred; deterministic derived keys are used
    only as a migration-safe fallback.
    """

    if frame.empty:
        empty = add_product_hierarchy_keys(frame)
        return empty.copy(), empty

    members = add_product_hierarchy_keys(frame)

    grouped = members.groupby("presentation_group_key", sort=False, dropna=False)
    representative_indices = grouped.head(1).index
    representatives = members.loc[representative_indices].copy()

    group_sources = grouped["hierarchy_key_source"].agg(_join_unique_nonempty_text)
    representatives["hierarchy_key_source"] = representatives[
        "presentation_group_key"
    ].map(group_sources)

    member_counts = grouped.size()
    representatives["group_member_count"] = representatives[
        "presentation_group_key"
    ].map(member_counts).astype("int64")

    finish_counts = grouped["finish_name"].agg(_unique_nonempty_text_count) if "finish_name" in members.columns else member_counts * 0
    finish_lists = grouped["finish_name"].agg(_join_unique_nonempty_text) if "finish_name" in members.columns else member_counts.map(lambda _: "")
    representatives["finish_variant_count"] = representatives[
        "presentation_group_key"
    ].map(finish_counts).astype("int64")
    representatives["available_finishes"] = representatives[
        "presentation_group_key"
    ].map(finish_lists).replace("", pd.NA)

    # Prefer manufacturer article numbers, but use record_id for assembled
    # configurations without a dedicated article number. This also counts mixed
    # groups correctly when only some members have an article number.
    article_identity = _coalesced_text(
        members, ["manufacturer_article_no", "record_id"]
    )
    article_counts = article_identity.groupby(
        members["presentation_group_key"], sort=False
    ).nunique(dropna=True)
    representatives["article_variant_count"] = representatives[
        "presentation_group_key"
    ].map(article_counts).astype("int64")

    product_links: dict[str, object] = {}
    product_link_types: dict[str, object] = {}
    for group_key, group in grouped:
        product_url = _first_nonempty_text(group.get("product_url", pd.Series(dtype="string")))
        evidence_url = _first_nonempty_text(group.get("evidence_url", pd.Series(dtype="string")))
        if product_url:
            product_links[str(group_key)] = product_url
            product_link_types[str(group_key)] = "Official product page"
        elif evidence_url:
            product_links[str(group_key)] = evidence_url
            product_link_types[str(group_key)] = "Technical source"
        else:
            product_links[str(group_key)] = pd.NA
            product_link_types[str(group_key)] = pd.NA

    representatives["product_link"] = representatives["presentation_group_key"].map(product_links)
    representatives["product_link_type"] = representatives[
        "presentation_group_key"
    ].map(product_link_types)

    return representatives.reset_index(drop=True), members.reset_index(drop=True)



def filter_reference_comparables(
    grouped: pd.DataFrame,
    reference_group_key: str,
    *,
    numeric_tolerances: Mapping[str, Mapping[str, Any]] | None = None,
    exact_match_fields: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filter technical product groups around a selected reference product.

    The reference is used only to define hard comparison tolerances. No
    similarity score is calculated. A candidate either satisfies every active
    tolerance/exact-match requirement or it is excluded. Delta columns are
    added for transparent review but never enter the independent benchmark
    score.
    """

    if grouped.empty or "presentation_group_key" not in grouped.columns:
        return grouped.iloc[0:0].copy(), pd.DataFrame()

    reference_key = str(reference_group_key).strip()
    reference_rows = grouped[
        grouped["presentation_group_key"].astype("string").str.strip().eq(reference_key)
    ]
    if reference_rows.empty:
        raise ValueError("The selected reference product was not found in the grouped data.")
    reference = reference_rows.iloc[0]

    candidates = grouped.copy()
    eligible_mask = pd.Series(True, index=candidates.index, dtype="bool")
    audit_rows: list[dict[str, Any]] = []

    for field in exact_match_fields:
        if field not in candidates.columns:
            raise ValueError(f"Exact-match field is unavailable: {field}")
        reference_value = _text(reference.get(field)).strip().casefold()
        if not reference_value:
            raise ValueError(
                f"The reference product has no explicit value for {field}; "
                "the exact-match requirement cannot be applied."
            )
        before_count = int(eligible_mask.sum())
        candidate_values = candidates[field].astype("string").str.strip().str.casefold()
        field_mask = candidate_values.eq(reference_value)
        eligible_mask &= field_mask
        audit_rows.append(
            {
                "field": field,
                "label": REFERENCE_EXACT_FIELDS.get(field, field),
                "comparison_type": "exact match",
                "reference_value": reference.get(field),
                "tolerance_mode": None,
                "tolerance_value": None,
                "accepted_minimum": None,
                "accepted_maximum": None,
                "unit": None,
                "eligible_before": before_count,
                "eligible_after": int(eligible_mask.sum()),
            }
        )

    for field, rule in (numeric_tolerances or {}).items():
        if field not in candidates.columns:
            raise ValueError(f"Numeric comparison field is unavailable: {field}")
        reference_value = pd.to_numeric(pd.Series([reference.get(field)]), errors="coerce").iloc[0]
        if pd.isna(reference_value):
            raise ValueError(
                f"The reference product has no explicit value for {field}; "
                "the tolerance cannot be applied."
            )

        tolerance_value = max(float(rule.get("value", 0.0)), 0.0)
        mode = str(rule.get("mode", "absolute")).strip().casefold()
        if mode not in {"absolute", "percent"}:
            raise ValueError(f"Unsupported tolerance mode for {field}: {mode}")
        absolute_tolerance = (
            abs(float(reference_value)) * tolerance_value / 100.0
            if mode == "percent"
            else tolerance_value
        )
        accepted_minimum = float(reference_value) - absolute_tolerance
        accepted_maximum = float(reference_value) + absolute_tolerance

        before_count = int(eligible_mask.sum())
        values = numeric_series(candidates[field])
        field_mask = values.notna() & values.between(
            accepted_minimum, accepted_maximum, inclusive="both"
        )
        eligible_mask &= field_mask
        audit_rows.append(
            {
                "field": field,
                "label": REFERENCE_NUMERIC_FIELDS.get(field, {}).get("label", field),
                "comparison_type": "tolerance range",
                "reference_value": float(reference_value),
                "tolerance_mode": mode,
                "tolerance_value": tolerance_value,
                "accepted_minimum": accepted_minimum,
                "accepted_maximum": accepted_maximum,
                "unit": REFERENCE_NUMERIC_FIELDS.get(field, {}).get("unit"),
                "eligible_before": before_count,
                "eligible_after": int(eligible_mask.sum()),
            }
        )

    reference_mask = candidates["presentation_group_key"].astype("string").str.strip().eq(
        reference_key
    )
    eligible_mask |= reference_mask
    comparable = candidates.loc[eligible_mask].copy()
    comparable["Is_Reference"] = comparable["presentation_group_key"].astype(
        "string"
    ).str.strip().eq(reference_key)
    comparable["Reference_Label"] = comparable["Is_Reference"].map(
        {True: "REFERENCE", False: ""}
    )
    comparable["Comparison_Status"] = comparable["Is_Reference"].map(
        {True: "Reference product", False: "Meets tolerance requirements"}
    )

    # Deltas are informational only and are deliberately not converted into a
    # similarity score or used by the independent ranking engine.
    for field in REFERENCE_NUMERIC_FIELDS:
        if field not in comparable.columns:
            continue
        reference_value = pd.to_numeric(pd.Series([reference.get(field)]), errors="coerce").iloc[0]
        values = numeric_series(comparable[field])
        delta_column = f"Delta_vs_reference_{field}"
        delta_percent_column = f"Delta_vs_reference_{field}_pct"
        comparable[delta_column] = values - reference_value
        if pd.notna(reference_value) and float(reference_value) != 0.0:
            comparable[delta_percent_column] = (
                comparable[delta_column] / abs(float(reference_value)) * 100.0
            )
        else:
            comparable[delta_percent_column] = pd.NA

    comparable = comparable.sort_values(
        ["Is_Reference", "manufacturer_name", "model_name"],
        ascending=[False, True, True],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    return comparable, pd.DataFrame(audit_rows)


def execute_reference_product_comparison(
    frame: pd.DataFrame,
    reference_group_key: str,
    *,
    numeric_tolerances: Mapping[str, Mapping[str, Any]] | None = None,
    exact_match_fields: Sequence[str] = (),
    weights: Mapping[str, float | int],
    top_n: int = 10,
) -> ReferenceComparisonExecution:
    """Select comparable systems and score them independently of the reference.

    Tolerances only define eligibility. Advanced benchmark scores are
    normalised across the resulting comparable set. The reference receives the
    same score as every other product when its active scoring data is complete.
    If it is not rankable, it remains visible with an explicit status and no
    artificial score.
    """

    grouped, members = aggregate_presentation_groups(frame)
    comparable_groups, tolerance_audit = filter_reference_comparables(
        grouped,
        reference_group_key,
        numeric_tolerances=numeric_tolerances,
        exact_match_fields=exact_match_fields,
    )
    if comparable_groups.empty:
        return ReferenceComparisonExecution(
            reference=grouped.iloc[0:0].copy(),
            comparable_groups=comparable_groups,
            comparable_members=members.iloc[0:0].copy(),
            ranked_all=comparable_groups.copy(),
            ranked=comparable_groups.copy(),
            unranked=comparable_groups.copy(),
            tolerance_audit=tolerance_audit,
        )

    comparable_keys = set(
        comparable_groups["presentation_group_key"].astype("string").dropna().tolist()
    )
    comparable_members = members[
        members["presentation_group_key"].astype("string").isin(comparable_keys)
    ].copy()

    scored_complete, scored_members = score_advanced_product_groups(
        comparable_members,
        weights,
        missing_data_policy="require_complete",
    )
    # A second pass supplies transparent group aggregates and missing-field
    # diagnostics for products that cannot be ranked. Its score is discarded.
    scored_all, _ = score_advanced_product_groups(
        comparable_members,
        weights,
        missing_data_policy="allow_incomplete_zero_score",
    )

    annotation_columns = [
        column
        for column in comparable_groups.columns
        if column.startswith("Delta_vs_reference_")
        or column in {"presentation_group_key", "Is_Reference", "Reference_Label", "Comparison_Status"}
    ]
    annotations = comparable_groups[annotation_columns].drop_duplicates(
        subset=["presentation_group_key"], keep="first"
    )

    if not scored_complete.empty:
        scored_complete = scored_complete.merge(
            annotations,
            on="presentation_group_key",
            how="left",
            suffixes=("", "_comparison"),
        )
        scored_complete = scored_complete.sort_values(
            "Final_Score_%", ascending=False, kind="stable", na_position="last"
        ).reset_index(drop=True)
        scored_complete.insert(0, "Rank", range(1, len(scored_complete) + 1))
        scored_complete["Ranking_Status"] = "Ranked"
    else:
        scored_complete = scored_complete.copy()

    scored_keys = set(
        scored_complete.get("presentation_group_key", pd.Series(dtype="string"))
        .astype("string")
        .dropna()
        .tolist()
    )
    unranked = scored_all[
        ~scored_all["presentation_group_key"].astype("string").isin(scored_keys)
    ].copy()
    if not unranked.empty:
        unranked = unranked.merge(
            annotations,
            on="presentation_group_key",
            how="left",
            suffixes=("", "_comparison"),
        )
        unranked["Rank"] = pd.NA
        unranked["Final_Score_%"] = pd.NA
        for score_column in (
            "Score_Flow_Rate_%",
            "Score_Installation_Height_%",
            "Score_V4A_%",
            "Score_Sales_Price_%",
            "Score_Colours_%",
            "Score_Before_Completeness_Penalty_%",
        ):
            if score_column in unranked.columns:
                unranked[score_column] = pd.NA
        unranked["Ranking_Status"] = "Not rankable — missing data"
        # The reference is retained for transparency even though the active
        # ranking policy requires complete data. Keep the audit label aligned
        # with that behaviour instead of exposing the diagnostic second-pass
        # policy used only to calculate missing-field information.
        if "Is_Reference" in unranked.columns:
            reference_retained_mask = unranked["Is_Reference"].fillna(False).astype(bool)
            unranked.loc[
                reference_retained_mask, "Missing_Data_Policy"
            ] = "require_complete_reference_retained"

    reference_key = str(reference_group_key).strip()
    reference = comparable_groups[
        comparable_groups["presentation_group_key"].astype("string").str.strip().eq(
            reference_key
        )
    ].copy()

    display_ranked = scored_complete.head(max(int(top_n), 1)).copy()
    reference_ranked = scored_complete[
        scored_complete["presentation_group_key"].astype("string").str.strip().eq(
            reference_key
        )
    ]
    reference_unranked = unranked[
        unranked["presentation_group_key"].astype("string").str.strip().eq(reference_key)
    ]
    displayed_keys = set(
        display_ranked.get("presentation_group_key", pd.Series(dtype="string"))
        .astype("string")
        .dropna()
        .tolist()
    )
    if not reference_ranked.empty and reference_key not in displayed_keys:
        display_ranked = pd.concat(
            [display_ranked, reference_ranked], ignore_index=True, sort=False
        )
    elif not reference_unranked.empty:
        reference_for_display = reference_unranked.dropna(axis=1, how="all")
        display_ranked = pd.concat(
            [display_ranked, reference_for_display], ignore_index=True, sort=False
        )

    if not display_ranked.empty:
        if "Rank" not in display_ranked.columns:
            display_ranked["Rank"] = pd.NA
        if "Is_Reference" not in display_ranked.columns:
            display_ranked["Is_Reference"] = False
        display_ranked["Reference_Label"] = display_ranked.get(
            "Reference_Label", pd.Series("", index=display_ranked.index)
        ).fillna("")
        display_ranked = display_ranked.sort_values(
            ["Rank", "Is_Reference"],
            ascending=[True, False],
            kind="stable",
            na_position="last",
        ).reset_index(drop=True)

    competitor_unranked = unranked[
        ~unranked.get("Is_Reference", pd.Series(False, index=unranked.index)).fillna(False)
    ].copy()

    return ReferenceComparisonExecution(
        reference=reference,
        comparable_groups=comparable_groups,
        comparable_members=scored_members,
        ranked_all=scored_complete,
        ranked=display_ranked,
        unranked=competitor_unranked,
        tolerance_audit=tolerance_audit,
    )



def mandatory_requirements_from_filters(
    filters: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Normalise UI/API filter payload into explicit hard requirements.

    The loose ``filters`` object is retained for backward compatibility and UI
    state reconstruction. This ordered list is the canonical, auditable form
    intended for exports, APIs and a future LLM query layer.
    """

    payload = dict(filters or {})
    requirements: list[dict[str, Any]] = []

    def add(
        field: str,
        operator: str,
        *,
        value: Any = None,
        minimum: Any = None,
        maximum: Any = None,
        unit: str | None = None,
        notes: str | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "field": field,
            "label": MANDATORY_FILTER_LABELS.get(field, field),
            "operator": operator,
        }
        if value is not None:
            row["value"] = _json_safe_value(value)
        if minimum is not None:
            row["minimum"] = _json_safe_value(minimum)
        if maximum is not None:
            row["maximum"] = _json_safe_value(maximum)
        if unit:
            row["unit"] = unit
        if notes:
            row["notes"] = notes
        requirements.append(row)

    drain_form = payload.get("drain_form")
    if drain_form not in {None, "", "all"}:
        add("mapped_drain_form", "equals", value=drain_form)

    solution_types = payload.get("solution_types")
    if isinstance(solution_types, Sequence) and not isinstance(solution_types, (str, bytes)):
        selected_solution_types = [
            str(item) for item in solution_types if str(item) != "all"
        ]
        if selected_solution_types:
            add("mapped_solution_type", "in", value=selected_solution_types)

    include_incomplete = bool(
        payload.get("include_incomplete_systems_and_components", False)
    )
    add(
        "benchmark_scope",
        "equals",
        value=(
            "active systems plus incomplete systems/components"
            if include_incomplete
            else "active complete/assembled systems only"
        ),
    )

    manufacturers = payload.get("manufacturers")
    if isinstance(manufacturers, Sequence) and not isinstance(
        manufacturers, (str, bytes)
    ):
        selected = [str(item) for item in manufacturers if str(item) != "all"]
        if selected:
            add("manufacturer_key", "in", value=selected)

    length_range = payload.get("length_range_mm")
    if (
        isinstance(length_range, Sequence)
        and not isinstance(length_range, (str, bytes))
        and len(length_range) == 2
    ):
        add(
            "installable_length_mm",
            "overlaps_verified_range",
            minimum=length_range[0],
            maximum=length_range[1],
            unit="mm",
            notes=(
                "Systems without a verified range are also retained"
                if bool(payload.get("include_unverified_length", False))
                else "Only systems with a verified overlapping range are retained"
            ),
        )

    range_fields = (
        ("primary_flow_rate_range_lps", "flow_rate_primary_lps", "l/s"),
        ("installation_height_range_mm", "height_adj_min_mm", "mm"),
    )
    for payload_key, field, unit in range_fields:
        selected_range = payload.get(payload_key)
        if (
            isinstance(selected_range, Sequence)
            and not isinstance(selected_range, (str, bytes))
            and len(selected_range) == 2
        ):
            add(
                field,
                "between_inclusive",
                minimum=selected_range[0],
                maximum=selected_range[1],
                unit=unit,
            )

    numeric_filters = payload.get("numeric_filters", {})
    if isinstance(numeric_filters, Mapping):
        for field, selected_range in numeric_filters.items():
            if (
                isinstance(selected_range, Sequence)
                and not isinstance(selected_range, (str, bytes))
                and len(selected_range) == 2
            ):
                unit = "mm" if str(field).endswith("_mm") else None
                add(
                    str(field),
                    "between_inclusive",
                    minimum=selected_range[0],
                    maximum=selected_range[1],
                    unit=unit,
                )

    attributes = payload.get("attributes", {})
    if isinstance(attributes, Mapping):
        for field, values in attributes.items():
            if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                selected = [str(item) for item in values if str(item) != "all"]
                if selected:
                    add(str(field), "in", value=selected)
            elif values not in {None, "", "all"}:
                add(str(field), "equals", value=values)

    return requirements


def mandatory_requirements_table(
    requirements: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    """Return a user-facing audit table for explicit mandatory requirements."""

    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        value = requirement.get("value")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            value = "; ".join(str(item) for item in value)
        minimum = requirement.get("minimum")
        maximum = requirement.get("maximum")
        if minimum is not None or maximum is not None:
            range_text = f"{minimum} – {maximum}"
        else:
            range_text = None
        rows.append(
            {
                "Field": requirement.get("field"),
                "Requirement": requirement.get("label"),
                "Operator": requirement.get("operator"),
                "Value": value if value is not None else range_text,
                "Unit": requirement.get("unit"),
                "Notes": requirement.get("notes"),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["Field", "Requirement", "Operator", "Value", "Unit", "Notes"],
    )

def build_ranking_request(
    *,
    mode: str,
    criteria: Mapping[str, bool],
    weights: Mapping[str, float | int] | None = None,
    criterion_labels: Mapping[str, str] | None = None,
    top_n: int = 10,
    filters: Mapping[str, Any] | None = None,
    missing_data_policy: str = "require_complete",
    grouping_policy: str = PRESENTATION_GROUPING_POLICY,
) -> dict[str, Any]:
    """Build a JSON-serialisable, versioned ranking request.

    This request is intentionally independent of Streamlit. The same structure
    can later be produced by an API or an LLM orchestration layer while the
    deterministic data layer remains responsible for validation and scoring.
    """

    normalised_mode = str(mode).strip().casefold()
    if normalised_mode not in RANKING_REQUEST_MODES:
        raise ValueError(f"Unsupported ranking mode: {mode}")
    if normalised_mode == "single_parameter" and len(criteria) != 1:
        raise ValueError("Single-parameter ranking requires exactly one criterion.")
    if normalised_mode == "multi_parameter" and len(criteria) < 2:
        raise ValueError("Multi-parameter ranking requires at least two criteria.")
    if int(top_n) <= 0:
        raise ValueError("top_n must be greater than zero.")
    if missing_data_policy not in RANKING_MISSING_DATA_POLICIES:
        raise ValueError(f"Unsupported missing-data policy: {missing_data_policy}")

    normalised_weights = normalise_ranking_weights(criteria, weights)
    request_criteria: list[dict[str, Any]] = []
    for column, higher_is_better in criteria.items():
        request_criteria.append(
            {
                "field": str(column),
                "label": str((criterion_labels or {}).get(column, column)),
                "direction": "higher" if bool(higher_is_better) else "lower",
                "raw_weight": float((weights or {}).get(column, 1.0)),
                "normalised_weight": float(normalised_weights[column]),
            }
        )

    filter_payload = dict(filters or {})
    return {
        "schema_version": RANKING_REQUEST_SCHEMA_VERSION,
        "mode": normalised_mode,
        "filters": _json_safe_value(filter_payload),
        "mandatory_requirements": mandatory_requirements_from_filters(filter_payload),
        "criteria": request_criteria,
        "top_n": int(top_n),
        "missing_data_policy": missing_data_policy,
        "grouping_policy": str(grouping_policy),
        "hierarchy_schema_version": HIERARCHY_SCHEMA_VERSION,
    }


def validate_ranking_request(request: Mapping[str, Any]) -> None:
    """Validate a structured request before any ranking is executed."""

    if str(request.get("schema_version", "")) != RANKING_REQUEST_SCHEMA_VERSION:
        raise ValueError("Unsupported ranking request schema_version.")
    mode = str(request.get("mode", "")).strip().casefold()
    if mode not in RANKING_REQUEST_MODES:
        raise ValueError("Unsupported ranking request mode.")
    criteria = request.get("criteria")
    if not isinstance(criteria, Sequence) or isinstance(criteria, (str, bytes)):
        raise ValueError("Ranking request criteria must be a list.")
    criterion_count = len(criteria)
    if mode == "single_parameter" and criterion_count != 1:
        raise ValueError("Single-parameter ranking requires exactly one criterion.")
    if mode == "multi_parameter" and criterion_count < 2:
        raise ValueError("Multi-parameter ranking requires at least two criteria.")
    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            raise ValueError("Each ranking criterion must be an object.")
        if not str(criterion.get("field", "")).strip():
            raise ValueError("Each ranking criterion requires a field.")
        if criterion.get("direction") not in {"higher", "lower"}:
            raise ValueError("Ranking criterion direction must be higher or lower.")
        weight = float(criterion.get("normalised_weight", 0.0))
        if weight < 0:
            raise ValueError("Ranking criterion weights cannot be negative.")
    mandatory_requirements = request.get("mandatory_requirements")
    if not isinstance(mandatory_requirements, Sequence) or isinstance(
        mandatory_requirements, (str, bytes)
    ):
        raise ValueError("Ranking request mandatory_requirements must be a list.")
    for requirement in mandatory_requirements:
        if not isinstance(requirement, Mapping):
            raise ValueError("Each mandatory requirement must be an object.")
        if not str(requirement.get("field", "")).strip():
            raise ValueError("Each mandatory requirement requires a field.")
        if not str(requirement.get("operator", "")).strip():
            raise ValueError("Each mandatory requirement requires an operator.")

    if int(request.get("top_n", 0)) <= 0:
        raise ValueError("Ranking request top_n must be greater than zero.")
    if request.get("missing_data_policy") not in RANKING_MISSING_DATA_POLICIES:
        raise ValueError("Unsupported ranking request missing_data_policy.")
    hierarchy_version = str(
        request.get("hierarchy_schema_version", HIERARCHY_SCHEMA_VERSION)
    )
    if hierarchy_version != HIERARCHY_SCHEMA_VERSION:
        raise ValueError("Unsupported hierarchy_schema_version.")


def execute_ranking_request(
    frame: pd.DataFrame, request: Mapping[str, Any]
) -> RankingExecution:
    """Execute a validated request against an already mandatory-filtered frame."""

    validate_ranking_request(request)
    grouped, members = aggregate_presentation_groups(frame)
    criteria_rows = list(request["criteria"])
    criteria = {
        str(item["field"]): item["direction"] == "higher"
        for item in criteria_rows
    }
    weights = {
        str(item["field"]): float(item.get("normalised_weight", 0.0))
        for item in criteria_rows
    }
    mode = str(request["mode"])
    if mode == "single_parameter":
        column, higher_is_better = next(iter(criteria.items()))
        ranked_all = rank_single_parameter(
            grouped, column, higher_is_better=higher_is_better
        )
    else:
        ranked_all = rank_multiple_parameters(grouped, criteria, weights=weights)

    top_n = int(request["top_n"])
    ranking = ranked_all.head(top_n).reset_index(drop=True)
    return RankingExecution(
        request=dict(request),
        ranked_all=ranked_all,
        ranking=ranking,
        grouped=grouped,
        members=members,
    )


def ranking_request_tables(
    request: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create audit tables for criteria, filters and request-level settings."""

    validate_ranking_request(request)
    criteria = pd.DataFrame(list(request["criteria"]))
    if not criteria.empty:
        criteria["normalised_weight_percent"] = (
            pd.to_numeric(criteria["normalised_weight"], errors="coerce") * 100.0
        )

    filters = mandatory_requirements_table(
        list(request.get("mandatory_requirements", []))
    )

    settings = pd.DataFrame(
        [
            {
                "schema_version": request["schema_version"],
                "mode": request["mode"],
                "top_n": request["top_n"],
                "missing_data_policy": request["missing_data_policy"],
                "grouping_policy": request["grouping_policy"],
                "hierarchy_schema_version": request.get(
                    "hierarchy_schema_version", HIERARCHY_SCHEMA_VERSION
                ),
            }
        ]
    )
    return criteria, filters, settings


def _flatten_audit_values(
    prefix: str, value: Any, rows: list[dict[str, Any]]
) -> None:
    if isinstance(value, Mapping):
        if not value and prefix:
            rows.append({"filter": prefix, "value": "{}"})
        for key, nested in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten_audit_values(child, nested, rows)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        display_value = "; ".join(str(item) for item in value)
    elif value is None:
        display_value = "not active"
    else:
        display_value = value
    rows.append({"filter": prefix or "filters", "value": display_value})


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if pd.isna(value):
        return None
    return str(value)


def rank_single_parameter(
    frame: pd.DataFrame,
    column: str,
    *,
    higher_is_better: bool,
    top_n: int | None = None,
) -> pd.DataFrame:
    """Rank technical product groups by one numeric parameter.

    Rows without an explicit value for the selected parameter are excluded.
    The 0-100 score is calculated only within the already-filtered comparison
    set, matching the behaviour of the existing weighted scorer.
    """

    if frame.empty or column not in frame.columns:
        return frame.iloc[0:0].copy()

    ranked = frame.copy()
    ranked[column] = numeric_series(ranked[column])
    ranked = ranked[ranked[column].notna()].copy()
    if ranked.empty:
        return ranked

    ranked["Ranking_Score_%"] = _normalised_numeric_score(
        ranked, column, higher_is_better=higher_is_better
    )
    sort_columns = [column]
    ascending = [not higher_is_better]
    for optional_column in ("manufacturer_name", "model_name", "record_id"):
        if optional_column in ranked.columns:
            sort_columns.append(optional_column)
            ascending.append(True)
    ranked = ranked.sort_values(
        sort_columns,
        ascending=ascending,
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))
    if top_n is not None:
        ranked = ranked.head(int(top_n)).reset_index(drop=True)
    return ranked



def multi_parameter_score_column(column: str) -> str:
    """Return the deterministic score-column name for a ranking criterion."""

    return f"Score_{column}_%"


def multi_parameter_weight_column(column: str) -> str:
    """Return the deterministic weight-column name for a ranking criterion."""

    return f"Weight_{column}_%"


def normalise_ranking_weights(
    criteria: Mapping[str, bool],
    weights: Mapping[str, float | int] | None = None,
) -> dict[str, float]:
    """Normalise non-negative criterion weights so that they sum to one.

    Missing weights default to ``1``. Negative values are treated as zero. If
    all effective values are zero, the function falls back to equal weights.
    Keeping the normalisation in the data layer makes the same ranking request
    reusable from Streamlit, an API, or a future LLM orchestration layer.
    """

    if not criteria:
        return {}

    effective = {
        column: max(float((weights or {}).get(column, 1.0)), 0.0)
        for column in criteria
    }
    total = sum(effective.values())
    if total <= 0:
        equal = 1.0 / len(criteria)
        return {column: equal for column in criteria}
    return {column: value / total for column, value in effective.items()}


def rank_multiple_parameters(
    frame: pd.DataFrame,
    criteria: Mapping[str, bool],
    *,
    weights: Mapping[str, float | int] | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """Rank technical product groups by an optimal combination of metrics.

    ``criteria`` maps a numeric source column to its ranking direction, where
    ``True`` means higher values are better and ``False`` means lower values
    are better. Only rows with an explicit value for every selected criterion
    are eligible. Scores are normalised to 0-100 within that complete, already
    filtered comparison set and combined as a weighted arithmetic mean. Equal
    weights are used when ``weights`` is omitted.
    """

    if frame.empty or len(criteria) < 2:
        return frame.iloc[0:0].copy()
    if any(column not in frame.columns for column in criteria):
        return frame.iloc[0:0].copy()

    ranked = frame.copy()
    for column in criteria:
        ranked[column] = numeric_series(ranked[column])

    complete_mask = pd.Series(True, index=ranked.index, dtype="bool")
    for column in criteria:
        complete_mask &= ranked[column].notna()
    ranked = ranked.loc[complete_mask].copy()
    if ranked.empty:
        return ranked

    normalised_weights = normalise_ranking_weights(criteria, weights)

    weighted_score = pd.Series(0.0, index=ranked.index, dtype="float64")
    criterion_score_columns: list[str] = []
    for column, higher_is_better in criteria.items():
        score_column = multi_parameter_score_column(column)
        weight_column = multi_parameter_weight_column(column)
        criterion_score_columns.append(score_column)
        ranked[score_column] = _normalised_numeric_score(
            ranked, column, higher_is_better=bool(higher_is_better)
        )
        ranked[weight_column] = normalised_weights[column] * 100.0
        weighted_score += ranked[score_column] * normalised_weights[column]

    ranked["Ranking_Score_%"] = weighted_score
    ranked["Ranking_Criteria_Count"] = len(criteria)
    ranked["Ranking_Weight_Sum_%"] = 100.0

    sort_columns = ["Ranking_Score_%", *criterion_score_columns]
    ascending = [False] * len(sort_columns)
    for optional_column in ("manufacturer_name", "model_name", "record_id"):
        if optional_column in ranked.columns:
            sort_columns.append(optional_column)
            ascending.append(True)
    ranked = ranked.sort_values(
        sort_columns,
        ascending=ascending,
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))
    if top_n is not None:
        ranked = ranked.head(int(top_n)).reset_index(drop=True)
    return ranked

def _presentation_group_keys(frame: pd.DataFrame) -> pd.Series:
    """Compatibility wrapper returning the stable hierarchy presentation key."""

    return add_product_hierarchy_keys(frame)["presentation_group_key"]


def _coalesced_text(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    result = pd.Series(pd.NA, index=frame.index, dtype="string")
    for column in columns:
        if column not in frame.columns:
            continue
        values = frame[column].astype("string").str.strip()
        usable = values.notna() & values.ne("")
        result = result.where(result.notna() & result.ne(""), values.where(usable))
    return result.fillna("<na>").str.casefold()


def _unique_nonempty_text_count(series: pd.Series) -> int:
    values = series.astype("string").str.strip().dropna()
    return len({value for value in values.tolist() if value})


def _join_unique_nonempty_text(series: pd.Series) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for value in series.astype("string").str.strip().dropna().tolist():
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return "; ".join(values)


def _first_nonempty_text(series: pd.Series) -> str | None:
    for value in series.astype("string").str.strip().dropna().tolist():
        if value:
            return value
    return None


def selection_labels(frame: pd.DataFrame) -> dict[str, str]:
    """Map a selectbox label to a unique ``record_id``."""

    if "record_id" not in frame.columns:
        return {}

    labels: dict[str, str] = {}
    for position, (_, row) in enumerate(frame.iterrows(), start=1):
        record_id = row.get("record_id")
        if pd.isna(record_id):
            continue
        variant_name = row.get("variant_name", "N/A")
        variant_label = "N/A" if pd.isna(variant_name) or not str(variant_name).strip() else str(variant_name)
        label = f"{record_id} — {variant_label}"
        if label in labels:
            label = f"{label} ({position})"
        labels[label] = str(record_id)
    return labels


def related_rows(frame: pd.DataFrame, link_column: str, record_id: str) -> pd.DataFrame:
    """Find rows linked to the selected ``record_id``."""

    if link_column not in frame.columns:
        return frame.iloc[0:0].copy()
    links = frame[link_column].astype("string").str.strip()
    return frame[links.eq(str(record_id))].copy()


def available_columns(frame: pd.DataFrame, requested_columns: Iterable[str]) -> list[str]:
    """Return only columns that actually exist in the input."""

    return [column for column in requested_columns if column in frame.columns]
