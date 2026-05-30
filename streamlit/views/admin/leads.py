"""Admin — Leads page."""
from __future__ import annotations

from typing import Any

import streamlit as st

from utils import _format_dt, _get_json, _patch_json

_STATUS_OPTIONS = ["new", "contacted", "qualified", "closed"]
_PAGE_SIZES = [20, 50, 100]


def render(backend_url: str, token: str) -> None:
    st.title("Leads")
    st.caption("Visitor contacts captured by the AI assistant.")

    filter_col, _, limit_col, refresh_col = st.columns([2, 2, 1, 1])
    with filter_col:
        filter_status = st.selectbox(
            "Filter",
            ["all"] + _STATUS_OPTIONS,
            format_func=lambda x: "All statuses" if x == "all" else x.capitalize(),
            key="leads_filter",
            label_visibility="collapsed",
        )
    with limit_col:
        page_size = st.selectbox(
            "Show", _PAGE_SIZES, index=0, label_visibility="collapsed", key="leads_page_size"
        )
    with refresh_col:
        if st.button("Refresh", use_container_width=True):
            st.session_state.pop("leads_data", None)

    if "leads_data" not in st.session_state:
        with st.spinner("Loading leads..."):
            data = _get_json(f"{backend_url}/leads", token)
            st.session_state["leads_data"] = data or []

    leads: list[dict[str, Any]] = st.session_state.get("leads_data", [])

    if not leads:
        st.info(
            "No leads captured yet. "
            "The AI assistant records visitor contact details here when they use the lead capture feature."
        )
        return

    filtered = [
        lead for lead in leads
        if filter_status == "all" or lead.get("status") == filter_status
    ]

    if not filtered:
        st.info(f"No leads with status **{filter_status}**.")
        return

    total = len(filtered)
    shown = filtered[:page_size]
    if total > page_size:
        st.caption(f"Showing {page_size} of {total} leads — increase the limit to see more.")

    for lead in shown:
        lid = lead["id"]
        name_label = lead.get("visitor_name") or "Anonymous"
        with st.container(border=True):
            info_col, action_col = st.columns([4, 2])
            with info_col:
                contact = lead.get("contact") or "—"
                st.markdown(f"**{name_label}** — `{contact}`")
                st.caption(lead.get("intent") or "—")
                st.caption(f"Created {_format_dt(lead.get('created_at', ''))}")
            with action_col:
                current_idx = (
                    _STATUS_OPTIONS.index(lead["status"])
                    if lead.get("status") in _STATUS_OPTIONS
                    else 0
                )
                new_status = st.selectbox(
                    "Status",
                    _STATUS_OPTIONS,
                    index=current_idx,
                    key=f"lead_status_{lid}",
                    label_visibility="collapsed",
                    format_func=lambda x: x.capitalize(),
                )
                if st.button("Update", key=f"update_lead_{lid}", use_container_width=True):
                    result = _patch_json(
                        f"{backend_url}/leads/{lid}", {"status": new_status}, token
                    )
                    if result:
                        st.success("Updated.")
                        st.session_state.pop("leads_data", None)
                        st.rerun()
