"""State-safe controls for the upstream-to-downstream mandatory-filter pipeline."""

from __future__ import annotations

import math
from typing import Callable

import streamlit as st


def text_filter(
    label: str,
    options: list[str],
    *,
    key: str,
    format_func: Callable[[str], str] = str,
) -> list[str] | None:
    """Retain valid choices and keep an unrestricted selection unrestricted.

    An intentionally empty selection means no matches. If an upstream change
    invalidates every previously selected choice, reset to all available choices
    and explain the reset. Widget state is reconciled before creating the widget.
    """

    options_key = f"_mandatory_options_{key}"
    previous_options = st.session_state.get(options_key, [])
    previous = st.session_state.get(key)
    if previous is None or not previous_options:
        selected = list(options)
    elif set(previous) == set(previous_options):
        selected = list(options)
    else:
        selected = [value for value in previous if value in options]
        if previous and not selected and options:
            selected = list(options)
        if selected != list(previous) and options:
            st.sidebar.caption(f"{label}: selection updated to the available options.")
    st.session_state[options_key] = list(options)
    st.session_state[key] = selected
    if not options:
        st.sidebar.caption(f"{label}: no values are available for the current selection.")
        return None
    selected = st.sidebar.multiselect(
        label, options=options, key=key, format_func=format_func
    )
    return None if set(selected) == set(options) else list(selected)


def range_filter(
    label: str,
    bounds: tuple[float, float] | None,
    *,
    key: str,
    decimals: int = 1,
    integer: bool = False,
    help: str | None = None,
) -> tuple[float, float] | None:
    """Use a stable decimal grid and reconcile a range when its scope changes."""

    bounds_key = f"_mandatory_bounds_{key}"
    if bounds is None:
        st.session_state.pop(key, None)
        st.session_state.pop(bounds_key, None)
        st.sidebar.caption(f"{label}: no supported numeric values are available.")
        return None
    minimum, maximum = map(float, bounds)
    if minimum == maximum:
        st.session_state[key] = (minimum, maximum)
        st.session_state[bounds_key] = (minimum, maximum)
        st.sidebar.caption(f"{label}: the only available value is {minimum:g}.")
        return minimum, maximum

    scale = 10 ** decimals
    if integer:
        lower, upper, step = math.floor(minimum), math.ceil(maximum), 1
        display_format = "%d"
    else:
        lower = round(math.floor(minimum * scale) / scale, decimals)
        upper = round(math.ceil(maximum * scale) / scale, decimals)
        step = 1.0 / scale
        display_format = f"%.{decimals}f"
    current_bounds = (lower, upper)
    previous_bounds = st.session_state.get(bounds_key)
    previous = st.session_state.get(key)
    was_full = (
        previous is not None
        and previous_bounds is not None
        and all(math.isclose(a, b) for a, b in zip(previous, previous_bounds))
    )
    if previous is None or previous_bounds is None or was_full:
        selection = current_bounds
    else:
        start, end = max(lower, previous[0]), min(upper, previous[1])
        selection = (start, end) if start <= end else current_bounds
        if selection != tuple(previous):
            st.sidebar.caption(f"{label}: selection updated to the available range.")
    if integer:
        selection = tuple(int(value) for value in selection)
    else:
        selection = tuple(float(value) for value in selection)
    st.session_state[key] = selection
    st.session_state[bounds_key] = current_bounds
    # value=None lets Streamlit use the tuple in session_state as a range without
    # introducing a second, conflicting default or changing identity on every drag.
    return st.sidebar.slider(
        label,
        min_value=lower,
        max_value=upper,
        value=None,
        step=step,
        format=display_format,
        key=key,
        help=help,
    )
