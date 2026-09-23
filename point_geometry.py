"""Canonical point-drain parameter registry used by the data layer and UI.

The registry contains only schema mappings and display metadata.  It does not
infer manufacturer values.  Any normalised application value must come from an
explicit source field with equivalent semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ParameterKind = Literal["text", "numeric"]


@dataclass(frozen=True)
class PointDrainParameter:
    """Metadata for one explicit point-drain parameter."""

    field: str
    label: str
    section: str
    kind: ParameterKind
    unit: str | None = None
    filterable: bool = False
    search: bool = True
    show_in_detail: bool = True

    @property
    def display_label(self) -> str:
        if self.unit:
            return f"{self.label} [{self.unit}]"
        return self.label


# Source-native and canonical fields that can legitimately describe point
# drainage.  The application may expose only fields that are actually populated
# in the active selection.  No field is populated from product-family wording or
# from unrelated generic dimensions.
POINT_DRAIN_PARAMETER_REGISTRY: tuple[PointDrainParameter, ...] = (
    PointDrainParameter(
        "point_top_shape", "Point top shape", "Top geometry", "text", filterable=True
    ),
    PointDrainParameter(
        "point_top_nominal_length_mm",
        "Nominal top length",
        "Top geometry",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "point_top_nominal_width_mm",
        "Nominal top width",
        "Top geometry",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "point_top_nominal_diameter_mm",
        "Nominal top diameter",
        "Top geometry",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "visible_grate_length_mm",
        "Visible grate length",
        "Visible grate",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "visible_grate_width_mm",
        "Visible grate width",
        "Visible grate",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "visible_grate_diameter_mm",
        "Visible grate diameter",
        "Visible grate",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "grate_diameter_mm",
        "Grate diameter",
        "Visible grate",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "grid_size_mm", "Grid size", "Visible grate", "text", show_in_detail=True
    ),
    PointDrainParameter(
        "included_grid_size_mm",
        "Included grid size",
        "Visible grate",
        "text",
        show_in_detail=True,
    ),
    PointDrainParameter(
        "visible_cover_length_mm",
        "Visible cover length",
        "Visible cover",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "visible_cover_width_mm",
        "Visible cover width",
        "Visible cover",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "cover_diameter_mm",
        "Cover diameter",
        "Visible cover",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "overall_body_diameter_mm",
        "Overall body diameter",
        "Body / frame",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "body_diameter_mm",
        "Body diameter",
        "Body / frame",
        "numeric",
        "mm",
        filterable=True,
    ),
    PointDrainParameter(
        "fixed_frame_size_mm", "Fixed frame size", "Body / frame", "text"
    ),
    PointDrainParameter(
        "tray_hole_diameter_mm",
        "Tray hole diameter",
        "Body / frame",
        "numeric",
        "mm",
    ),
    PointDrainParameter(
        "connection_side", "Connection side", "Body / frame", "text", filterable=True
    ),
    PointDrainParameter(
        "drain_position", "Drain position", "Installation", "text", filterable=True
    ),
    PointDrainParameter(
        "drain_location", "Drain location", "Installation", "text", filterable=True
    ),
    PointDrainParameter(
        "mounting_type", "Mounting type", "Installation", "text", filterable=True
    ),
    PointDrainParameter(
        "mounting_adjustment_min_mm",
        "Mounting adjustment minimum",
        "Installation",
        "numeric",
        "mm",
    ),
    PointDrainParameter(
        "mounting_adjustment_max_mm",
        "Mounting adjustment maximum",
        "Installation",
        "numeric",
        "mm",
    ),
    PointDrainParameter(
        "covering_thickness_min_mm",
        "Covering thickness minimum",
        "Installation",
        "numeric",
        "mm",
    ),
    PointDrainParameter(
        "covering_thickness_max_mm",
        "Covering thickness maximum",
        "Installation",
        "numeric",
        "mm",
    ),
    PointDrainParameter(
        "lateral_adjustment_mm",
        "Lateral adjustment",
        "Installation",
        "numeric",
        "mm",
    ),
    PointDrainParameter(
        "water_seal_mm",
        "Water seal",
        "Hydraulics",
        "numeric",
        "mm",
        filterable=True,
        show_in_detail=False,
    ),
    PointDrainParameter(
        "outlet_angle_min_deg",
        "Outlet angle minimum",
        "Outlet",
        "numeric",
        "°",
    ),
    PointDrainParameter(
        "outlet_angle_max_deg",
        "Outlet angle maximum",
        "Outlet",
        "numeric",
        "°",
    ),
    PointDrainParameter(
        "outlet_dn_default",
        "Outlet DN",
        "Outlet",
        "text",
        filterable=True,
        show_in_detail=False,
    ),
    PointDrainParameter(
        "outlet_orientation_default",
        "Outlet orientation",
        "Outlet",
        "text",
        filterable=True,
        show_in_detail=False,
    ),
    PointDrainParameter(
        "outlet_size_raw", "Outlet size (declared)", "Outlet", "text", filterable=True
    ),
    PointDrainParameter(
        "outlet_size_options", "Outlet size options", "Outlet", "text"
    ),
    PointDrainParameter("outlet_count", "Outlet count", "Outlet", "numeric"),
)


POINT_DRAIN_PARAMETER_BY_FIELD = {
    parameter.field: parameter for parameter in POINT_DRAIN_PARAMETER_REGISTRY
}

POINT_DRAIN_TEXT_FILTERS = {
    parameter.field: parameter.display_label
    for parameter in POINT_DRAIN_PARAMETER_REGISTRY
    if parameter.filterable and parameter.kind == "text"
}

POINT_DRAIN_NUMERIC_FILTERS = {
    parameter.field: parameter.display_label
    for parameter in POINT_DRAIN_PARAMETER_REGISTRY
    if parameter.filterable and parameter.kind == "numeric"
}

POINT_DRAIN_OBSERVATION_FIELDS = frozenset(POINT_DRAIN_PARAMETER_BY_FIELD)
POINT_DRAIN_SEARCH_FIELDS = tuple(
    parameter.field for parameter in POINT_DRAIN_PARAMETER_REGISTRY if parameter.search
)
POINT_DRAIN_DETAIL_FIELDS = tuple(
    parameter.field for parameter in POINT_DRAIN_PARAMETER_REGISTRY if parameter.show_in_detail
)
POINT_DRAIN_TEXT_GROUP_FIELDS = tuple(
    parameter.field
    for parameter in POINT_DRAIN_PARAMETER_REGISTRY
    if parameter.kind == "text"
)
POINT_DRAIN_NUMERIC_GROUP_FIELDS = tuple(
    parameter.field
    for parameter in POINT_DRAIN_PARAMETER_REGISTRY
    if parameter.kind == "numeric"
)

# Normalised application fields.  These are populated only from explicit,
# semantically equivalent source fields and remain blank if explicit values
# disagree.  They make manufacturer-specific schemas comparable without
# changing the source master workbooks.
POINT_DRAIN_CANONICAL_SOURCE_FIELDS: dict[str, tuple[str, ...]] = {
    "point_grate_length_mm": ("visible_grate_length_mm",),
    "point_grate_width_mm": ("visible_grate_width_mm",),
    "point_grate_diameter_mm": (
        "visible_grate_diameter_mm",
        "grate_diameter_mm",
    ),
    "point_cover_length_mm": ("visible_cover_length_mm",),
    "point_cover_width_mm": ("visible_cover_width_mm",),
    "point_cover_diameter_mm": ("cover_diameter_mm",),
    "point_body_diameter_mm": (
        "overall_body_diameter_mm",
        "body_diameter_mm",
    ),
}

POINT_DRAIN_CANONICAL_NUMERIC_FIELDS = tuple(POINT_DRAIN_CANONICAL_SOURCE_FIELDS)
POINT_DRAIN_COMPOSITE_DISPLAY_FIELDS = (
    "point_top_size",
    "point_grate_size",
    "point_cover_size",
    "point_body_size",
)
