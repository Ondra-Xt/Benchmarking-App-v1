"""Schema-aware Excel loader for shower-drain benchmark masters.

The application historically consumed three physical sheets. Canonical v2
masters may either expose layers as physical worksheets or package secondary
layers into ``81_Secondary_Archive_Payload``. This module normalises both
layouts into the same table dictionary without modifying source workbooks.
"""

from __future__ import annotations

import base64
import bz2
import json
from io import BytesIO
from typing import Any

import pandas as pd


DATASET_SHEETS: dict[str, str] = {
    "flat": "01_Flat_Input",
    "bom": "02_BOM_Components",
    "evidence": "03_Evidence",
    "prices": "04_Price_Observations",
    "missing_parts": "05_Missing_Parts",
    "hydraulics": "06_Hydraulic_Observations",
    "technical": "07_Technical_Observations",
    "technical_audit": "08_System_Technical_Audit",
    "exact_lifecycle": "09_Exact_Identity_Lifecycle",
    "record_lifecycle": "10_Record_Lifecycle",
    "package_contents": "11_Package_Contents",
    "compatibility": "12_Component_Compat_Graph",
    "regional_provenance": "13_Regional_Provenance",
    "controlled_gaps": "14_Controlled_Gaps",
}

SHEET_TO_DATA_KEY = {sheet_name: key for key, sheet_name in DATASET_SHEETS.items()}
SECONDARY_ARCHIVE_MANIFEST = "80_Secondary_Archive_Manifest"
SECONDARY_ARCHIVE_PAYLOAD = "81_Secondary_Archive_Payload"

# Identifier columns are forced to text so article numbers and IDs keep leading
# zeros. Numeric technical values intentionally keep pandas' normal inference.
TEXT_COLUMNS: dict[str, tuple[str, ...]] = {
    "flat": (
        "record_id",
        "system_key",
        "benchmark_entity_type",
        "product_category",
        "system_role",
        "product_family_name",
        "manufacturer_article_no",
        "manufacturer_key",
        "candidate_type",
        "variant_name",
        "material_v4a",
        "din_en_1253_status",
        "din_en_18534_status",
        "sealing_fleece_preassembled",
        "outlet_direction_selectable",
        "schema_version",
        "exact_identity_key",
        "identity_grain",
        "record_origin",
        "technical_completeness_flag",
        "lifecycle_status_v2",
        "regional_identity_status",
    ),
    "bom": (
        "relation_id",
        "parent_system_key",
        "parent_record_id",
        "component_record_id",
        "component_article_no",
        "component_name",
        "component_role",
    ),
    "evidence": (
        "linked_record_id",
        "linked_entity_type",
        "entity_type",
        "field_name",
        "source_url",
        "source_excerpt",
        "evidence_excerpt",
    ),
    "prices": (
        "price_observation_id",
        "price_subject_type",
        "exact_identity_key",
        "linked_record_id",
        "manufacturer_article_no",
        "seller_name",
        "currency",
        "market_region",
        "source_url",
    ),
    "missing_parts": ("system_key", "record_id", "missing_role"),
    "hydraulics": (
        "observation_id",
        "linked_record_id",
        "manufacturer_article_no",
        "entity_type",
        "observation_type",
        "source_url",
    ),
    "technical": (
        "observation_id",
        "linked_record_id",
        "manufacturer_article_no",
        "field_name",
        "normalized_value",
        "source_url",
    ),
    "technical_audit": ("record_id", "manufacturer_article_no"),
    "exact_lifecycle": ("manufacturer_article_no", "record_ids", "lifecycle_status"),
    "record_lifecycle": (
        "record_id",
        "manufacturer_article_no",
        "benchmark_entity_type",
        "lifecycle_status",
        "regional_identity_status",
    ),
    "package_contents": (
        "parent_record_id",
        "parent_article_no",
        "component_article_no",
        "component_record_id",
    ),
    "compatibility": (
        "source_component_record_id",
        "source_article_no",
        "target_record_id",
        "target_article_no",
    ),
    "regional_provenance": ("record_id", "manufacturer_article_no", "market", "source_url"),
    "controlled_gaps": ("gap_id", "linked_record_id", "manufacturer_article_no", "gap_domain"),
}


def empty_table_map() -> dict[str, list[pd.DataFrame]]:
    return {key: [] for key in DATASET_SHEETS}


def read_workbook_tables(
    source_name: str,
    source: str | BytesIO,
) -> tuple[dict[str, pd.DataFrame], list[str], dict[str, Any]]:
    """Read one workbook and return normalised logical layers.

    Physical worksheets take precedence. A secondary archive is used only for
    logical layers that are not already present physically, preventing double
    loading in workbooks that expose both representations.
    """

    tables: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    metadata: dict[str, Any] = {
        "source_name": source_name,
        "archive_contract": None,
        "archive_layers_loaded": 0,
        "physical_layers_loaded": 0,
    }

    with pd.ExcelFile(source) as workbook:
        available_sheets = set(workbook.sheet_names)

        for data_key, sheet_name in DATASET_SHEETS.items():
            if sheet_name not in available_sheets:
                continue
            dtype = {column: "string" for column in TEXT_COLUMNS.get(data_key, ())}
            frame = pd.read_excel(workbook, sheet_name=sheet_name, dtype=dtype or None)
            tables[data_key] = _normalise_table(frame, data_key, source_name)
            metadata["physical_layers_loaded"] += 1

        if SECONDARY_ARCHIVE_PAYLOAD in available_sheets:
            try:
                archive_tables, archive_meta = _decode_secondary_archive(
                    workbook, source_name, available_sheets
                )
                metadata.update(archive_meta)
                for data_key, frame in archive_tables.items():
                    if data_key not in tables or tables[data_key].empty:
                        tables[data_key] = frame
                        metadata["archive_layers_loaded"] += 1
            except Exception as error:
                warnings.append(
                    f"{source_name}: secondary archive could not be decoded ({error})."
                )

        if "flat" not in tables:
            warnings.append(f"{source_name}: missing sheet 01_Flat_Input.")
        # Preserve historical core-sheet warnings only when no archive supplies
        # the corresponding layer. Extended v2 layers are optional for legacy v1.
        for data_key in ("bom", "evidence"):
            if data_key not in tables:
                warnings.append(
                    f"{source_name}: missing logical layer {DATASET_SHEETS[data_key]}."
                )

    return tables, warnings, metadata


