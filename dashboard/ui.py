"""Small presentation helpers shared by the dashboard pages (SYNTHETIC data)."""

from __future__ import annotations

import textwrap

import altair as alt
import pandas as pd

ACCENT = "#2563eb"
MUTED = "#94a3b8"
ALERT = "#d9480f"


def money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    sign, value = ("-" if value < 0 else ""), abs(float(value))
    if value >= 1e6:
        return f"{sign}${value / 1e6:.1f}M"
    if value >= 1e3:
        return f"{sign}${value / 1e3:.0f}K"
    return f"{sign}${value:.0f}"


def pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:.{digits}%}"


def title(text: str) -> alt.TitleParams:
    """Chart title that states the takeaway, wrapped so it never overflows the chart."""
    return alt.TitleParams(text=textwrap.wrap(text, 75), anchor="start", fontSize=14)


def highlight_bar(df: pd.DataFrame, value: str, label: str, fmt: str, text: str, alert_label=None):
    """Horizontal bars sorted by value; one bar (alert_label) highlighted."""
    color = alt.condition(alt.datum[label] == alert_label, alt.value(ALERT), alt.value(MUTED))
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(f"{value}:Q", axis=alt.Axis(format=fmt), title=None),
            y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelOverlap=False)),
            color=color,
            tooltip=[label, alt.Tooltip(f"{value}:Q", format=fmt)],
        )
        .properties(title=title(text), height=max(120, 24 * len(df)))
    )
