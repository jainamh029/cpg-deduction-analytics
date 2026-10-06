"""Page 1 - Retailer performance (VP Sales). SYNTHETIC data."""

from __future__ import annotations

import altair as alt
import streamlit as st

from dashboard import data
from dashboard.ui import highlight_bar, money, pct, title


def render(con, f: data.Filters) -> None:
    st.header("Retailer performance")
    st.caption("For the VP Sales. Date filter = invoice date. All data is synthetic.")
    kpi = data.sales_kpis(con, f)
    cols = st.columns(4)
    cols[0].metric("Gross invoiced", money(kpi["gross_amount"]))
    cols[1].metric("Deduction rate", pct(kpi["deduction_rate"]))
    cols[2].metric("Net revenue after deductions", money(kpi["net_revenue"]))
    cols[3].metric("Recovery rate", pct(kpi["recovery_rate"]))
    st.caption(
        "Invoices from the last 4 months before the as-of date are incomplete (deductions still arriving), "
        "so the deduction rate above is understated and the trend below excludes those months."
    )

    score = data.retailer_scorecard(con, f)
    if score.empty:
        st.info("No invoices match these filters.")
        return
    top = score.iloc[0]
    st.altair_chart(
        highlight_bar(
            score,
            "deduction_rate",
            "retailer_name",
            ".1%",
            f"{top['retailer_name']} has the highest deduction rate at {pct(top['deduction_rate'])}, "
            f"against {pct(kpi['deduction_rate'])} for the selected portfolio",
            alert_label=top["retailer_name"],
        ),
        width="stretch",
    )

    monthly = data.monthly_rate_by_retailer(con, f)
    halves = data.trend_halves(con, f)
    if len(halves) == 2:
        first, second = halves["deduction_rate"]
        word = (
            "rose"
            if second - first > 0.0005
            else "fell"
            if first - second > 0.0005
            else "held steady"
        )
        trend_title = (
            f"Portfolio deduction rate {word}: {pct(first)} in the first half of the period vs "
            f"{pct(second)} in the second (mature months only)"
        )
    else:
        trend_title = "Not enough mature months in this range to compare halves of the period"
    if not monthly.empty:
        lines = (
            alt.Chart(monthly)
            .mark_line(point=False)
            .encode(
                x=alt.X("invoice_month:T", title=None),
                y=alt.Y("deduction_rate:Q", axis=alt.Axis(format=".0%"), title=None),
                color=alt.Color("retailer_name:N", legend=alt.Legend(title=None)),
                tooltip=[
                    "retailer_name",
                    "invoice_month",
                    alt.Tooltip("deduction_rate:Q", format=".1%"),
                ],
            )
            .properties(title=title(trend_title), height=320)
        )
        st.altair_chart(lines, width="stretch")

    late = score.dropna(subset=["days_past_due"]).sort_values("days_past_due", ascending=False)
    if not late.empty:
        slow = late.iloc[0]
        st.altair_chart(
            highlight_bar(
                late,
                "days_past_due",
                "retailer_name",
                ".0f",
                f"{slow['retailer_name']} pays furthest past due: {slow['days_past_due']:.0f} days after the due "
                f"date on average, versus a median of {late['days_past_due'].median():.0f} days across retailers",
                alert_label=slow["retailer_name"],
            ),
            width="stretch",
        )

    st.subheader("Retailer scorecard")
    table = score.drop(columns="retailer_id").rename(columns={"retailer_name": "Retailer"})
    table["deduction_rate"] = table["deduction_rate"].map(pct)
    table["recovery_rate"] = table["recovery_rate"].map(pct)
    table["gross_amount"] = table["gross_amount"].map(money)
    table["deduction_amount"] = table["deduction_amount"].map(money)
    table["payment_lag_days"] = table["payment_lag_days"].round(1)
    table["days_past_due"] = table["days_past_due"].round(1)
    st.dataframe(table, hide_index=True)
