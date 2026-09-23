"""Streamlit application for filtering and comparing shower drainage systems."""

from __future__ import annotations

import hmac
import json
import math
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from point_geometry import (
    POINT_DRAIN_NUMERIC_FILTERS,
    POINT_DRAIN_PARAMETER_REGISTRY,
    POINT_DRAIN_SEARCH_FIELDS,
    POINT_DRAIN_TEXT_FILTERS,
)

from drainage_data import (
    MasterData,
    advanced_scoring_audit_tables,
    aggregate_presentation_groups,
    available_columns,
    discover_local_workbooks,
    build_ranking_request,
    execute_ranking_request,
    execute_reference_product_comparison,
    filter_flat_input,
    hierarchy_audit_tables,
    hierarchy_summary,
    length_filter_bounds,
    load_all_workbooks,
    mandatory_requirements_from_filters,
    mandatory_requirements_table,
    numeric_bounds,
    prepare_benchmark_data,
    multi_parameter_score_column,
    multi_parameter_weight_column,
    normalise_ranking_weights,
    ranking_request_tables,
    related_rows,
    score_advanced_product_groups,
    selection_labels,
    string_options,
)


APP_ROOT = Path(__file__).resolve().parent
DATA_DIRECTORY = APP_ROOT / "data"
CONFIG_DIRECTORY = APP_ROOT / "config"
CLASSIFICATION_RULES_PATH = CONFIG_DIRECTORY / "classification_rules.csv"
LENGTH_RULES_PATH = CONFIG_DIRECTORY / "length_rules.csv"
USER_GUIDE_PATH = APP_ROOT / "USER_GUIDE.md"
USER_GUIDE_PDF_PATH = APP_ROOT / "docs" / "Shower_Drainage_Comparator_Quick_Start_Guide_EN.pdf"

CLASSIFICATION_RULE_COLUMNS = {
    "rule_id",
    "priority",
    "enabled",
    "benchmark_entity_type",
    "manufacturer_key",
    "product_category",
    "family_match",
    "family_value",
    "variant_contains",
    "mapped_drain_form",
    "leaderboard_visibility",
}

LENGTH_RULE_COLUMNS = {
    "rule_id",
    "priority",
    "enabled",
    "benchmark_entity_type",
    "manufacturer_key",
    "family_match",
    "family_value",
    "variant_contains",
    "required_drain_form",
    "length_mode",
    "min_rule",
    "max_rule",
    "strict_filter_eligible",
}

DRAIN_TYPE_OPTIONS = {
    "All drain forms": None,
    "Linear drain": "linear",
    "Point drain": "point",
    "Legacy integrated shower surface": "integrated_surface",
}

SOLUTION_TYPE_LABELS = {
    "drainage_system": "Drainage system",
    "integrated_shower_element": "Integrated shower element",
    "integrated_shower_surface": "Integrated shower surface",
    "heat_recovery_shower_system": "Heat-recovery shower system",
    "manual_review": "Manual review",
    "component": "Component",
    "family_metadata": "Family metadata",
}

POINT_ATTRIBUTE_FILTERS = POINT_DRAIN_TEXT_FILTERS
POINT_NUMERIC_FILTERS = POINT_DRAIN_NUMERIC_FILTERS

POINT_GEOMETRY_SUMMARY_COLUMNS = [
    "point_top_shape",
    "point_top_size",
    "point_grate_size",
    "point_cover_size",
    "point_body_size",
    "drain_position",
]

POINT_GEOMETRY_SEARCH_COLUMNS = [
    *POINT_DRAIN_SEARCH_FIELDS,
    "point_top_size",
    "point_grate_size",
    "point_cover_size",
    "point_body_size",
]


ATTRIBUTE_FILTERS = {
    "material_v4a": "V4A material",
    "din_en_1253_status": "DIN EN 1253",
    "din_en_18534_status": "DIN EN 18534",
    "sealing_fleece_preassembled": "Preassembled sealing fleece",
    "outlet_direction_selectable": "Selectable outlet direction",
}

BENCHMARK_MODES = [
    "Single-parameter ranking",
    "Multi-parameter ranking",
    "Reference-product comparison",
    "Advanced weighted scoring",
]

ADVANCED_MISSING_DATA_OPTIONS = {
    "Require complete data": "require_complete",
    "Allow incomplete data with zero score": "allow_incomplete_zero_score",
    "Allow incomplete data with proportional penalty":
        "allow_incomplete_proportional_penalty",
}

SINGLE_PARAMETER_OPTIONS = {
    "Flow rate at 20 mm head — higher is better": {
        "column": "flow_rate_20mm_lps",
        "higher_is_better": True,
        "value_label": "Flow rate at 20 mm [l/s]",
    },
    "Primary declared flow rate — higher is better": {
        "column": "flow_rate_primary_lps",
        "higher_is_better": True,
        "value_label": "Primary declared flow rate [l/s]",
    },
    "Minimum installation height — lower is better": {
        "column": "height_adj_min_mm",
        "higher_is_better": False,
        "value_label": "Minimum installation height [mm]",
    },
}

MULTI_PARAMETER_DEFAULTS = [
    "Flow rate at 20 mm head — higher is better",
    "Minimum installation height — lower is better",
]

# The advanced scorer can contain thousands of wide database records. Sending
# every row and every source column to the browser in one Streamlit message can
# overload the WebSocket and trigger a misleading SessionInfo popup. The full
# result remains available for export; the interactive table is intentionally
# limited to a compact, configurable leaderboard view.
ADVANCED_DISPLAY_LIMIT_OPTIONS = [25, 50, 100, 250, 500]

ADVANCED_LEADERBOARD_COLUMNS = [
    "Rank",
    "Final_Score_%",
    "Data_Completeness_%",
    "Weighted_Data_Completeness_%",
    "Available_Criteria",
    "Required_Criteria",
    "Missing_Ranking_Fields",
    "Score_Before_Completeness_Penalty_%",
    "Completeness_Penalty_Factor",
    "manufacturer_name",
    "product_family_name",
    "model_name",
    "drain_type_label",
    "mapped_solution_type",
    "drain_element_length_mm",
    "nominal_length_mm",
    *POINT_GEOMETRY_SUMMARY_COLUMNS,
    "point_grate_length_mm",
    "point_grate_width_mm",
    "point_grate_diameter_mm",
    "outlet_dn_default",
    "outlet_orientation_default",
    "flow_rate_primary_lps",
    "height_adj_min_mm",
    "material_v4a",
    "sales_price_value",
    "sales_price_currency",
    "sales_price_group_basis",
    "colours_count",
    "colours_count_source",
    "Score_Flow_Rate_%",
    "Score_Installation_Height_%",
    "Score_V4A_%",
    "Score_Sales_Price_%",
    "Score_Colours_%",
    "group_member_count",
    "finish_variant_count",
    "article_variant_count",
    "available_finishes",
    "product_link",
]


st.set_page_config(page_title="Shower Drainage Comparator", layout="wide")


def _read_app_password() -> str | None:
    """Return the configured shared password without exposing it to the UI."""

    try:
        value = st.secrets["app_password"]
    except (KeyError, FileNotFoundError):
        return None

    password = str(value).strip()
    return password or None


