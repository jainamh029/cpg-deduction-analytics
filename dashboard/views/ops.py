"""Page 2 - Deduction operations (AR manager). SYNTHETIC data."""

from __future__ import annotations

import altair as alt
import streamlit as st

from dashboard import data
from dashboard.ui import ACCENT, MUTED, money, pct, title


def render(con, f: data.Filters) -> None:
    st.header("Deduction operations")
    st.caption("For the AR manager. Date filter = deduction date. All data is synthetic.")
    kpi = data.ops_kpis(con, f)
    cols = st.columns(4)
    cols[0].metric("Open deduction balance", money(kpi["open_balance"]))
    cols[1].metric("Open items", f"{int(kpi['open_items']):,}")
    cols[2].metric("Dispute win rate", pct(kpi["win_rate"]))
    cols[3].metric(
        "Median days to resolve",
        "n/a"
        if kpi["median_days_to_resolve"] != kpi["median_days_to_resolve"]
        else f"{kpi['median_days_to_resolve']:.0f}",
    )

    aging = data.aging_by_reason(con, f)
    if aging.empty:
        st.info("No open deductions match these filters.")
    else:
        total = aging["open_balance"].sum()
        oldest = aging["aging_bucket"].max()
        old_amount = aging.loc[aging["aging_bucket"] == oldest, "open_balance"].sum()
        chart = (
            alt.Chart(aging)
            .mark_bar()
            .encode(
                x=alt.X(
                    "aging_bucket:N",
                    title="Days since deduction",
                    sort=sorted(aging["aging_bucket"].unique()),
                ),
                y=alt.Y("open_balance:Q", axis=alt.Axis(format="$~s"), title=None),
                color=alt.Color("reason_code:N", legend=alt.Legend(title="Reason")),
                tooltip=[
                    "aging_bucket",
                    "reason_code",
                    alt.Tooltip("open_balance:Q", format="$,.0f"),
                ],
            )
            .properties(
                title=title(
                    f"{money(old_amount)} of the {money(total)} open balance sits in the oldest age bucket ({oldest} days)"
                ),
                height=300,
            )
        )
        st.altair_chart(chart, width="stretch")

    mix = data.reason_mix(con, f).dropna(subset=["win_rate"])
    if not mix.empty:
        gap = (
            mix.assign(gap=mix["win_rate"] - mix["dispute_rate"])
            .sort_values("gap", ascending=False)
            .iloc[0]
        )
        long = mix.melt("reason_code", ["dispute_rate", "win_rate"], "measure", "rate")
        chart = (
            alt.Chart(long)
            .mark_bar()
            .encode(
                x=alt.X("reason_code:N", title=None, sort=list(mix["reason_code"])),
                xOffset="measure:N",
                y=alt.Y("rate:Q", axis=alt.Axis(format="%"), title=None),
                color=alt.Color(
                    "measure:N",
                    scale=alt.Scale(domain=["dispute_rate", "win_rate"], range=[MUTED, ACCENT]),
                    legend=alt.Legend(title=None),
                ),
                tooltip=["reason_code", "measure", alt.Tooltip("rate:Q", format=".1%")],
            )
            .properties(
                title=title(
                    f"{str(gap['reason_code']).replace('_', ' ').capitalize()} deductions win {pct(gap['win_rate'], 0)} of disputes, yet only "
                    f"{pct(gap['dispute_rate'], 0)} of their dollars are disputed"
                ),
                height=300,
            )
        )
        st.altair_chart(chart, width="stretch")

    cohorts = data.filing_cohorts(con, f).dropna(subset=["win_rate"])
    if len(cohorts) >= 2:
        fast, slow = cohorts.iloc[0], cohorts.iloc[-1]
        chart = (
            alt.Chart(cohorts)
            .mark_bar(color=ACCENT)
            .encode(
                x=alt.X("filing_lag_bucket:N", title="Days from deduction to filing"),
                y=alt.Y("win_rate:Q", axis=alt.Axis(format="%"), title=None),
                tooltip=["filing_lag_bucket", "disputes", alt.Tooltip("win_rate:Q", format=".1%")],
            )
            .properties(
                title=title(
                    f"Disputes filed {fast['filing_lag_bucket']} days after the deduction win {pct(fast['win_rate'], 0)}; "
                    f"those filed {slow['filing_lag_bucket']} days after win {pct(slow['win_rate'], 0)}"
                ),
                height=260,
            )
        )
        st.altair_chart(chart, width="stretch")

    st.subheader(
        f"Worklist: top {data.WORKLIST_SIZE} open, never-disputed deductions by expected recovery"
    )
    work = data.worklist(con, f)
    if work.empty:
        st.info("Nothing to work with these filters.")
    else:
        table = work.rename(
            columns={
                "deduction_id": "Deduction",
                "retailer_name": "Retailer",
                "reason_code": "Reason",
                "deduction_date": "Deducted",
                "age_days": "Age (days)",
                "aging_bucket": "Bucket",
                "amount": "Amount",
                "expected_recovery": "Expected recovery",
            }
        )
        table["Amount"] = table["Amount"].map(money)
        table["Expected recovery"] = table["Expected recovery"].map(money)
        st.dataframe(table, hide_index=True)
