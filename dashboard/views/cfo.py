"""Page 3 - Cash impact (CFO). SYNTHETIC data."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data
from dashboard.ui import ACCENT, ALERT, MUTED, highlight_bar, money, title


def render(con, f: data.Filters) -> None:
    st.header("Cash impact")
    st.caption(
        "For the CFO. Date filter = deduction date. Forecast covers all reasons. All data is synthetic."
    )
    cash = data.cash_kpis(con, f)
    grid = data.recoverable_grid(con, f)
    base = grid[
        (grid["window_days"] == data.CFO_WINDOW_DAYS) & (grid["scenario"] == data.CFO_SCENARIO)
    ]
    base_amount = float(base["recoverable_amount"].iloc[0]) if len(base) else 0.0
    cols = st.columns(3)
    cols[0].metric("Cash tied up in open deductions", money(cash["cash_tied_up"]))
    cols[1].metric(
        f"Recoverable ({data.CFO_WINDOW_DAYS}-day window, {data.CFO_SCENARIO} case)",
        money(base_amount),
    )
    cols[2].metric(
        "Deducted, net of recoveries", money(cash["deducted_amount"] - cash["recovered_amount"])
    )

    if not grid.empty:
        window = grid[grid["window_days"] == data.CFO_WINDOW_DAYS].set_index("scenario")[
            "recoverable_amount"
        ]
        chart = (
            alt.Chart(grid)
            .mark_bar()
            .encode(
                x=alt.X("window_days:O", title="Dispute window (days)"),
                xOffset=alt.XOffset("scenario:N", sort=["low", "base", "high"]),
                y=alt.Y("recoverable_amount:Q", axis=alt.Axis(format="$~s"), title=None),
                color=alt.Color(
                    "scenario:N",
                    sort=["low", "base", "high"],
                    scale=alt.Scale(domain=["low", "base", "high"], range=[MUTED, ACCENT, ALERT]),
                    legend=alt.Legend(title="Scenario"),
                ),
                tooltip=[
                    "window_days",
                    "scenario",
                    alt.Tooltip("recoverable_amount:Q", format="$,.0f"),
                ],
            )
            .properties(
                title=title(
                    f"Base case: {money(window.get('base'))} is recoverable from never-disputed deductions within "
                    f"{data.CFO_WINDOW_DAYS} days ({money(window.get('low'))} to {money(window.get('high'))} across scenarios)"
                ),
                height=300,
            )
        )
        st.altair_chart(chart, width="stretch")

    by_retailer = data.open_balance_by_retailer(con, f)
    if not by_retailer.empty:
        top = by_retailer.iloc[0]
        st.altair_chart(
            highlight_bar(
                by_retailer.head(10),
                "open_balance",
                "retailer_name",
                "$~s",
                f"{top['retailer_name']} holds the largest open balance: {money(top['open_balance'])} of cash tied up",
                alert_label=top["retailer_name"],
            ),
            width="stretch",
        )

    history = data.deduction_history(con, f)
    try:
        forward = data.forward_forecast(f)
    except FileNotFoundError:
        st.info("Forecast results not found. Run `make forecast`.")
        return
    if history.empty or forward.empty:
        st.info("No forecast for these filters.")
        return
    months = list(forward["month"])
    last_year = data.same_months_last_year(con, f, months)
    forecast_total = float(forward["holt_winters"].sum())
    hist = history.assign(series="Actual", value=history["amount"])[["month", "series", "value"]]
    fc = forward.assign(series="Holt-Winters forecast", value=forward["holt_winters"])[
        ["month", "series", "value"]
    ]
    bridge = pd.concat([hist.tail(1).assign(series="Holt-Winters forecast"), fc])
    base_chart = alt.Chart().encode(x=alt.X("month:T", title=None))
    line_actual = base_chart.mark_line(color=MUTED).encode(
        y=alt.Y("value:Q", axis=alt.Axis(format="$~s"), title=None)
    )
    line_fc = base_chart.mark_line(color=ACCENT).encode(y="value:Q")
    band = (
        alt.Chart(forward)
        .mark_area(opacity=0.2, color=ACCENT)
        .encode(x="month:T", y="hw_p10:Q", y2="hw_p90:Q")
    )
    layered = alt.layer(
        line_actual.properties(data=hist), line_fc.properties(data=bridge), band
    ).properties(
        title=title(
            f"Deductions are forecast at {money(forecast_total)} over the next 3 months "
            f"(80% band {money(forward['hw_p10'].sum())} to {money(forward['hw_p90'].sum())}), "
            f"versus {money(last_year)} in the same months last year"
        ),
        height=320,
    )
    st.altair_chart(layered, width="stretch")
    st.caption(
        "Band = 10th to 90th percentile of pooled backtest errors, not a model-based interval."
    )