def require_password() -> None:
    """Stop the app before data loading until the shared password is verified."""

    if st.session_state.get("authenticated", False):
        return

    st.title("Shower Drainage System Comparator")
    st.caption("This application is restricted to authorised users.")

    expected_password = _read_app_password()
    if expected_password is None:
        st.error("Application access is not configured.")
        st.info(
            "Add a top-level `app_password` value in Streamlit Cloud under "
            "Manage app → Settings → Secrets, then reboot the app."
        )
        st.stop()

    with st.form("password_gate", clear_on_submit=False):
        entered_password = st.text_input(
            "Access password",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        if hmac.compare_digest(entered_password, expected_password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


def render_logout_control() -> None:
    """Render a session logout action after successful authentication."""

    with st.sidebar:
        st.caption("Access: authenticated")
        if st.button("Log out", key="logout_button", use_container_width=True):
            st.session_state.pop("authenticated", None)
            st.rerun()


@st.cache_data(show_spinner="Loading and consolidating Excel workbooks…")
def load_master_data(
    local_workbooks: tuple[tuple[str, int, int], ...],
    uploaded_workbooks: tuple[tuple[str, bytes], ...],
    classification_rules_signature: tuple[str, int, int],
    length_rules_signature: tuple[str, int, int],
) -> MasterData:
    """Cache workbook loading and application of versioned configuration rules."""

    master = load_all_workbooks(local_workbooks, uploaded_workbooks)
    classification_rules = pd.read_csv(
        classification_rules_signature[0], dtype="string", keep_default_na=False
    )
    length_rules = pd.read_csv(
        length_rules_signature[0], dtype="string", keep_default_na=False
    )
    validate_rule_table(
        classification_rules,
        "classification_rules.csv",
        CLASSIFICATION_RULE_COLUMNS,
    )
    validate_rule_table(length_rules, "length_rules.csv", LENGTH_RULE_COLUMNS)
    if not master.flat.empty:
        master.flat = prepare_benchmark_data(
            master.flat,
            classification_rules,
            length_rules,
        )
    return master


@st.cache_data(show_spinner=False)
def dataframe_to_excel(frame: pd.DataFrame, sheet_name: str = "Result") -> bytes:
    """Convert the current result to a single Excel workbook."""

    output = BytesIO()
    safe_sheet_name = sheet_name[:31] or "Result"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=safe_sheet_name, index=False)
    return output.getvalue()


def dataframes_to_excel(tables: dict[str, pd.DataFrame]) -> bytes:
    """Create an audit-ready workbook with one sheet per supplied table."""

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        used_names: set[str] = set()
        for requested_name, frame in tables.items():
            base_name = (requested_name or "Sheet")[:31]
            sheet_name = base_name
            suffix = 1
            while sheet_name in used_names:
                suffix += 1
                sheet_name = f"{base_name[:27]}_{suffix}"
            used_names.add(sheet_name)
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


@st.cache_data(show_spinner=False)
def hierarchy_audit_workbook(frame: pd.DataFrame) -> bytes:
    """Build the database-migration workbook for stable hierarchy keys."""

    return dataframes_to_excel(hierarchy_audit_tables(frame))


@st.cache_data(show_spinner=False)
def advanced_scoring_workbook(
    scored_groups: pd.DataFrame,
    members: pd.DataFrame,
    weights_signature: tuple[tuple[str, float], ...],
    missing_data_policy: str,
    filter_payload_json: str,
) -> bytes:
    """Build a grouped scoring workbook with exact variants and hard filters."""

    tables = advanced_scoring_audit_tables(
        scored_groups,
        members,
        dict(weights_signature),
        missing_data_policy=missing_data_policy,
    )
    filter_payload = json.loads(filter_payload_json)
    requirements = mandatory_requirements_from_filters(filter_payload)
    tables["Mandatory_Requirements"] = mandatory_requirements_table(requirements)
    return dataframes_to_excel(tables)


def render_hierarchy_status(frame: pd.DataFrame) -> None:
    """Show product-hierarchy coverage and expose a migration-ready export."""

    summary = hierarchy_summary(frame)
    with st.expander("Product hierarchy and grouping status", expanded=False):
        metric_columns = st.columns(4)
        metric_columns[0].metric("Technical models", f"{summary['technical_models']:,}".replace(",", " "))
        metric_columns[1].metric("Technical variants", f"{summary['technical_variants']:,}".replace(",", " "))
        metric_columns[2].metric("Presentation groups", f"{summary['presentation_groups']:,}".replace(",", " "))
        metric_columns[3].metric("Hidden article/finish variants", f"{summary['hidden_variants']:,}".replace(",", " "))

        st.caption(
            (
                f"Hierarchy key source: {summary['explicit_records']:,} explicit, "
                f"{summary['mixed_records']:,} mixed, and "
                f"{summary['derived_records']:,} deterministically derived records. "
                "Persisted database keys are preferred automatically when present."
            ).replace(",", " ")
        )
        if summary["derived_records"]:
            st.info(
                "The current Excel workbooks do not yet persist all hierarchy keys. "
                "The application uses deterministic fallback keys and the export below "
                "can be reviewed before adding the fields to PostgreSQL or the master workbook."
            )

        workbook_state_key = "product_hierarchy_migration_workbook"
        if st.button(
            "Prepare product hierarchy migration workbook",
            key="prepare_product_hierarchy_migration",
            help=(
                "Builds a record-level key map, one row per presentation group, "
                "and validation checks. Generation runs only when requested."
            ),
        ):
            with st.spinner("Preparing product hierarchy migration workbook…"):
                st.session_state[workbook_state_key] = hierarchy_audit_workbook(frame)

        if workbook_state_key in st.session_state:
            st.download_button(
                "Download product hierarchy migration workbook (.xlsx)",
                data=st.session_state[workbook_state_key],
                file_name="shower_drainage_product_hierarchy_migration.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


def ranking_request_json(request: dict[str, object]) -> bytes:
    """Serialise the deterministic request for future API/LLM reuse."""

    return json.dumps(request, indent=2, ensure_ascii=False).encode("utf-8")


def ranking_audit_tables(
    *,
    request: dict[str, object],
    ranking: pd.DataFrame,
    ranked_all: pd.DataFrame,
    grouped: pd.DataFrame,
    members: pd.DataFrame,
    source_record_count: int,
    source_workbook_count: int,
) -> dict[str, pd.DataFrame]:
    """Build ranking, criteria, filter and run-metadata sheets."""

    criteria, filters, request_settings = ranking_request_tables(request)
    ranked_group_keys = set(
        ranking.get("presentation_group_key", pd.Series(dtype="string"))
        .astype("string")
        .dropna()
        .tolist()
    )
    ranked_variants = members[
        members.get(
            "presentation_group_key", pd.Series(index=members.index, dtype="string")
        )
        .astype("string")
        .isin(ranked_group_keys)
    ].copy()
    metadata = pd.DataFrame(
        [
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source_workbooks": source_workbook_count,
                "mandatory_filtered_source_records": source_record_count,
                "technical_product_groups": len(grouped),
                "eligible_ranked_products": len(ranked_all),
                "exported_top_products": len(ranking),
                "excluded_for_missing_ranking_data": max(len(grouped) - len(ranked_all), 0),
            }
        ]
    )
    return {
        "Ranking": ranking,
        "Ranking_Criteria": criteria,
        "Mandatory_Filters": filters,
        "Request_Settings": request_settings,
        "Run_Metadata": metadata,
        "Ranked_Variants": ranked_variants,
    }


def render_ranking_audit_downloads(
    *,
    request: dict[str, object],
    ranking: pd.DataFrame,
    ranked_all: pd.DataFrame,
    grouped: pd.DataFrame,
    members: pd.DataFrame,
    source_record_count: int,
    source_workbook_count: int,
    filename_prefix: str,
) -> None:
    """Expose auditable Excel and JSON outputs for a ranking run."""

    audit_tables = ranking_audit_tables(
        request=request,
        ranking=ranking,
        ranked_all=ranked_all,
        grouped=grouped,
        members=members,
        source_record_count=source_record_count,
        source_workbook_count=source_workbook_count,
    )
    excel_data = dataframes_to_excel(audit_tables)
    json_data = ranking_request_json(request)
    excel_column, json_column = st.columns(2)
    with excel_column:
        st.download_button(
            "Download ranking audit workbook (.xlsx)",
            data=excel_data,
            file_name=f"{filename_prefix}_audit.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with json_column:
        st.download_button(
            "Download ranking request (.json)",
            data=json_data,
            file_name=f"{filename_prefix}_request.json",
            mime="application/json",
        )

    with st.expander("Structured ranking request (API / LLM-ready)"):
        st.code(json.dumps(request, indent=2, ensure_ascii=False), language="json")
        st.caption(
            "The request describes mandatory filters, ranking criteria, directions, "
            "normalised weights, missing-data policy and Top-N. The ranking itself "
            "remains deterministic in the data layer."
        )


@st.cache_data(show_spinner=False)
def load_text_file(path: str, modified_ns: int, size: int) -> str:
    """Read a local text file through a cache signature."""

    del modified_ns, size
    return Path(path).read_text(encoding="utf-8")


def render_help_and_user_guide() -> None:
    """Expose concise first-use guidance and downloadable documentation."""

    with st.sidebar.expander("Help and User Guide", expanded=False):
        st.markdown(
            """
**Quick workflow**

1. Set **Mandatory requirements** to define eligible products.
2. Choose a **Result method**.
3. Review the ranked technical products and open product details.
4. Download an audit workbook when the result needs to be shared.

**Reference-product comparison** uses the selected product only to define a
comparable set. The benchmark score is then calculated independently across
that set, and the reference product can rank below a competitor.
"""
        )
        guide_signature = file_signature(USER_GUIDE_PATH)
        if guide_signature is not None:
            guide_text = load_text_file(*guide_signature)
            st.download_button(
                "Download full User Guide (.md)",
                data=guide_text.encode("utf-8"),
                file_name="Shower_Drainage_Comparator_User_Guide_EN.md",
                mime="text/markdown",
                key="download_user_guide_markdown",
            )
            show_full_guide = st.checkbox(
                "Show full guide in the sidebar",
                value=False,
                key="show_full_user_guide",
            )
            if show_full_guide:
                st.markdown(guide_text)
        else:
            st.caption("USER_GUIDE.md is not present in the application repository.")

        if USER_GUIDE_PDF_PATH.exists():
            st.download_button(
                "Download printable User Guide (.pdf)",
                data=USER_GUIDE_PDF_PATH.read_bytes(),
                file_name=USER_GUIDE_PDF_PATH.name,
                mime="application/pdf",
                key="download_user_guide_pdf",
            )


def is_full_range(
    selected_range: tuple[float, float], bounds: tuple[float, float] | None
) -> bool:
    if bounds is None:
        return True
    return selected_range[0] == bounds[0] and selected_range[1] == bounds[1]


def file_signature(path: Path) -> tuple[str, int, int] | None:
    """Return a configuration file signature for reliable cache invalidation."""

    if not path.is_file():
        return None
    stats = path.stat()
    return str(path), stats.st_mtime_ns, stats.st_size


def validate_rule_table(
    frame: pd.DataFrame, filename: str, required_columns: set[str]
) -> None:
    """Stop the application before incomplete configuration can distort the result."""

    missing_columns = sorted(required_columns.difference(frame.columns))
    if missing_columns:
        raise ValueError(f"{filename}: missing columns {', '.join(missing_columns)}")
    if frame.empty:
        raise ValueError(f"{filename}: the file contains no rules")
    if frame["rule_id"].duplicated().any():
        raise ValueError(f"{filename}: rule_id values must be unique")


def numeric_range_widget(
    label: str, frame: pd.DataFrame, column: str, *, key: str
) -> tuple[float, float] | None:
    bounds = numeric_bounds(frame, column)
    if bounds is None:
        st.sidebar.caption(f"{label}: no numeric values are available.")
        return None

    minimum, maximum = bounds
    if minimum == maximum:
        st.sidebar.caption(f"{label}: the only available value is {minimum:g}.")
        return bounds

    step = max((maximum - minimum) / 200, 0.01)
    return st.sidebar.slider(
        label,
        min_value=float(minimum),
        max_value=float(maximum),
        value=(float(minimum), float(maximum)),
        step=float(step),
        key=key,
    )


def length_range_widget(
    frame: pd.DataFrame,
) -> tuple[tuple[int, int] | None, tuple[float, float] | None]:
    """Render the length slider using verified installable ranges only."""

    bounds = length_filter_bounds(frame)
    if bounds is None:
        st.sidebar.caption("Length: no verified length range is available for the current selection.")
        return None, None

    minimum = math.floor(bounds[0])
    maximum = math.ceil(bounds[1])
    if minimum == maximum:
        st.sidebar.caption(f"Drain element length: the only available value is {minimum} mm.")
        return (minimum, maximum), bounds

    selection = st.sidebar.slider(
        "Drain element length [mm]",
        min_value=minimum,
        max_value=maximum,
        value=(minimum, maximum),
        step=1,
        key="drain_length_range",
        help=(
            "A product passes when its verified installable range overlaps "
            "the selected interval."
        ),
    )
    return selection, bounds


def active_text_filter(
    label: str, options: list[str], *, key: str
) -> list[str] | None:
    if not options:
        st.sidebar.caption(f"{label}: column is not available.")
        return None
    selected = st.sidebar.multiselect(label, options=options, default=options, key=key)
    return None if set(selected) == set(options) else selected


def display_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """Replace missing values with N/A for display.

    Calculations and export continue to use the original data frame and its
    numeric dtypes; this conversion is used only in the user interface.
    """

    display = frame.copy()
    for column in display.columns:
        if not display[column].isna().any():
            continue
        if pd.api.types.is_numeric_dtype(display[column]):
            display[column] = display[column].map(
                lambda value: "N/A" if pd.isna(value) else f"{value:g}"
            )
        else:
            display[column] = display[column].astype("string").fillna("N/A")
    return display


def ranking_group_labels(frame: pd.DataFrame) -> dict[str, str]:
    """Create readable labels for selecting a ranked technical product group."""

    if "presentation_group_key" not in frame.columns:
        return {}

    labels: dict[str, str] = {}
    for position, (_, row) in enumerate(frame.iterrows(), start=1):
        group_key = row.get("presentation_group_key")
        if pd.isna(group_key) or not str(group_key).strip():
            continue
        rank = row.get("Rank", position)
        if pd.isna(rank):
            rank_label = "Unranked"
        else:
            try:
                rank_label = f"#{int(rank)}"
            except (TypeError, ValueError):
                rank_label = f"#{rank}"
        manufacturer = _display_text(row.get("manufacturer_name"), "Unknown manufacturer")
        model = _display_text(row.get("model_name"), _display_text(row.get("product_family_name"), "Unknown model"))
        drain_form = _display_text(row.get("mapped_drain_form"), "").casefold()
        length = row.get("drain_element_length_mm")
        if pd.isna(length):
            length = row.get("nominal_length_mm")
        outlet = _display_text(row.get("outlet_dn_default"), "")

        details: list[str] = []
        if drain_form == "point":
            point_size = _display_text(
                row.get("point_grate_size"),
                _display_text(row.get("point_top_size"), ""),
            )
            if point_size:
                details.append(point_size)
        elif pd.notna(length):
            try:
                details.append(f"{float(length):g} mm")
            except (TypeError, ValueError):
                details.append(str(length))
        if outlet:
            details.append(outlet)
        suffix = f" — {' / '.join(details)}" if details else ""
        label = f"{rank_label} {manufacturer} — {model}{suffix}"
        if label in labels:
            label = f"{label} ({position})"
        labels[label] = str(group_key)
    return labels


def _display_text(value: object, fallback: str = "N/A") -> str:
    if pd.isna(value):
        return fallback
    text = str(value).strip()
    return text or fallback


def _token_label(value: object) -> str:
    """Human-readable label for schema tokens used by v2 filters."""

    text = _display_text(value, "Unknown")
    if text in SOLUTION_TYPE_LABELS:
        return SOLUTION_TYPE_LABELS[text]
    return text.replace("_", " ").strip().title()


def active_token_filter(
    label: str, options: list[str], *, key: str
) -> list[str] | None:
    """Multiselect that keeps raw schema tokens but renders readable labels."""

    if not options:
        st.sidebar.caption(f"{label}: column is not available.")
        return None
    selected = st.sidebar.multiselect(
        label,
        options=options,
        default=options,
        key=key,
        format_func=_token_label,
    )
    return None if set(selected) == set(options) else selected


def _record_overview_table(row: pd.Series) -> pd.DataFrame:
    """Build a compact category-aware parameter table for one exact record."""

    common = [
        ("Manufacturer", "manufacturer_name"),
        ("Product family", "product_family_name"),
        ("Model", "model_name"),
        ("Variant", "variant_name"),
        ("Article number", "manufacturer_article_no"),
        ("Drain form", "drain_type_label"),
        ("Solution type", "mapped_solution_type"),
        ("Product category", "product_category"),
        ("Primary flow [l/s]", "flow_rate_primary_lps"),
        ("Flow @10 mm [l/s]", "flow_rate_10mm_lps"),
        ("Flow @20 mm [l/s]", "flow_rate_20mm_lps"),
        ("Minimum installation height [mm]", "height_adj_min_mm"),
        ("Maximum installation height [mm]", "height_adj_max_mm"),
        ("Product height [mm]", "height_mm"),
        ("Water seal [mm]", "water_seal_mm"),
        ("Outlet DN", "outlet_dn_default"),
        ("Outlet orientation", "outlet_orientation_default"),
        ("Selectable outlet direction", "outlet_direction_selectable"),
        ("Material", "material_raw"),
        ("V2A", "material_v2a"),
        ("V4A", "material_v4a"),
        ("DIN EN 1253", "din_en_1253_status"),
        ("DIN 18534", "din_en_18534_status"),
        ("Sealing interface", "sealing_interface_type"),
        ("Preassembled sealing fleece", "sealing_fleece_preassembled"),
        ("Lifecycle", "lifecycle_status_v2"),
        ("Technical completeness", "technical_completeness_flag"),
    ]
    drain_form = _display_text(row.get("mapped_drain_form"), "unknown").casefold()
    if drain_form == "point":
        category_specific = [
            ("Nominal top size", "point_top_size"),
            ("Grate size", "point_grate_size"),
            ("Cover size", "point_cover_size"),
            ("Body size", "point_body_size"),
        ]
        category_specific.extend(
            (parameter.display_label, parameter.field)
            for parameter in POINT_DRAIN_PARAMETER_REGISTRY
            if parameter.show_in_detail
        )
        # Generic source dimensions are retained as declared dimensions only.
        # They are never relabelled as visible grate/top geometry.
        category_specific.extend(
            [
                ("Declared overall / legacy length [mm]", "nominal_length_mm"),
                ("Declared overall / legacy width [mm]", "width_mm"),
            ]
        )
    elif drain_form == "linear":
        category_specific = [
            ("Drain element length [mm]", "drain_element_length_mm"),
            ("Length basis", "drain_element_length_basis"),
            ("Channel length [mm]", "channel_length_mm"),
            ("Channel position", "channel_position"),
            ("Maximum channel shortening [mm]", "max_shortening_inside_channel_mm"),
            ("Overall product length [mm]", "nominal_length_mm"),
            ("Overall product width [mm]", "width_mm"),
        ]
    else:
        category_specific = [
            ("Overall length [mm]", "nominal_length_mm"),
            ("Overall width [mm]", "width_mm"),
        ]

    rows: list[dict[str, object]] = []
    for label, column in common + category_specific:
        if column not in row.index:
            continue
        value = row.get(column)
        if value is None or pd.isna(value) or str(value).strip() == "":
            continue
        display_value = _token_label(value) if column == "mapped_solution_type" else value
        rows.append({"Parameter": label, "Value": display_value})
    return pd.DataFrame(rows)


def render_v2_data_status(master: MasterData) -> None:
    """Expose which canonical v2 layers were actually loaded."""

    with st.expander("Loaded data architecture", expanded=False):
        system_count = 0
        component_count = 0
        if "benchmark_entity_type" in master.flat.columns:
            entity = master.flat["benchmark_entity_type"].astype("string").str.casefold()
            system_count = int(entity.eq("system").sum())
            component_count = int(entity.eq("component").sum())
        metrics = st.columns(4)
        metrics[0].metric("Records", f"{len(master.flat):,}".replace(",", " "))
        metrics[1].metric("Systems", f"{system_count:,}".replace(",", " "))
        metrics[2].metric("Components", f"{component_count:,}".replace(",", " "))
        metrics[3].metric("Source workbooks", master.source_count)

        layer_rows = []
        for label, attribute in [
            ("BOM", "bom"),
            ("Evidence", "evidence"),
            ("Prices", "prices"),
            ("Hydraulic observations", "hydraulics"),
            ("Technical observations", "technical"),
            ("Technical audit", "technical_audit"),
            ("Record lifecycle", "record_lifecycle"),
            ("Package contents", "package_contents"),
            ("Compatibility graph", "compatibility"),
            ("Regional provenance", "regional_provenance"),
            ("Controlled gaps", "controlled_gaps"),
        ]:
            layer_rows.append({"Logical layer": label, "Rows": len(getattr(master, attribute))})
        st.dataframe(pd.DataFrame(layer_rows), use_container_width=True, hide_index=True)

        if not master.workbook_metadata.empty:
            metadata_columns = available_columns(
                master.workbook_metadata,
                [
                    "source_name",
                    "physical_layers_loaded",
                    "archive_layers_loaded",
                    "archive_contract",
                ],
            )
            if metadata_columns:
                st.caption("Workbook loading mode")
                st.dataframe(
                    display_dataframe(master.workbook_metadata[metadata_columns]),
                    use_container_width=True,
                    hide_index=True,
                )


def render_record_details(
    master: MasterData,
    selected_system: pd.DataFrame,
    selected_record_id: str,
    *,
    heading: str = "Selected system",
) -> None:
    """Render one exact record with category-aware v2 drill-down layers."""

    st.markdown(f"#### {heading}")
    if selected_system.empty:
        st.info("The selected record is not available.")
        return

    row = selected_system.iloc[0]
    overview = _record_overview_table(row)
    if not overview.empty:
        st.dataframe(overview, use_container_width=True, hide_index=True)

    product_url = row.get("product_url")
    if pd.notna(product_url) and str(product_url).strip():
        st.link_button("Open manufacturer product page", str(product_url).strip())

    selected_system_key = selected_record_id
    system_key_value = row.get("system_key")
    if pd.notna(system_key_value) and str(system_key_value).strip():
        selected_system_key = str(system_key_value).strip()

    bom_rows = related_rows(master.bom, "parent_system_key", selected_system_key)
    if bom_rows.empty and selected_system_key != selected_record_id:
        bom_rows = related_rows(master.bom, "parent_system_key", selected_record_id)
    technical_rows = related_rows(master.technical, "linked_record_id", selected_record_id)
    hydraulic_rows = related_rows(master.hydraulics, "linked_record_id", selected_record_id)
    price_rows = related_rows(master.prices, "linked_record_id", selected_record_id)
    evidence_rows = related_rows(master.evidence, "linked_record_id", selected_record_id)
    package_rows = related_rows(master.package_contents, "parent_record_id", selected_record_id)
    lifecycle_rows = related_rows(master.record_lifecycle, "record_id", selected_record_id)
    audit_rows = related_rows(master.technical_audit, "record_id", selected_record_id)
    gap_rows = related_rows(master.controlled_gaps, "linked_record_id", selected_record_id)
    if selected_system_key != selected_record_id:
        system_evidence_rows = related_rows(master.evidence, "linked_record_id", selected_system_key)
        evidence_rows = pd.concat(
            [evidence_rows, system_evidence_rows], ignore_index=True, sort=False
        ).drop_duplicates()

    tabs = st.tabs([
        "BOM / package",
        "Technical",
        "Hydraulics",
        "Prices",
        "Evidence",
        "Lifecycle / gaps",
        "Raw record",
    ])

    with tabs[0]:
        bom_columns = available_columns(
            bom_rows,
            [
                "component_article_no",
                "component_name",
                "component_role",
                "required_level",
                "quantity",
                "compatibility_confidence",
                "relation_class",
                "compatibility_status",
            ],
        )
        if bom_rows.empty:
            st.info("No BOM components were found for the selected system.")
        else:
            st.dataframe(display_dataframe(bom_rows[bom_columns]), use_container_width=True, hide_index=True)
        if not package_rows.empty:
            st.caption("Package contents")
            package_columns = available_columns(
                package_rows,
                [
                    "content_name",
                    "quantity_raw",
                    "relation_semantic",
                    "component_article_no",
                    "component_record_id",
                    "exact_component_mapping_status",
                    "source_url",
                ],
            )
            st.dataframe(
                display_dataframe(package_rows[package_columns]),
                use_container_width=True,
                hide_index=True,
                column_config={"source_url": st.column_config.LinkColumn("Source", display_text="Open")},
            )

    with tabs[1]:
        technical_columns = available_columns(
            technical_rows,
            [
                "field_name",
                "normalized_value",
                "unit",
                "raw_value",
                "source_basis",
                "evidence_quality",
                "source_url",
                "source_excerpt",
            ],
        )
        if technical_rows.empty:
            st.info("No v2 technical observations were found for the selected record.")
        else:
            st.dataframe(
                display_dataframe(technical_rows[technical_columns]),
                use_container_width=True,
                hide_index=True,
                column_config={"source_url": st.column_config.LinkColumn("Source", display_text="Open")},
            )

    with tabs[2]:
        hydraulic_columns = available_columns(
            hydraulic_rows,
            [
                "observation_type",
                "flow_lps",
                "head_mm",
                "water_seal_mm",
                "provenance_type",
                "basis",
                "source_url",
                "source_excerpt",
            ],
        )
        if hydraulic_rows.empty:
            st.info("No v2 hydraulic observations were found for the selected record.")
        else:
            st.dataframe(
                display_dataframe(hydraulic_rows[hydraulic_columns]),
                use_container_width=True,
                hide_index=True,
                column_config={"source_url": st.column_config.LinkColumn("Source", display_text="Open")},
            )

    with tabs[3]:
        price_columns = available_columns(
            price_rows,
            [
                "seller_name",
                "price_value",
                "currency",
                "price_type",
                "tax_status",
                "shipping_status",
                "market_region",
                "observed_at",
                "availability_status",
                "source_url",
            ],
        )
        if price_rows.empty:
            st.info("No exact price observations were found for the selected record.")
        else:
            st.dataframe(
                display_dataframe(price_rows[price_columns]),
                use_container_width=True,
                hide_index=True,
                column_config={"source_url": st.column_config.LinkColumn("Source", display_text="Open")},
            )

    with tabs[4]:
        evidence_columns = available_columns(
            evidence_rows,
            [
                "field_name",
                "normalized_value",
                "unit",
                "source_url",
                "source_excerpt",
                "evidence_quality",
            ],
        )
        if evidence_rows.empty:
            st.info("No evidence was found for the selected system.")
        else:
            st.dataframe(
                display_dataframe(evidence_rows[evidence_columns]),
                use_container_width=True,
                hide_index=True,
                column_config={"source_url": st.column_config.LinkColumn("Source", display_text="Open")},
            )

    with tabs[5]:
        if not lifecycle_rows.empty:
            st.caption("Record lifecycle")
            st.dataframe(display_dataframe(lifecycle_rows), use_container_width=True, hide_index=True)
        if not audit_rows.empty:
            st.caption("System technical audit")
            st.dataframe(display_dataframe(audit_rows), use_container_width=True, hide_index=True)
        if not gap_rows.empty:
            st.caption("Controlled gaps")
            gap_columns = available_columns(
                gap_rows, ["gap_domain", "gap_status", "blocking", "source_url", "notes"]
            )
            st.dataframe(
                display_dataframe(gap_rows[gap_columns]),
                use_container_width=True,
                hide_index=True,
                column_config={"source_url": st.column_config.LinkColumn("Source", display_text="Open")},
            )
        if lifecycle_rows.empty and audit_rows.empty and gap_rows.empty:
            st.info("No v2 lifecycle, audit or controlled-gap rows were found for this record.")

    with tabs[6]:
        st.dataframe(display_dataframe(selected_system), use_container_width=True, hide_index=True)



def render_ranked_group_details(
    master: MasterData,
    ranked: pd.DataFrame,
    grouped_members: pd.DataFrame,
    *,
    key_prefix: str,
    score_columns: tuple[str, ...] = (),
    score_column_labels: dict[str, str] | None = None,
    overall_score_column: str = "Ranking_Score_%",
    overall_score_label: str = "Combined score",
) -> None:
    """Render one grouped technical product and its hidden exact variants."""

    st.divider()
    st.subheader("Ranked product details")
    group_labels = ranking_group_labels(ranked)
    if not group_labels:
        st.info("No ranked product group is available for detail display.")
        return

    selected_group_label = st.selectbox(
        "Select a ranked technical product",
        options=list(group_labels),
        key=f"{key_prefix}_group",
    )
    selected_group_key = group_labels[selected_group_label]
    selected_group = ranked[
        ranked["presentation_group_key"].astype("string").eq(selected_group_key)
    ].iloc[[0]]

    summary_columns = available_columns(
        selected_group,
        [
            "Rank",
            "manufacturer_name",
            "product_family_name",
            "model_name",
            "technical_model_key",
            "technical_variant_key",
            "presentation_group_key",
            "hierarchy_key_source",
            "drain_type_label",
            "mapped_solution_type",
            "drain_element_length_mm",
            "nominal_length_mm",
            *POINT_GEOMETRY_SUMMARY_COLUMNS,
            "flow_rate_20mm_lps",
            "flow_rate_primary_lps",
            "flow_rate_primary_head_mm",
            "height_adj_min_mm",
            "height_adj_max_mm",
            "outlet_dn_default",
            "material_v4a",
            "sales_price_value",
            "sales_price_currency",
            "sales_price_group_basis",
            "colours_count",
            "colours_count_source",
            *score_columns,
            overall_score_column,
            "finish_variant_count",
            "article_variant_count",
            "available_finishes",
            "product_link",
        ],
    )
    summary_config = {
        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
        overall_score_column: st.column_config.NumberColumn(
            overall_score_label, format="%.1f %%"
        ),
        "sales_price_value": st.column_config.NumberColumn(
            "Grouped price value", format="%.2f"
        ),
        "colours_count": st.column_config.NumberColumn(
            "Colour/finish options", format="%.0f"
        ),
        "product_link": st.column_config.LinkColumn(
            "Product link", display_text="Open"
        ),
    }
    for column in score_columns:
        display_label = (score_column_labels or {}).get(
            column,
            column.replace("Score_", "").replace("_%", " score").replace("_", " ").title(),
        )
        summary_config[column] = st.column_config.NumberColumn(
            display_label,
            format="%.1f %%",
        )

    st.markdown("#### Technical product group")
    st.dataframe(
        selected_group[summary_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            column: config
            for column, config in summary_config.items()
            if column in summary_columns
        },
    )

    variants = related_rows(
        grouped_members, "presentation_group_key", selected_group_key
    )
    variant_columns = available_columns(
        variants,
        [
            "record_id",
            "technical_model_key",
            "technical_variant_key",
            "presentation_group_key",
            "hierarchy_key_source",
            "manufacturer_article_no",
            "variant_name",
            "finish_name",
            "drain_type_label",
            "mapped_solution_type",
            "drain_element_length_mm",
            "length_mm",
            *POINT_GEOMETRY_SUMMARY_COLUMNS,
            "flow_rate_20mm_lps",
            "flow_rate_primary_lps",
            "height_adj_min_mm",
            "outlet_dn_default",
            "product_url",
            "evidence_url",
        ],
    )
    st.markdown(f"#### Hidden article and finish variants ({len(variants)})")
    if variants.empty or not variant_columns:
        st.info("No exact article/configuration rows are available for this group.")
        return
    st.dataframe(
        variants[variant_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "product_url": st.column_config.LinkColumn(
                "Product", display_text="Open"
            ),
            "evidence_url": st.column_config.LinkColumn(
                "Technical source", display_text="Open"
            ),
        },
    )

    variant_labels = selection_labels(variants)
    if not variant_labels:
        return
    selected_variant_label = st.selectbox(
        "Select an exact article/configuration for BOM and evidence",
        options=list(variant_labels),
        key=f"{key_prefix}_variant",
    )
    selected_record_id = variant_labels[selected_variant_label]
    selected_variant = variants[
        variants["record_id"].astype("string").str.strip().eq(selected_record_id)
    ].iloc[[0]]
    render_record_details(
        master,
        selected_variant,
        selected_record_id,
        heading="Selected article/configuration",
    )

def render_advanced_details(master: MasterData, scored: pd.DataFrame) -> None:
    st.divider()
    st.subheader("System details")
    labels = selection_labels(scored)
    if not labels:
        st.info("The `record_id` column is required to display system details.")
        return

    selected_label = st.selectbox("Select a system", options=list(labels), key="advanced_system")
    selected_record_id = labels[selected_label]
    selected_system = scored[
        scored["record_id"].astype("string").str.strip().eq(selected_record_id)
    ].iloc[[0]]
    render_record_details(master, selected_system, selected_record_id)


def render_single_parameter_ranking(
    master: MasterData,
    filtered: pd.DataFrame,
    *,
    criterion_label: str,
    top_n: int,
    filter_payload: dict[str, object],
    source_workbook_count: int,
) -> None:
    """Render a top-N ranking with finish/article variants collapsed."""

    criterion = SINGLE_PARAMETER_OPTIONS[criterion_label]
    criterion_column = str(criterion["column"])
    request = build_ranking_request(
        mode="single_parameter",
        criteria={criterion_column: bool(criterion["higher_is_better"])},
        weights={criterion_column: 1.0},
        criterion_labels={criterion_column: criterion_label.split(" —", 1)[0]},
        top_n=top_n,
        filters=filter_payload,
    )
    execution = execute_ranking_request(filtered, request)
    grouped = execution.grouped
    grouped_members = execution.members
    ranked_all = execution.ranked_all
    if ranked_all.empty:
        st.warning(
            "No product in the current filtered selection has an explicit value "
            "for the selected ranking parameter."
        )
        return

    ranked = execution.ranking
    hidden_rows = max(len(filtered) - len(grouped), 0)

    st.subheader(f"Top {min(top_n, len(ranked_all))} products")
    st.caption(
        (
            f"Ranking parameter: {criterion_label}. "
            f"{len(filtered):,} source records were consolidated into "
            f"{len(grouped):,} technical products; {hidden_rows:,} colour/finish "
            "or article variants are hidden from the main ranking."
        ).replace(",", " ")
    )

    ranking_columns = available_columns(
        ranked,
        [
            "Rank",
            "manufacturer_name",
            "product_family_name",
            "model_name",
            "drain_type_label",
            "mapped_solution_type",
            "drain_element_length_mm",
            *POINT_GEOMETRY_SUMMARY_COLUMNS,
            "flow_rate_20mm_lps",
            "flow_rate_primary_lps",
            "flow_rate_primary_head_mm",
            "height_adj_min_mm",
            "outlet_dn_default",
            "Ranking_Score_%",
            "finish_variant_count",
            "article_variant_count",
            "product_link",
        ],
    )
    st.dataframe(
        ranked[ranking_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn("Rank", format="%d"),
            "manufacturer_name": st.column_config.TextColumn("Manufacturer"),
            "product_family_name": st.column_config.TextColumn("Product family"),
            "model_name": st.column_config.TextColumn("Technical model"),
            "drain_type_label": st.column_config.TextColumn("Drain form"),
            "mapped_solution_type": st.column_config.TextColumn("Solution type"),
            "drain_element_length_mm": st.column_config.NumberColumn("Drain element length [mm]", format="%.0f"),
            "point_top_shape": st.column_config.TextColumn("Point top shape"),
            "point_top_size": st.column_config.TextColumn("Nominal top size"),
            "point_grate_size": st.column_config.TextColumn("Grate size"),
            "point_cover_size": st.column_config.TextColumn("Cover size"),
            "point_body_size": st.column_config.TextColumn("Body size"),
            "drain_position": st.column_config.TextColumn("Drain position"),
            "flow_rate_20mm_lps": st.column_config.NumberColumn(
                "Flow rate at 20 mm [l/s]", format="%.2f"
            ),
            "flow_rate_primary_lps": st.column_config.NumberColumn(
                "Primary flow rate [l/s]", format="%.2f"
            ),
            "flow_rate_primary_head_mm": st.column_config.NumberColumn(
                "Primary head [mm]", format="%.0f"
            ),
            "height_adj_min_mm": st.column_config.NumberColumn(
                "Minimum installation height [mm]", format="%.0f"
            ),
            "outlet_dn_default": st.column_config.TextColumn("Outlet DN"),
            "Ranking_Score_%": st.column_config.NumberColumn("Score", format="%.1f %%"),
            "finish_variant_count": st.column_config.NumberColumn("Finish options", format="%d"),
            "article_variant_count": st.column_config.NumberColumn("Article/configuration variants", format="%d"),
            "product_link": st.column_config.LinkColumn("Product link", display_text="Open"),
        },
    )

    render_ranking_audit_downloads(
        request=request,
        ranking=ranked,
        ranked_all=ranked_all,
        grouped=grouped,
        members=grouped_members,
        source_record_count=len(filtered),
        source_workbook_count=source_workbook_count,
        filename_prefix="shower_drainage_single_parameter_ranking",
    )

    render_ranked_group_details(
        master,
        ranked,
        grouped_members,
        key_prefix="single_rank",
    )


def render_multi_parameter_ranking(
    master: MasterData,
    filtered: pd.DataFrame,
    *,
    criterion_labels: list[str],
    criterion_weights: dict[str, float],
    top_n: int,
    filter_payload: dict[str, object],
    source_workbook_count: int,
) -> None:
    """Render a user-weighted ranking across two or more selected metrics."""

    criteria = {
        SINGLE_PARAMETER_OPTIONS[label]["column"]: bool(
            SINGLE_PARAMETER_OPTIONS[label]["higher_is_better"]
        )
        for label in criterion_labels
    }
    criterion_label_map = {
        SINGLE_PARAMETER_OPTIONS[label]["column"]: label.split(" —", 1)[0]
        for label in criterion_labels
    }
    request = build_ranking_request(
        mode="multi_parameter",
        criteria=criteria,
        weights=criterion_weights,
        criterion_labels=criterion_label_map,
        top_n=top_n,
        filters=filter_payload,
    )
    execution = execute_ranking_request(filtered, request)
    grouped = execution.grouped
    grouped_members = execution.members
    normalised_weights = normalise_ranking_weights(criteria, criterion_weights)
    ranked_all = execution.ranked_all
    if ranked_all.empty:
        st.warning(
            "No technical product in the current filtered selection has explicit "
            "values for every selected ranking parameter."
        )
        return

    ranked = execution.ranking
    hidden_rows = max(len(filtered) - len(grouped), 0)
    excluded_incomplete = max(len(grouped) - len(ranked_all), 0)
    complete_share = (len(ranked_all) / len(grouped) * 100.0) if len(grouped) else 0.0
    score_columns = tuple(
        multi_parameter_score_column(SINGLE_PARAMETER_OPTIONS[label]["column"])
        for label in criterion_labels
    )
    overall_score_column = "Ranking_Score_%"

    st.subheader(f"Top {min(top_n, len(ranked_all))} optimal combinations")
    weight_summary = "; ".join(
        f"{label.split(' —', 1)[0]} {normalised_weights[SINGLE_PARAMETER_OPTIONS[label]['column']] * 100:.1f}%"
        for label in criterion_labels
    )
    st.caption(
        (
            f"Normalised weights: {weight_summary}. "
            f"{len(filtered):,} source records were consolidated into "
            f"{len(grouped):,} technical products; {hidden_rows:,} colour/finish "
            f"or article variants are hidden. {len(ranked_all):,} products "
            f"({complete_share:.1f}%) have complete data for every selected "
            f"criterion; {excluded_incomplete:,} were excluded for missing values."
        ).replace(",", " ")
    )

    weight_profile = pd.DataFrame(
        [
            {
                "Criterion": label.split(" —", 1)[0],
                "Direction": (
                    "Higher is better"
                    if SINGLE_PARAMETER_OPTIONS[label]["higher_is_better"]
                    else "Lower is better"
                ),
                "Raw weight": criterion_weights[
                    SINGLE_PARAMETER_OPTIONS[label]["column"]
                ],
                "Normalised weight [%]": normalised_weights[
                    SINGLE_PARAMETER_OPTIONS[label]["column"]
                ]
                * 100.0,
            }
            for label in criterion_labels
        ]
    )
    st.dataframe(
        weight_profile,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Raw weight": st.column_config.NumberColumn(format="%.1f"),
            "Normalised weight [%]": st.column_config.NumberColumn(format="%.1f %%"),
        },
    )

    with st.expander("How the combined ranking is calculated"):
        st.markdown(
            "Each selected metric is normalised to a **0–100 score** within the "
            "current mandatory-filtered comparison set. Higher-is-better metrics "
            "reward larger values; lower-is-better metrics reward smaller values. "
            "The final score is the weighted sum of the metric scores after the "
            "entered weights are automatically normalised to 100%. Products with "
            "a missing selected metric are not ranked."
        )

    selected_value_columns = [
        SINGLE_PARAMETER_OPTIONS[label]["column"] for label in criterion_labels
    ]
    ranking_columns = available_columns(
        ranked,
        [
            "Rank",
            "manufacturer_name",
            "product_family_name",
            "model_name",
            "drain_type_label",
            "mapped_solution_type",
            "drain_element_length_mm",
            *POINT_GEOMETRY_SUMMARY_COLUMNS,
            *selected_value_columns,
            "outlet_dn_default",
            "material_v4a",
            "sales_price_value",
            "sales_price_currency",
            "sales_price_group_basis",
            "colours_count",
            "colours_count_source",
            *score_columns,
            overall_score_column,
            "finish_variant_count",
            "article_variant_count",
            "product_link",
        ],
    )

    column_config: dict[str, object] = {
        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
        "manufacturer_name": st.column_config.TextColumn("Manufacturer"),
        "product_family_name": st.column_config.TextColumn("Product family"),
        "model_name": st.column_config.TextColumn("Technical model"),
        "drain_type_label": st.column_config.TextColumn("Drain form"),
        "mapped_solution_type": st.column_config.TextColumn("Solution type"),
        "drain_element_length_mm": st.column_config.NumberColumn(
            "Drain element length [mm]", format="%.0f"
        ),
        "point_top_shape": st.column_config.TextColumn("Point top shape"),
        "point_top_size": st.column_config.TextColumn("Nominal top size"),
        "point_grate_size": st.column_config.TextColumn("Grate size"),
        "point_cover_size": st.column_config.TextColumn("Cover size"),
        "point_body_size": st.column_config.TextColumn("Body size"),
        "drain_position": st.column_config.TextColumn("Drain position"),
        "outlet_dn_default": st.column_config.TextColumn("Outlet DN"),
        "Ranking_Score_%": st.column_config.NumberColumn(
            "Combined score", format="%.1f %%"
        ),
        "finish_variant_count": st.column_config.NumberColumn(
            "Finish options", format="%d"
        ),
        "article_variant_count": st.column_config.NumberColumn(
            "Article/configuration variants", format="%d"
        ),
        "product_link": st.column_config.LinkColumn(
            "Product link", display_text="Open"
        ),
    }
    for label in criterion_labels:
        option = SINGLE_PARAMETER_OPTIONS[label]
        column = option["column"]
        score_column = multi_parameter_score_column(column)
        value_format = "%.2f" if "lps" in column else "%.0f"
        column_config[column] = st.column_config.NumberColumn(
            option["value_label"], format=value_format
        )
        short_label = label.split(" —", 1)[0]
        column_config[score_column] = st.column_config.NumberColumn(
            f"{short_label} score", format="%.1f %%"
        )

    st.dataframe(
        ranked[ranking_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            column: config
            for column, config in column_config.items()
            if column in ranking_columns
        },
    )

    render_ranking_audit_downloads(
        request=request,
        ranking=ranked,
        ranked_all=ranked_all,
        grouped=grouped,
        members=grouped_members,
        source_record_count=len(filtered),
        source_workbook_count=source_workbook_count,
        filename_prefix="shower_drainage_multi_parameter_ranking",
    )

    score_column_labels = {
        multi_parameter_score_column(SINGLE_PARAMETER_OPTIONS[label]["column"]):
        f"{label.split(' —', 1)[0]} score"
        for label in criterion_labels
    }
    render_ranked_group_details(
        master,
        ranked,
        grouped_members,
        key_prefix="multi_rank",
        score_columns=score_columns,
        score_column_labels=score_column_labels,
        overall_score_column=overall_score_column,
    )




def reference_product_labels(frame: pd.DataFrame) -> dict[str, str]:
    """Create readable, unique labels for reference-product selection."""

    if frame.empty or "presentation_group_key" not in frame.columns:
        return {}
    labels: dict[str, str] = {}
    for position, (_, row) in enumerate(frame.iterrows(), start=1):
        key = row.get("presentation_group_key")
        if pd.isna(key) or not str(key).strip():
            continue
        manufacturer = _display_text(
            row.get("manufacturer_name"),
            _display_text(row.get("manufacturer_key"), "Unknown manufacturer"),
        )
        family = _display_text(row.get("product_family_name"), "")
        model = _display_text(
            row.get("model_name"),
            _display_text(row.get("variant_name"), "Unknown product"),
        )
        details: list[str] = []
        reference_length_field = (
            "drain_element_length_mm"
            if pd.notna(row.get("drain_element_length_mm"))
            else "nominal_length_mm"
        )
        for column, suffix in (
            (reference_length_field, "mm drain element"),
            ("height_adj_min_mm", "mm installation height"),
            ("flow_rate_20mm_lps", "l/s at 20 mm"),
        ):
            value = row.get(column)
            if pd.isna(value):
                continue
            try:
                number = float(value)
                details.append(f"{number:g} {suffix}")
            except (TypeError, ValueError):
                details.append(f"{value} {suffix}")
        outlet = _display_text(row.get("outlet_dn_default"), "")
        if outlet:
            details.append(outlet)
        family_text = f" / {family}" if family and family != model else ""
        detail_text = f" — {' · '.join(details)}" if details else ""
        label = f"{manufacturer}{family_text} / {model}{detail_text}"
        if label in labels:
            label = f"{label} ({position})"
        labels[label] = str(key)
    return labels


def _normalise_reference_search_text(value: object) -> str:
    """Return a punctuation-insensitive search representation."""

    if value is None or pd.isna(value):
        return ""
    return "".join(character for character in str(value).casefold() if character.isalnum())


def filter_reference_product_groups(
    groups: pd.DataFrame,
    members: pd.DataFrame,
    query: str,
) -> pd.DataFrame:
    """Filter reference-product groups by product text or any member article number.

    Search is case-insensitive and ignores punctuation in both the query and the
    source values. Multiple whitespace-separated terms must all be present. This
    allows searches such as ``FLOWLINE 1200``, ``691600`` or formatted article
    numbers such as ``154.450.KS.1``.
    """

    query = str(query or "").strip()
    if not query or groups.empty:
        return groups.copy()

    tokens = [
        _normalise_reference_search_text(token)
        for token in query.split()
        if _normalise_reference_search_text(token)
    ]
    if not tokens:
        return groups.copy()

    search_columns = [
        "manufacturer_article_no",
        "record_id",
        "system_key",
        "model_key",
        "model_name",
        "variant_key",
        "variant_name",
        "system_name",
        "product_family_key",
        "product_family_name",
        "finish_name",
        "length_mm",
        "nominal_length_mm",
        "drain_element_length_mm",
        *POINT_GEOMETRY_SEARCH_COLUMNS,
        "outlet_dn_default",
    ]

    available_member_columns = [
        column for column in search_columns if column in members.columns
    ]
    if not available_member_columns or "presentation_group_key" not in members.columns:
        # Fall back to representative/group rows if member-level data is not available.
        available_group_columns = [
            column for column in search_columns if column in groups.columns
        ]
        if not available_group_columns:
            return groups.iloc[0:0].copy()
        group_blobs = groups[available_group_columns].fillna("").astype(str).agg(" ".join, axis=1)
        normalised_blobs = group_blobs.map(_normalise_reference_search_text)
        mask = normalised_blobs.map(lambda text: all(token in text for token in tokens))
        return groups.loc[mask].copy()

    member_blobs = (
        members[available_member_columns]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .map(_normalise_reference_search_text)
    )
    searchable_members = pd.DataFrame(
        {
            "presentation_group_key": members["presentation_group_key"].astype("string"),
            "search_blob": member_blobs,
        }
    )
    group_blobs = (
        searchable_members.groupby("presentation_group_key", sort=False)["search_blob"]
        .agg("".join)
    )
    matching_keys = {
        str(key)
        for key, text in group_blobs.items()
        if all(token in str(text) for token in tokens)
    }
    return groups[
        groups["presentation_group_key"].astype("string").isin(matching_keys)
    ].copy()


def _reference_value(row: pd.Series, column: str) -> float | None:
    value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
    return None if pd.isna(value) else float(value)


def render_reference_product_comparison(
    master: MasterData,
    filtered: pd.DataFrame,
    *,
    score_weights: dict[str, int],
    top_n: int,
    source_workbook_count: int,
) -> None:
    """Filter around a reference system, then score the comparable set independently."""

    if sum(float(value) for value in score_weights.values()) <= 0:
        st.warning("Set at least one independent scoring weight above zero.")
        return

    # The competitor pool remains strict: only complete/assembled systems that pass
    # the current mandatory requirements are ranked. Reference selection is broader
    # on purpose, so users can search known product names/article numbers even when
    # the database currently stores that reference as a partial system.
    source = filtered.copy()
    if "candidate_type" in source.columns:
        candidate_types = source["candidate_type"].astype("string").str.strip().str.casefold()
        source = source[candidate_types.isin(["complete_system", "assembled_system", "complete_product"])].copy()
    if source.empty:
        st.warning("No final or assembled competitor system is available in the current mandatory scope.")
        return

    grouped, grouped_members = aggregate_presentation_groups(source)
    if grouped.empty:
        st.warning("No technical product group is available in the current competitor scope.")
        return

    # Build a separate searchable reference catalogue from all system-like records,
    # independent of leaderboard visibility. This makes names such as ORIO / DallBox
    # discoverable even when a record is partial or currently not benchmark-eligible.
    reference_source = master.flat.copy()
    reference_mask = pd.Series(False, index=reference_source.index, dtype="bool")
    if "benchmark_entity_type" in reference_source.columns:
        reference_mask |= (
            reference_source["benchmark_entity_type"]
            .astype("string")
            .str.strip()
            .str.casefold()
            .eq("system")
        )
    if "candidate_type" in reference_source.columns:
        reference_candidate_types = (
            reference_source["candidate_type"].astype("string").str.strip().str.casefold()
        )
        reference_mask |= reference_candidate_types.isin(
            ["complete_system", "assembled_system", "complete_product", "partial_system"]
        )
    reference_source = reference_source.loc[reference_mask].copy()
    if reference_source.empty:
        st.warning("No system-like product is available for reference selection.")
        return

    reference_grouped, reference_grouped_members = aggregate_presentation_groups(reference_source)
    if reference_grouped.empty:
        st.warning("No technical product group is available for reference selection.")
        return

    st.subheader("Reference-product comparison")
    st.caption(
        "The reference product is used only to create a technically comparable set. "
        "There is no similarity score. Every comparable product, including the "
        "reference, is then scored independently with the same benchmark rules."
    )

    manufacturer_column = (
        "manufacturer_name"
        if "manufacturer_name" in reference_grouped.columns
        else "manufacturer_key"
    )
    manufacturer_options = sorted(
        reference_grouped[manufacturer_column]
        .astype("string")
        .str.strip()
        .dropna()
        .loc[lambda s: s.ne("")]
        .unique()
        .tolist(),
        key=str.casefold,
    )
    if not manufacturer_options:
        st.warning("Reference-product manufacturers could not be resolved.")
        return

    selection_columns = st.columns([1, 2])
    with selection_columns[0]:
        reference_manufacturer = st.selectbox(
            "Reference manufacturer",
            options=manufacturer_options,
            key="reference_product_manufacturer",
        )

    manufacturer_groups = reference_grouped[
        reference_grouped[manufacturer_column]
        .astype("string")
        .str.strip()
        .eq(reference_manufacturer)
    ].copy()
    manufacturer_group_keys = set(
        manufacturer_groups["presentation_group_key"].astype("string").tolist()
    )
    manufacturer_members = reference_grouped_members[
        reference_grouped_members["presentation_group_key"]
        .astype("string")
        .isin(manufacturer_group_keys)
    ].copy()

    with selection_columns[1]:
        reference_search = st.text_input(
            "Search product name or article number",
            key="reference_product_search",
            placeholder="e.g. FLOWLINE 1200, CleanLine, 691600, 154.450...",
            help=(
                "Searches complete and partial system names, model/family names, IDs "
                "and exact manufacturer article numbers within the selected manufacturer. "
                "A partial product can be selected as the reference, but only complete/"
                "assembled products enter the competitor ranking pool."
            ),
        )
        searched_groups = filter_reference_product_groups(
            manufacturer_groups,
            manufacturer_members,
            reference_search,
        )
        labels = reference_product_labels(searched_groups)
        st.caption(
            f"Showing {len(labels):,} of {len(manufacturer_groups):,} technical products "
            f"for {reference_manufacturer}."
        )
        if not labels:
            st.warning(
                "No system-like product matches this search. Try part of the product "
                "name, model, family or manufacturer article number."
            )
            return
        reference_label = st.selectbox(
            "Reference technical product / final set",
            options=list(labels),
            key="reference_product_group",
        )
    reference_key = labels[reference_label]
    reference_row = manufacturer_groups[
        manufacturer_groups["presentation_group_key"].astype("string").eq(reference_key)
    ].iloc[0]

    reference_candidate_type = _display_text(reference_row.get("candidate_type"), "unknown")
    reference_completeness = _display_text(reference_row.get("completeness_status"), "unknown")
    if reference_candidate_type.casefold() not in {"complete_system", "assembled_system", "complete_product"}:
        st.info(
            "The selected reference is stored as a partial/non-final system in the database. "
            "It will still be retained as the reference, but it may be shown as not rankable "
            "if required scoring data is missing. Competitor ranking remains limited to "
            "complete/assembled systems."
        )
        st.caption(
            f"Reference database status: {reference_candidate_type} · {reference_completeness}"
        )

    # Ensure the selected reference group is present in the execution source even when
    # it is partial or hidden from the normal leaderboard. The rest of the execution
    # source remains the strict complete/assembled competitor pool.
    selected_reference_members = reference_grouped_members[
        reference_grouped_members["presentation_group_key"]
        .astype("string")
        .eq(reference_key)
    ].copy()
    execution_source = pd.concat([source, selected_reference_members], ignore_index=True)
    if "record_id" in execution_source.columns:
        execution_source = execution_source.drop_duplicates(subset=["record_id"], keep="first")

    st.markdown("### 1. Reference values")
    reference_drain_form = _display_text(
        reference_row.get("mapped_drain_form"), ""
    ).casefold()
    reference_metrics = st.columns(6)
    if reference_drain_form == "point":
        metric_specs = (
            ("Grate size", "point_grate_size", "", ""),
            ("Top shape", "point_top_shape", "", ""),
            ("Flow at 20 mm", "flow_rate_20mm_lps", "l/s", ".2f"),
            ("Installation height", "height_adj_min_mm", "mm", ".0f"),
            ("Water seal", "water_seal_mm", "mm", ".0f"),
            ("Outlet", "outlet_dn_default", "", ""),
        )
    else:
        metric_specs = (
            ("Drain element length", "drain_element_length_mm", "mm", ".0f"),
            ("Flow at 20 mm", "flow_rate_20mm_lps", "l/s", ".2f"),
            ("Installation height", "height_adj_min_mm", "mm", ".0f"),
            ("Water seal", "water_seal_mm", "mm", ".0f"),
            ("Outlet", "outlet_dn_default", "", ""),
            ("V4A", "material_v4a", "", ""),
        )
    for column, (label, field, unit, number_format) in zip(reference_metrics, metric_specs):
        value = reference_row.get(field)
        if number_format and pd.notna(value):
            try:
                display_value = f"{float(value):{number_format}} {unit}".strip()
            except (TypeError, ValueError):
                display_value = _display_text(value)
        else:
            display_value = _display_text(value)
        column.metric(label, display_value)

    st.markdown("### 2. Similarity tolerances (eligibility only)")
    st.caption(
        "A product either meets every active tolerance or it is excluded. Differences "
        "to the reference are shown for information only and never add or remove score points."
    )

    numeric_tolerances: dict[str, dict[str, object]] = {}
    exact_match_fields: list[str] = ["mapped_drain_form"]

    exact_col1, exact_col2, exact_col3, exact_col4 = st.columns(4)
    with exact_col1:
        solution_known = bool(_display_text(reference_row.get("mapped_solution_type"), ""))
        require_same_solution = st.checkbox(
            "Require the same solution type",
            value=solution_known,
            key="reference_same_solution_type",
            disabled=not solution_known,
        )
    if require_same_solution and solution_known:
        exact_match_fields.append("mapped_solution_type")
    with exact_col2:
        category_known = bool(_display_text(reference_row.get("product_category"), ""))
        require_same_category = st.checkbox(
            "Require the same source product category",
            value=False,
            key="reference_same_product_category",
            disabled=not category_known,
            help="Source categories are manufacturer-specific. Use this only for a deliberately narrow comparison.",
        )
    if require_same_category and category_known:
        exact_match_fields.append("product_category")
    with exact_col3:
        outlet_known = bool(_display_text(reference_row.get("outlet_dn_default"), ""))
        require_same_outlet = st.checkbox(
            "Require the same outlet DN",
            value=outlet_known,
            key="reference_same_outlet_dn",
            disabled=not outlet_known,
        )
    if require_same_outlet and outlet_known:
        exact_match_fields.append("outlet_dn_default")
    with exact_col4:
        v4a_value = _display_text(reference_row.get("material_v4a"), "").casefold()
        v4a_known = v4a_value in {"yes", "no"}
        require_same_v4a = st.checkbox(
            "Require the same V4A status",
            value=False,
            key="reference_same_v4a",
            disabled=not v4a_known,
        )
    if require_same_v4a and v4a_known:
        exact_match_fields.append("material_v4a")

    if reference_drain_form == "point":
        point_shape_value = _display_text(reference_row.get("point_top_shape"), "")
        require_same_point_shape = st.checkbox(
            "Require the same explicit point-top shape",
            value=False,
            key="reference_same_point_top_shape",
            disabled=not bool(point_shape_value),
            help=(
                "This is applied only when the reference has an explicit shape. "
                "No shape is inferred from dimensions."
            ),
        )
        if require_same_point_shape and point_shape_value:
            exact_match_fields.append("point_top_shape")

        point_geometry_tolerance_specs = (
            ("point_grate_length_mm", "Grate length"),
            ("point_grate_width_mm", "Grate width"),
            ("point_grate_diameter_mm", "Grate diameter"),
            ("point_top_nominal_length_mm", "Nominal top length"),
            ("point_top_nominal_width_mm", "Nominal top width"),
            ("point_top_nominal_diameter_mm", "Nominal top diameter"),
            ("point_body_diameter_mm", "Body diameter"),
        )
        available_point_geometry = [
            (field, label, _reference_value(reference_row, field))
            for field, label in point_geometry_tolerance_specs
            if _reference_value(reference_row, field) is not None
        ]
        if available_point_geometry:
            with st.expander("Point-drain geometry tolerances", expanded=False):
                st.caption(
                    "Only explicit canonical point geometry is offered. Generic product "
                    "length/width is never treated as grate geometry."
                )
                for field, label, reference_value in available_point_geometry:
                    control_col, tolerance_col = st.columns([2, 1])
                    use_geometry = control_col.checkbox(
                        f"Use {label.lower()} ({float(reference_value):g} mm)",
                        value=False,
                        key=f"reference_use_{field}",
                    )
                    tolerance_value = tolerance_col.number_input(
                        f"± mm for {label}",
                        min_value=0.0,
                        value=10.0,
                        step=1.0,
                        key=f"reference_tolerance_{field}",
                        disabled=not use_geometry,
                    )
                    if use_geometry:
                        numeric_tolerances[field] = {
                            "mode": "absolute",
                            "value": float(tolerance_value),
                        }

    tolerance_columns = st.columns(2)
    with tolerance_columns[0]:
        length_value = _reference_value(reference_row, "drain_element_length_mm")
        use_length = st.checkbox(
            "Use drain-element length",
            value=length_value is not None,
            key="reference_use_length",
            disabled=length_value is None,
        )
        length_tolerance = st.number_input(
            "Allowed length difference [mm]",
            min_value=0.0,
            value=100.0,
            step=10.0,
            key="reference_length_tolerance",
            disabled=not use_length,
        )
        if use_length and length_value is not None:
            numeric_tolerances["drain_element_length_mm"] = {
                "mode": "absolute",
                "value": float(length_tolerance),
            }

        height_value = _reference_value(reference_row, "height_adj_min_mm")
        use_height = st.checkbox(
            "Use minimum installation height",
            value=height_value is not None,
            key="reference_use_height",
            disabled=height_value is None,
        )
        height_tolerance = st.number_input(
            "Allowed installation-height difference [mm]",
            min_value=0.0,
            value=15.0,
            step=1.0,
            key="reference_height_tolerance",
            disabled=not use_height,
        )
        if use_height and height_value is not None:
            numeric_tolerances["height_adj_min_mm"] = {
                "mode": "absolute",
                "value": float(height_tolerance),
            }

    with tolerance_columns[1]:
        flow_value = _reference_value(reference_row, "flow_rate_20mm_lps")
        use_flow = st.checkbox(
            "Use flow rate at 20 mm head",
            value=flow_value is not None,
            key="reference_use_flow_20mm",
            disabled=flow_value is None,
        )
        flow_mode_label = st.radio(
            "Flow tolerance type",
            options=["Absolute [l/s]", "Percentage [%]"],
            horizontal=True,
            key="reference_flow_tolerance_mode",
            disabled=not use_flow,
        )
        if flow_mode_label == "Percentage [%]":
            flow_tolerance = st.number_input(
                "Allowed flow-rate difference [%]",
                min_value=0.0,
                value=20.0,
                step=1.0,
                key="reference_flow_tolerance_percent",
                disabled=not use_flow,
            )
            flow_mode = "percent"
        else:
            flow_tolerance = st.number_input(
                "Allowed flow-rate difference [l/s]",
                min_value=0.0,
                value=0.20,
                step=0.05,
                format="%.2f",
                key="reference_flow_tolerance_absolute",
                disabled=not use_flow,
            )
            flow_mode = "absolute"
        if use_flow and flow_value is not None:
            numeric_tolerances["flow_rate_20mm_lps"] = {
                "mode": flow_mode,
                "value": float(flow_tolerance),
            }

        water_seal_value = _reference_value(reference_row, "water_seal_mm")
        use_water_seal = st.checkbox(
            "Use water seal",
            value=False,
            key="reference_use_water_seal",
            disabled=water_seal_value is None,
        )
        water_seal_tolerance = st.number_input(
            "Allowed water-seal difference [mm]",
            min_value=0.0,
            value=10.0,
            step=1.0,
            key="reference_water_seal_tolerance",
            disabled=not use_water_seal,
        )
        if use_water_seal and water_seal_value is not None:
            numeric_tolerances["water_seal_mm"] = {
                "mode": "absolute",
                "value": float(water_seal_tolerance),
            }

    if not numeric_tolerances and len(exact_match_fields) == 1:
        st.warning(
            "Activate at least one tolerance or exact-match condition in addition "
            "to the always-required drain form."
        )
        return

    try:
        execution = execute_reference_product_comparison(
            execution_source,
            reference_key,
            numeric_tolerances=numeric_tolerances,
            exact_match_fields=exact_match_fields,
            weights=score_weights,
            top_n=top_n,
        )
    except ValueError as error:
        st.error(str(error))
        return

    comparable = execution.comparable_groups
    ranked_all = execution.ranked_all
    ranked = execution.ranked
    unranked = execution.unranked
    if comparable.empty:
        st.warning("No product meets the selected similarity tolerances.")
        return

    st.markdown("### 3. Comparable set and independent benchmark scoring")
    ranked_count = len(ranked_all)
    manufacturer_count = (
        int(comparable["manufacturer_key"].astype("string").nunique(dropna=True))
        if "manufacturer_key" in comparable.columns
        else 0
    )
    summary_columns = st.columns(4)
    summary_columns[0].metric("Technical products evaluated", len(grouped))
    summary_columns[1].metric("Products meeting tolerances", len(comparable))
    summary_columns[2].metric("Manufacturers represented", manufacturer_count)
    summary_columns[3].metric("Rankable products", ranked_count)

    with st.expander("Active tolerance rules", expanded=False):
        st.dataframe(
            execution.tolerance_audit,
            use_container_width=True,
            hide_index=True,
            column_config={
                "reference_value": st.column_config.NumberColumn(format="%.3f"),
                "tolerance_value": st.column_config.NumberColumn(format="%.3f"),
                "accepted_minimum": st.column_config.NumberColumn(format="%.3f"),
                "accepted_maximum": st.column_config.NumberColumn(format="%.3f"),
            },
        )

    st.info(
        "Scoring is normalised only within this comparable set. The reference "
        "product is scored by the same independent criteria as every competitor."
    )

    result_columns = available_columns(
        ranked,
        [
            "Rank",
            "Reference_Label",
            "Ranking_Status",
            "manufacturer_name",
            "product_family_name",
            "model_name",
            "mapped_drain_form",
            "mapped_solution_type",
            "drain_element_length_mm",
            "Delta_vs_reference_drain_element_length_mm",
            *POINT_GEOMETRY_SUMMARY_COLUMNS,
            "flow_rate_20mm_lps",
            "Delta_vs_reference_flow_rate_20mm_lps",
            "height_adj_min_mm",
            "Delta_vs_reference_height_adj_min_mm",
            "water_seal_mm",
            "Delta_vs_reference_water_seal_mm",
            "outlet_dn_default",
            "material_v4a",
            "flow_rate_primary_lps",
            "sales_price_value",
            "sales_price_currency",
            "colours_count",
            "Score_Flow_Rate_%",
            "Score_Installation_Height_%",
            "Score_V4A_%",
            "Score_Sales_Price_%",
            "Score_Colours_%",
            "Final_Score_%",
            "Missing_Ranking_Fields",
            "product_link",
        ],
    )
    st.dataframe(
        ranked[result_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn("Rank", format="%d"),
            "Reference_Label": st.column_config.TextColumn("Reference"),
            "Ranking_Status": st.column_config.TextColumn("Ranking status"),
            "manufacturer_name": st.column_config.TextColumn("Manufacturer"),
            "product_family_name": st.column_config.TextColumn("Product family"),
            "model_name": st.column_config.TextColumn("Technical product"),
            "mapped_drain_form": st.column_config.TextColumn("Drain form"),
            "mapped_solution_type": st.column_config.TextColumn("Solution type"),
            "drain_element_length_mm": st.column_config.NumberColumn("Drain element length [mm]", format="%.0f"),
            "Delta_vs_reference_drain_element_length_mm": st.column_config.NumberColumn("Drain length delta [mm]", format="%+.0f"),
            "point_top_shape": st.column_config.TextColumn("Point top shape"),
            "point_top_size": st.column_config.TextColumn("Nominal top size"),
            "point_grate_size": st.column_config.TextColumn("Grate size"),
            "point_cover_size": st.column_config.TextColumn("Cover size"),
            "point_body_size": st.column_config.TextColumn("Body size"),
            "drain_position": st.column_config.TextColumn("Drain position"),
            "flow_rate_20mm_lps": st.column_config.NumberColumn("Flow at 20 mm [l/s]", format="%.2f"),
            "Delta_vs_reference_flow_rate_20mm_lps": st.column_config.NumberColumn("Flow delta [l/s]", format="%+.2f"),
            "height_adj_min_mm": st.column_config.NumberColumn("Installation height [mm]", format="%.0f"),
            "Delta_vs_reference_height_adj_min_mm": st.column_config.NumberColumn("Height delta [mm]", format="%+.0f"),
            "water_seal_mm": st.column_config.NumberColumn("Water seal [mm]", format="%.0f"),
            "Delta_vs_reference_water_seal_mm": st.column_config.NumberColumn("Water-seal delta [mm]", format="%+.0f"),
            "outlet_dn_default": st.column_config.TextColumn("Outlet DN"),
            "material_v4a": st.column_config.TextColumn("V4A"),
            "flow_rate_primary_lps": st.column_config.NumberColumn("Primary flow [l/s]", format="%.2f"),
            "sales_price_value": st.column_config.NumberColumn("Price", format="%.2f"),
            "sales_price_currency": st.column_config.TextColumn("Currency"),
            "colours_count": st.column_config.NumberColumn("Finish options", format="%.0f"),
            "Score_Flow_Rate_%": st.column_config.NumberColumn("Flow score", format="%.1f %%"),
            "Score_Installation_Height_%": st.column_config.NumberColumn("Height score", format="%.1f %%"),
            "Score_V4A_%": st.column_config.NumberColumn("V4A score", format="%.1f %%"),
            "Score_Sales_Price_%": st.column_config.NumberColumn("Price score", format="%.1f %%"),
            "Score_Colours_%": st.column_config.NumberColumn("Finish score", format="%.1f %%"),
            "Final_Score_%": st.column_config.NumberColumn("Final score", format="%.1f %%"),
            "Missing_Ranking_Fields": st.column_config.TextColumn("Missing scoring data"),
            "product_link": st.column_config.LinkColumn("Product", display_text="Open"),
        },
    )

    if not unranked.empty:
        with st.expander(
            f"Comparable competitors not rankable because of missing scoring data ({len(unranked)})"
        ):
            unranked_columns = available_columns(
                unranked,
                [
                    "manufacturer_name",
                    "product_family_name",
                    "model_name",
                    "nominal_length_mm",
                    "flow_rate_primary_lps",
                    "height_adj_min_mm",
                    "material_v4a",
                    "Missing_Ranking_Fields",
                    "product_link",
                ],
            )
            st.dataframe(
                unranked[unranked_columns],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "product_link": st.column_config.LinkColumn("Product", display_text="Open")
                },
            )

    weight_rows = []
    weight_labels = {
        "flow_rate": ("Primary flow rate", "higher is better"),
        "installation_height": ("Minimum installation height", "lower is better"),
        "v4a": ("V4A material", "yes is better"),
        "sales_price": ("Sales price", "lower is better"),
        "colours": ("Number of colours/finishes", "higher is better"),
    }
    total_weight = sum(max(float(value), 0.0) for value in score_weights.values())
    for metric, raw_weight in score_weights.items():
        label, direction = weight_labels[metric]
        weight_rows.append(
            {
                "metric": metric,
                "criterion": label,
                "direction": direction,
                "raw_weight": raw_weight,
                "normalised_weight_percent": (
                    max(float(raw_weight), 0.0) / total_weight * 100.0 if total_weight else 0.0
                ),
            }
        )
    weight_frame = pd.DataFrame(weight_rows)
    audit_tables = {
        "Reference_Product": execution.reference,
        "Tolerance_Rules": execution.tolerance_audit,
        "Ranked_Comparison": ranked_all,
        "Displayed_Leaderboard": ranked,
        "Unranked_Comparable": unranked,
        "Scoring_Weights": weight_frame,
        "Comparable_Variants": execution.comparable_members,
        "Run_Metadata": pd.DataFrame(
            [
                {
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source_workbook_count": source_workbook_count,
                    "technical_products_evaluated": len(grouped),
                    "comparable_products": len(comparable),
                    "ranked_products_total": ranked_count,
                    "leaderboard_rows_shown": len(ranked),
                    "reference_group_key": reference_key,
                    "similarity_score_used": False,
                    "score_normalisation_scope": "current comparable set",
                    "missing_data_policy": "require_complete_reference_retained",
                }
            ]
        ),
    }
    st.download_button(
        "Download reference comparison audit (.xlsx)",
        data=dataframes_to_excel(audit_tables),
        file_name="shower_drainage_reference_product_comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    render_ranked_group_details(
        master,
        ranked,
        execution.comparable_members,
        key_prefix="reference_comparison",
        score_columns=(
            "Score_Flow_Rate_%",
            "Score_Installation_Height_%",
            "Score_V4A_%",
            "Score_Sales_Price_%",
            "Score_Colours_%",
        ),
        score_column_labels={
            "Score_Flow_Rate_%": "Flow score",
            "Score_Installation_Height_%": "Height score",
            "Score_V4A_%": "V4A score",
            "Score_Sales_Price_%": "Price score",
            "Score_Colours_%": "Finish score",
        },
        overall_score_column="Final_Score_%",
        overall_score_label="Final score",
    )