def _decode_secondary_archive(
    workbook: pd.ExcelFile,
    source_name: str,
    available_sheets: set[str],
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    payload = pd.read_excel(
        workbook,
        sheet_name=SECONDARY_ARCHIVE_PAYLOAD,
        dtype={"chunk_text": "string"},
    )
    required = {"chunk_no", "chunk_text"}
    if not required.issubset(payload.columns):
        raise ValueError("payload is missing chunk_no/chunk_text columns")

    payload = payload.copy()
    payload["chunk_no"] = pd.to_numeric(payload["chunk_no"], errors="coerce")
    payload = payload[payload["chunk_no"].notna()].sort_values("chunk_no", kind="stable")
    encoded = "".join(payload["chunk_text"].fillna("").astype(str).tolist())
    if not encoded:
        raise ValueError("payload contains no archive data")

    compressed = base64.b64decode(encoded, validate=True)
    decoded = bz2.decompress(compressed)
    archive = json.loads(decoded.decode("utf-8"))
    if not isinstance(archive, dict) or not isinstance(archive.get("layers"), dict):
        raise ValueError("archive root does not contain a layers object")

    manifest_counts: dict[str, int] = {}
    if SECONDARY_ARCHIVE_MANIFEST in available_sheets:
        manifest = pd.read_excel(workbook, sheet_name=SECONDARY_ARCHIVE_MANIFEST)
        if {"logical_layer", "row_count"}.issubset(manifest.columns):
            for _, row in manifest.iterrows():
                layer_name = str(row.get("logical_layer") or "").strip()
                row_count = pd.to_numeric(pd.Series([row.get("row_count")]), errors="coerce").iloc[0]
                if layer_name and pd.notna(row_count):
                    manifest_counts[layer_name] = int(row_count)

    tables: dict[str, pd.DataFrame] = {}
    for logical_layer, layer_payload in archive["layers"].items():
        data_key = SHEET_TO_DATA_KEY.get(str(logical_layer))
        if data_key is None or not isinstance(layer_payload, dict):
            continue
        headers = layer_payload.get("schema_headers") or []
        rows = layer_payload.get("rows") or []
        if not isinstance(headers, list) or not isinstance(rows, list):
            raise ValueError(f"{logical_layer}: invalid headers/rows")
        declared_count = layer_payload.get("row_count")
        if declared_count is not None and int(declared_count) != len(rows):
            raise ValueError(
                f"{logical_layer}: declared {declared_count} rows but decoded {len(rows)}"
            )
        manifest_count = manifest_counts.get(str(logical_layer))
        if manifest_count is not None and manifest_count != len(rows):
            raise ValueError(
                f"{logical_layer}: manifest {manifest_count} rows but decoded {len(rows)}"
            )
        frame = pd.DataFrame(rows, columns=headers)
        frame = _normalise_table(frame, data_key, source_name)
        frame["_archive_contract"] = str(archive.get("archive_contract") or "")
        tables[data_key] = frame

    metadata = {
        "archive_contract": str(archive.get("archive_contract") or "") or None,
        "archive_layer_count": len(tables),
        "archive_compressed_bytes": len(compressed),
        "archive_uncompressed_bytes": len(decoded),
    }
    return tables, metadata


def _normalise_table(frame: pd.DataFrame, data_key: str, source_name: str) -> pd.DataFrame:
    normalised = frame.copy()
    for column in TEXT_COLUMNS.get(data_key, ()):
        if column in normalised.columns:
            normalised[column] = normalised[column].astype("string").str.strip()

    # Compatibility aliases keep the existing Streamlit views and audit tools
    # working while accepting the v2 universal schema.
    if data_key == "bom":
        _copy_alias(normalised, "parent_record_id", "parent_system_key")
        _copy_alias(normalised, "requirement_status", "required_level")
        _copy_alias(normalised, "relationship_basis", "compatibility_confidence")
        _copy_alias(normalised, "evidence_excerpt", "source_excerpt")
    elif data_key == "evidence":
        _copy_alias(normalised, "linked_entity_type", "entity_type")
        _copy_alias(normalised, "evidence_excerpt", "source_excerpt")
        _copy_alias(normalised, "raw_value", "extracted_value")
    elif data_key == "prices":
        _copy_alias(normalised, "seller_name", "retailer")
    elif data_key == "technical":
        _copy_alias(normalised, "source_excerpt", "evidence_excerpt")

    normalised["_source_workbook"] = source_name
    return normalised


def _copy_alias(frame: pd.DataFrame, source_column: str, target_column: str) -> None:
    if target_column in frame.columns or source_column not in frame.columns:
        return
    frame[target_column] = frame[source_column]
