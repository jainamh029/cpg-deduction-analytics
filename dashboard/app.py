"""Streamlit dashboard for the SYNTHETIC CPG deduction analytics project.

Run: streamlit run dashboard/app.py   (after `make build forecast`)
Reads only marts.*, metrics.* and forecast/results/. Page can be preselected with ?page=sales|ops|cfo.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from dashboard import data
from dashboard.views import cfo, ops, sales

PAGES = {
    "sales": ("VP Sales: retailer performance", sales),
    "ops": ("AR manager: deduction operations", ops),
    "cfo": ("CFO: cash impact", cfo),
}


@st.cache_resource
def connection():
    return data.connect()


def sidebar_filters(con) -> data.Filters | None:
    names = data.retailers(con)
    lo, hi = data.invoice_date_range(con)
    chosen = st.sidebar.multiselect(
        "Retailers", list(names["retailer_name"]), default=list(names["retailer_name"])
    )
    span = st.sidebar.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
    reasons = st.sidebar.multiselect(
        "Reason codes", data.reason_codes(con), default=data.reason_codes(con)
    )
    st.sidebar.caption(
        "Date range filters invoice date on the sales page and deduction date on the other pages."
    )
    if not chosen or not reasons or len(span) != 2:
        st.warning("Choose at least one retailer, one reason and a full date range.")
        return None
    ids = tuple(int(i) for i in names.loc[names["retailer_name"].isin(chosen), "retailer_id"])
    start, end = span
    return data.Filters(
        ids,
        date(start.year, start.month, start.day),
        date(end.year, end.month, end.day),
        tuple(reasons),
    )


def main() -> None:
    st.set_page_config(page_title="CPG deduction analytics (synthetic data)", layout="wide")
    st.sidebar.title("Deduction analytics")
    st.sidebar.warning("All data is SYNTHETIC. Not Confido's data or schema.")
    keys = list(PAGES)
    default = st.query_params.get("page", "sales")
    index = keys.index(default) if default in keys else 0
    key = st.sidebar.radio("Page", keys, index=index, format_func=lambda k: PAGES[k][0])
    con = connection()
    filters = sidebar_filters(con)
    if filters is not None:
        PAGES[key][1].render(con, filters)


main()