def render_active_mandatory_requirements(
    filter_payload: dict[str, object],
    *,
    source_record_count: int,
    filtered_record_count: int,
) -> None:
    """Show the hard constraints separately from ranking preferences."""

    requirements = mandatory_requirements_from_filters(filter_payload)
    requirement_table = mandatory_requirements_table(requirements)
    with st.expander(
        f"Active mandatory requirements ({len(requirements)})",
        expanded=False,
    ):
        st.caption(
            "Mandatory requirements decide which products are eligible. Ranking "
            "criteria only order the eligible technical products."
        )
        if requirement_table.empty:
            st.info("No mandatory requirement is active.")
        else:
            visible_columns = [
                column
                for column in ["Requirement", "Operator", "Value", "Unit", "Notes"]
                if column in requirement_table.columns
            ]
            st.dataframe(
                requirement_table[visible_columns],
                use_container_width=True,
                hide_index=True,
            )
        reduction = max(source_record_count - filtered_record_count, 0)
        st.caption(
            f"Eligibility pipeline: {source_record_count:,} source records → "
            f"{filtered_record_count:,} records after mandatory requirements "
            f"({reduction:,} excluded).".replace(",", " ")
        )

def main() -> None:
    require_password()
    render_logout_control()

    st.title("Shower Drainage System Comparator")
    st.caption(
        "Data is loaded automatically from all `.xlsx` files in the `data/` directory. "
        "Legacy masters and canonical v2 masters, including compressed secondary archives, "
        "are normalised into one benchmark view."
    )

    DATA_DIRECTORY.mkdir(exist_ok=True)
    local_workbooks = discover_local_workbooks(DATA_DIRECTORY)
    classification_rules_signature = file_signature(CLASSIFICATION_RULES_PATH)
    length_rules_signature = file_signature(LENGTH_RULES_PATH)

    missing_config = [
        str(path.relative_to(APP_ROOT))
        for path, signature in [
            (CLASSIFICATION_RULES_PATH, classification_rules_signature),
            (LENGTH_RULES_PATH, length_rules_signature),
        ]
        if signature is None
    ]
    if missing_config:
        st.error(
            "Missing configuration files: " + ", ".join(f"`{name}`" for name in missing_config)
        )
        st.info("Place both approved CSV files in the `config/` directory next to `app.py`.")
        st.stop()

    with st.sidebar:
        st.header("Data sources")
        uploaded_files = st.file_uploader(
            "Add Excel workbooks",
            type=["xlsx"],
            accept_multiple_files=True,
            help="Uploaded workbooks are merged with the contents of the `data/` directory.",
        )
        render_help_and_user_guide()

    uploaded_workbooks = tuple(
        (uploaded_file.name, uploaded_file.getvalue()) for uploaded_file in (uploaded_files or [])
    )
    try:
        master = load_master_data(
            local_workbooks,
            uploaded_workbooks,
            classification_rules_signature,
            length_rules_signature,
        )
    except Exception as error:
        st.error(f"Configuration rules or input data could not be loaded: {error}")
        st.stop()

    for warning in master.warnings:
        st.warning(warning)

    if master.source_count == 0:
        st.info("No Excel workbook is currently available in the `data/` directory or in the upload selection.")
        st.stop()
    if master.flat.empty:
        st.info("No data was found in the `01_Flat_Input` sheets.")
        st.stop()

    render_hierarchy_status(master.flat)
    render_v2_data_status(master)

    with st.sidebar:
        st.divider()
        st.header("1. Mandatory requirements")
        st.caption(
            "These controls define product eligibility. They do not affect the "
            "relative importance of ranking criteria."
        )
        st.markdown("#### Product scope")

        selected_drain_type_label = st.selectbox(
            "Drain form",
            options=list(DRAIN_TYPE_OPTIONS),
            index=0,
            help=(
                "Choose the physical drain form. Solution type is filtered separately, so "
                "integrated shower elements can still be compared as linear or point drainage."
            ),
        )
        selected_drain_form = DRAIN_TYPE_OPTIONS[selected_drain_type_label]

        include_incomplete = st.checkbox(
            "Include incomplete systems and components", value=False
        )

        manufacturer_filter = active_text_filter(
            "Manufacturer", string_options(master.flat, "manufacturer_key"), key="manufacturer_filter"
        )

        solution_scope = filter_flat_input(
            master.flat,
            include_incomplete=include_incomplete,
            manufacturers=manufacturer_filter,
            flow_range=None,
            height_range=None,
            attribute_filters={},
            drain_forms=None if selected_drain_form is None else [selected_drain_form],
        )
        solution_type_filter = active_token_filter(
            "Solution type",
            string_options(solution_scope, "mapped_solution_type"),
            key="solution_type_filter",
        )

        scope_frame = filter_flat_input(
            master.flat,
            include_incomplete=include_incomplete,
            manufacturers=manufacturer_filter,
            flow_range=None,
            height_range=None,
            attribute_filters={},
            drain_forms=None if selected_drain_form is None else [selected_drain_form],
            solution_types=solution_type_filter,
        )

        st.markdown("#### Geometry and performance")
        length_filter: tuple[float, float] | None = None
        include_unverified_length = False
        if selected_drain_form == "linear":
            use_length_requirement = st.checkbox(
                "Set a mandatory drain-length range",
                value=False,
                key="activate_length_requirement",
                help=(
                    "When active, a product must have a verified installable range "
                    "that overlaps the selected interval."
                ),
            )
            if use_length_requirement:
                length_selection, verified_length_bounds = length_range_widget(scope_frame)
                verified_count = int(
                    scope_frame.get(
                        "length_filter_ready",
                        pd.Series(index=scope_frame.index, dtype="string"),
                    )
                    .astype("string")
                    .str.casefold()
                    .eq("yes")
                    .sum()
                )
                unverified_count = len(scope_frame) - verified_count
                st.caption(
                    (
                        f"Verified range: {verified_count:,} systems; "
                        f"without a verified range: {unverified_count:,}."
                    ).replace(",", " ")
                )
                if length_selection is not None and verified_length_bounds is not None:
                    length_filter = (
                        float(length_selection[0]),
                        float(length_selection[1]),
                    )
                    include_unverified_length = st.checkbox(
                        "Also include systems without a verified length range",
                        value=False,
                        help=(
                            "These systems are not confirmed as compatible and remain "
                            "in the result for information only."
                        ),
                    )

        flow_selection: tuple[float, float] | None = None
        use_flow_requirement = st.checkbox(
            "Set a mandatory primary flow-rate range",
            value=False,
            key="activate_flow_requirement",
        )
        if use_flow_requirement:
            flow_selection = numeric_range_widget(
                "Primary flow rate [l/s]",
                master.flat,
                "flow_rate_primary_lps",
                key="flow_range",
            )

        height_selection: tuple[float, float] | None = None
        use_height_requirement = st.checkbox(
            "Set a mandatory installation-height range",
            value=False,
            key="activate_height_requirement",
        )
        if use_height_requirement:
            height_selection = numeric_range_widget(
                "Installation height [mm]",
                master.flat,
                "height_adj_min_mm",
                key="height_range",
            )

        if use_flow_requirement or use_height_requirement:
            st.caption(
                "An active numeric requirement excludes products with N/A in that field."
            )

        point_numeric_filters: dict[str, tuple[float, float] | None] = {}
        point_attribute_selections: dict[str, list[str] | None] = {}
        if selected_drain_form == "point":
            st.markdown("#### Point-drain geometry")
            for column, label in POINT_ATTRIBUTE_FILTERS.items():
                options = string_options(scope_frame, column)
                if options:
                    point_attribute_selections[column] = active_text_filter(
                        label, options, key=f"point_attribute_{column}"
                    )

            for column, label in POINT_NUMERIC_FILTERS.items():
                if numeric_bounds(scope_frame, column) is None:
                    continue
                activate = st.checkbox(
                    f"Set mandatory {label.lower()}",
                    value=False,
                    key=f"activate_point_numeric_{column}",
                )
                if activate:
                    point_numeric_filters[column] = numeric_range_widget(
                        label, scope_frame, column, key=f"point_numeric_{column}"
                    )

        st.markdown("#### Materials, standards and installation")
        attribute_selections: dict[str, list[str] | None] = {}
        for column, label in ATTRIBUTE_FILTERS.items():
            attribute_selections[column] = active_text_filter(
                label,
                string_options(scope_frame, column),
                key=f"attribute_{column}",
            )
        attribute_selections.update(point_attribute_selections)

        st.divider()
        st.header("2. Ranking criteria")
        st.caption(
            "Ranking criteria order only the products that passed the mandatory "
            "requirements above."
        )
        benchmark_mode = st.radio(
            "Result method",
            options=BENCHMARK_MODES,
            index=0,
            help=(
                "Single-parameter ranking sorts by one metric. Multi-parameter "
                "ranking finds the best user-weighted combination of selected metrics. "
                "All three modes use stable technical hierarchy keys to group "
                "colour/finish variants. Advanced weighted scoring preserves the "
                "custom five-factor workflow at technical-product level."
            ),
        )

        criterion_label = next(iter(SINGLE_PARAMETER_OPTIONS))
        multi_criterion_labels = list(MULTI_PARAMETER_DEFAULTS)
        multi_criterion_weights: dict[str, float] = {}
        top_n = 10
        advanced_display_limit = 100
        advanced_missing_data_policy = "require_complete"
        score_weights: dict[str, int] = {}
        if benchmark_mode == "Single-parameter ranking":
            criterion_label = st.selectbox(
                "Ranking parameter",
                options=list(SINGLE_PARAMETER_OPTIONS),
                index=0,
            )
            top_n = st.select_slider(
                "Number of ranked products",
                options=[5, 10, 20],
                value=10,
                key="single_top_n",
            )
            st.caption(
                "Surface and colour variants are grouped and remain available in "
                "the product detail section."
            )
        elif benchmark_mode == "Multi-parameter ranking":
            multi_criterion_labels = st.multiselect(
                "Ranking parameters",
                options=list(SINGLE_PARAMETER_OPTIONS),
                default=MULTI_PARAMETER_DEFAULTS,
                help=(
                    "Select at least two parameters. Every selected criterion gets "
                    "a user-defined priority weight."
                ),
            )
            if multi_criterion_labels:
                st.markdown("#### Criterion weights")
                for label in multi_criterion_labels:
                    option = SINGLE_PARAMETER_OPTIONS[label]
                    column = option["column"]
                    short_label = label.split(" —", 1)[0]
                    multi_criterion_weights[column] = float(
                        st.slider(
                            short_label,
                            min_value=1,
                            max_value=10,
                            value=5,
                            step=1,
                            key=f"multi_weight_{column}",
                            help=(
                                "Relative priority. The application automatically "
                                "normalises all selected weights to 100%."
                            ),
                        )
                    )

                selected_criteria = {
                    SINGLE_PARAMETER_OPTIONS[label]["column"]: bool(
                        SINGLE_PARAMETER_OPTIONS[label]["higher_is_better"]
                    )
                    for label in multi_criterion_labels
                }
                normalised_sidebar_weights = normalise_ranking_weights(
                    selected_criteria, multi_criterion_weights
                )
                sidebar_weight_text = " · ".join(
                    f"{label.split(' —', 1)[0]}: "
                    f"{normalised_sidebar_weights[SINGLE_PARAMETER_OPTIONS[label]['column']] * 100:.1f}%"
                    for label in multi_criterion_labels
                )
                st.caption(f"Normalised: {sidebar_weight_text}")

            top_n = st.select_slider(
                "Number of ranked products",
                options=[5, 10, 20],
                value=10,
                key="multi_top_n",
            )
            st.caption(
                "Only technical products with explicit values for every selected "
                "parameter are ranked. Surface and colour variants stay hidden in "
                "the main result and are available in product details."
            )
        elif benchmark_mode == "Reference-product comparison":
            st.markdown("#### Independent scoring weights")
            st.caption(
                "These weights score the comparable set independently. The selected "
                "reference product receives no bonus and may rank below a competitor."
            )
            score_weights = {
                "flow_rate": st.slider(
                    "Flow rate", 0, 10, 5, key="reference_weight_flow_rate"
                ),
                "installation_height": st.slider(
                    "Installation height",
                    0,
                    10,
                    5,
                    key="reference_weight_installation_height",
                ),
                "v4a": st.slider(
                    "V4A material", 0, 10, 5, key="reference_weight_v4a"
                ),
                "sales_price": st.slider(
                    "Sales price", 0, 10, 0, key="reference_weight_sales_price"
                ),
                "colours": st.slider(
                    "Number of colours", 0, 10, 0, key="reference_weight_colours"
                ),
            }
            top_n = st.select_slider(
                "Number of ranked competitors",
                options=[5, 10, 20],
                value=10,
                key="reference_top_n",
            )
            st.caption(
                "Comparable products missing an active scoring value are not ranked. "
                "The reference product remains visible with `Not rankable — missing data`."
            )
        else:
            st.header("Scoring weights")
            score_weights = {
                "flow_rate": st.slider("Flow rate", 0, 10, 5, key="weight_flow_rate"),
                "installation_height": st.slider(
                    "Installation height", 0, 10, 5, key="weight_installation_height"
                ),
                "v4a": st.slider("V4A material", 0, 10, 5, key="weight_v4a"),
                "sales_price": st.slider("Sales price", 0, 10, 0, key="weight_sales_price"),
                "colours": st.slider("Number of colours", 0, 10, 0, key="weight_colours"),
            }
            st.markdown("#### Missing-data policy")
            advanced_missing_data_label = st.radio(
                "Treatment of missing active ranking values",
                options=list(ADVANCED_MISSING_DATA_OPTIONS),
                index=0,
                key="advanced_missing_data_policy",
                help=(
                    "Require complete data excludes products missing any metric with "
                    "a weight above zero. Zero score keeps them and assigns zero points "
                    "to missing metrics. Proportional penalty scores available metrics "
                    "and multiplies the result by the share of active criteria present."
                ),
            )
            advanced_missing_data_policy = ADVANCED_MISSING_DATA_OPTIONS[
                advanced_missing_data_label
            ]
            if advanced_missing_data_policy == "require_complete":
                st.caption(
                    "Default and most conservative: products must have explicit values "
                    "for every criterion with a non-zero weight."
                )
            elif advanced_missing_data_policy == "allow_incomplete_zero_score":
                st.caption(
                    "Incomplete products remain visible, and every missing active metric "
                    "contributes zero points."
                )
            else:
                st.caption(
                    "Incomplete products are scored from available metrics and then "
                    "penalised by their unweighted data-completeness percentage."
                )
            advanced_display_limit = st.select_slider(
                "Rows shown in leaderboard",
                options=ADVANCED_DISPLAY_LIMIT_OPTIONS,
                value=100,
                help=(
                    "Only the leading rows are sent to the browser. The complete "
                    "filtered and scored result remains available in the Excel export."
                ),
            )

    flow_filter = flow_selection
    height_filter = height_selection

    filter_payload: dict[str, object] = {
        "drain_form": selected_drain_form or "all",
        "solution_types": solution_type_filter or ["all"],
        "include_incomplete_systems_and_components": include_incomplete,
        "manufacturers": manufacturer_filter or ["all"],
        "length_range_mm": list(length_filter) if length_filter is not None else None,
        "include_unverified_length": include_unverified_length,
        "primary_flow_rate_range_lps": list(flow_filter) if flow_filter is not None else None,
        "installation_height_range_mm": list(height_filter) if height_filter is not None else None,
        "numeric_filters": {
            column: list(selected_range) if selected_range is not None else None
            for column, selected_range in point_numeric_filters.items()
        },
        "attributes": {
            column: selected_values or ["all"]
            for column, selected_values in attribute_selections.items()
        },
    }

    filtered = filter_flat_input(
        master.flat,
        include_incomplete=include_incomplete,
        manufacturers=manufacturer_filter,
        flow_range=flow_filter,
        height_range=height_filter,
        attribute_filters=attribute_selections,
        drain_forms=None if selected_drain_form is None else [selected_drain_form],
        solution_types=solution_type_filter,
        numeric_filters=point_numeric_filters,
        length_range=length_filter,
        include_unverified_length=include_unverified_length,
    )

    render_active_mandatory_requirements(
        filter_payload,
        source_record_count=len(master.flat),
        filtered_record_count=len(filtered),
    )

    if filtered.empty:
        st.warning("No system matches the selected mandatory filters.")
        st.stop()

    if benchmark_mode == "Single-parameter ranking":
        render_single_parameter_ranking(
            master,
            filtered,
            criterion_label=criterion_label,
            top_n=top_n,
            filter_payload=filter_payload,
            source_workbook_count=master.source_count,
        )
        return

    if benchmark_mode == "Multi-parameter ranking":
        if len(multi_criterion_labels) < 2:
            st.warning("Select at least two ranking parameters in the sidebar.")
            st.stop()
        render_multi_parameter_ranking(
            master,
            filtered,
            criterion_labels=multi_criterion_labels,
            criterion_weights=multi_criterion_weights,
            top_n=top_n,
            filter_payload=filter_payload,
            source_workbook_count=master.source_count,
        )
        return

    if benchmark_mode == "Reference-product comparison":
        render_reference_product_comparison(
            master,
            filtered,
            score_weights=score_weights,
            top_n=top_n,
            source_workbook_count=master.source_count,
        )
        return

    if sum(float(value) for value in score_weights.values()) <= 0:
        st.warning("Set at least one advanced-scoring weight above zero.")
        st.stop()

    scored, grouped_members = score_advanced_product_groups(
        filtered,
        score_weights,
        missing_data_policy=advanced_missing_data_policy,
    )
    total_technical_groups = (
        int(grouped_members["presentation_group_key"].nunique(dropna=True))
        if not grouped_members.empty and "presentation_group_key" in grouped_members.columns
        else len(scored)
    )
    hidden_variant_rows = max(len(filtered) - total_technical_groups, 0)
    excluded_incomplete_groups = max(total_technical_groups - len(scored), 0)

    if scored.empty:
        st.warning(
            "No technical product has sufficient explicit data for the active "
            "weights and selected missing-data policy."
        )
        st.stop()

    scored = (
        scored.sort_values("Final_Score_%", ascending=False, kind="stable")
        .reset_index(drop=True)
    )
    scored.insert(0, "Rank", range(1, len(scored) + 1))

    leaderboard_columns = available_columns(scored, ADVANCED_LEADERBOARD_COLUMNS)
    leaderboard = scored.loc[:, leaderboard_columns].head(advanced_display_limit).copy()
    policy_label = next(
        label
        for label, value in ADVANCED_MISSING_DATA_OPTIONS.items()
        if value == advanced_missing_data_policy
    )
    mean_completeness = (
        float(pd.to_numeric(scored["Data_Completeness_%"], errors="coerce").mean())
        if "Data_Completeness_%" in scored.columns
        else 100.0
    )

    st.subheader("Advanced weighted technical-product leaderboard")
    metric_columns = st.columns(4)
    metric_columns[0].metric("Technical groups before policy", f"{total_technical_groups:,}".replace(",", " "))
    metric_columns[1].metric("Ranked groups", f"{len(scored):,}".replace(",", " "))
    metric_columns[2].metric("Excluded for missing data", f"{excluded_incomplete_groups:,}".replace(",", " "))
    metric_columns[3].metric("Mean data completeness", f"{mean_completeness:.1f}%")
    st.caption(
        (
            f"Missing-data policy: {policy_label}. {len(filtered):,} filtered source "
            f"records represent {total_technical_groups:,} technical product groups; "
            f"{hidden_variant_rows:,} article or finish variants are hidden from the "
            f"main leaderboard. Showing the leading {len(leaderboard):,} ranked groups "
            "in the browser. The complete grouped leaderboard and every exact source "
            "variant are available in the Excel export. Group price is the lowest "
            "observed member price when currency is unambiguous; colour count prefers "
            "explicit data and otherwise falls back to grouped finishes."
        ).replace(",", " ")
    )

    advanced_column_config = {
        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
        "Final_Score_%": st.column_config.NumberColumn("Final Score %", format="%.1f %%"),
        "Data_Completeness_%": st.column_config.ProgressColumn(
            "Data completeness", min_value=0.0, max_value=100.0, format="%.1f %%"
        ),
        "Weighted_Data_Completeness_%": st.column_config.NumberColumn(
            "Weighted completeness %", format="%.1f %%"
        ),
        "Available_Criteria": st.column_config.NumberColumn(
            "Available criteria", format="%d"
        ),
        "Required_Criteria": st.column_config.NumberColumn(
            "Active criteria", format="%d"
        ),
        "Missing_Ranking_Fields": st.column_config.TextColumn("Missing ranking fields"),
        "Score_Before_Completeness_Penalty_%": st.column_config.NumberColumn(
            "Score before completeness penalty", format="%.1f %%"
        ),
        "Completeness_Penalty_Factor": st.column_config.NumberColumn(
            "Completeness penalty factor", format="%.2f"
        ),
        "manufacturer_name": st.column_config.TextColumn("Manufacturer"),
        "product_family_name": st.column_config.TextColumn("Product family"),
        "model_name": st.column_config.TextColumn("Technical model"),
        "drain_type_label": st.column_config.TextColumn("Drain form"),
        "mapped_solution_type": st.column_config.TextColumn("Solution type"),
        "drain_element_length_mm": st.column_config.NumberColumn(
            "Drain element length [mm]", format="%.0f"
        ),
        "nominal_length_mm": st.column_config.NumberColumn(
            "Overall product length [mm]", format="%.0f"
        ),
        "point_top_shape": st.column_config.TextColumn("Point top shape"),
        "point_top_size": st.column_config.TextColumn("Nominal top size"),
        "point_grate_size": st.column_config.TextColumn("Grate size"),
        "point_cover_size": st.column_config.TextColumn("Cover size"),
        "point_body_size": st.column_config.TextColumn("Body size"),
        "drain_position": st.column_config.TextColumn("Drain position"),
        "outlet_dn_default": st.column_config.TextColumn("Outlet DN"),
        "outlet_orientation_default": st.column_config.TextColumn("Outlet orientation"),
        "flow_rate_primary_lps": st.column_config.NumberColumn(
            "Primary flow rate [l/s]", format="%.2f"
        ),
        "height_adj_min_mm": st.column_config.NumberColumn(
            "Minimum installation height [mm]", format="%.0f"
        ),
        "material_v4a": st.column_config.TextColumn("V4A"),
        "sales_price_value": st.column_config.NumberColumn(
            "Lowest observed variant price", format="%.2f"
        ),
        "sales_price_currency": st.column_config.TextColumn("Currency"),
        "sales_price_group_basis": st.column_config.TextColumn("Price basis"),
        "colours_count": st.column_config.NumberColumn(
            "Colour/finish options", format="%.0f"
        ),
        "colours_count_source": st.column_config.TextColumn("Colour-count basis"),
        "Score_Flow_Rate_%": st.column_config.NumberColumn("Flow score", format="%.1f %%"),
        "Score_Installation_Height_%": st.column_config.NumberColumn(
            "Height score", format="%.1f %%"
        ),
        "Score_V4A_%": st.column_config.NumberColumn("V4A score", format="%.1f %%"),
        "Score_Sales_Price_%": st.column_config.NumberColumn(
            "Price score", format="%.1f %%"
        ),
        "Score_Colours_%": st.column_config.NumberColumn(
            "Colour score", format="%.1f %%"
        ),
        "group_member_count": st.column_config.NumberColumn(
            "Hidden source rows", format="%d"
        ),
        "finish_variant_count": st.column_config.NumberColumn(
            "Finish variants", format="%d"
        ),
        "article_variant_count": st.column_config.NumberColumn(
            "Article/configuration variants", format="%d"
        ),
        "available_finishes": st.column_config.TextColumn("Available finishes"),
        "product_link": st.column_config.LinkColumn("Product", display_text="Open"),
    }
    st.dataframe(
        leaderboard,
        use_container_width=True,
        hide_index=True,
        column_config={
            column: config
            for column, config in advanced_column_config.items()
            if column in leaderboard.columns
        },
    )

    export_data = advanced_scoring_workbook(
        scored,
        grouped_members,
        tuple(sorted((key, float(value)) for key, value in score_weights.items())),
        advanced_missing_data_policy,
        json.dumps(filter_payload, sort_keys=True, ensure_ascii=False),
    )
    st.download_button(
        "Download grouped advanced scoring audit (.xlsx)",
        data=export_data,
        file_name="shower_drainage_advanced_grouped_scoring.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    render_ranked_group_details(
        master,
        scored.head(advanced_display_limit),
        grouped_members,
        key_prefix="advanced",
        score_columns=(
            "Score_Flow_Rate_%",
            "Score_Installation_Height_%",
            "Score_V4A_%",
            "Score_Sales_Price_%",
            "Score_Colours_%",
        ),
        score_column_labels={
            "Score_Flow_Rate_%": "Flow score",
            "Score_Installation_Height_%": "Height score",
            "Score_V4A_%": "V4A score",
            "Score_Sales_Price_%": "Price score",
            "Score_Colours_%": "Colour score",
        },
        overall_score_column="Final_Score_%",
        overall_score_label="Final score",
    )


if __name__ == "__main__":
    main()
