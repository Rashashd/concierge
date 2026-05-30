"""Manager — Home / welcome page."""
from __future__ import annotations

import streamlit as st

from utils import _get_json


_CARDS = [
    (
        "Tenants",
        "View all tenants, manage users, check costs, suspend or erase.",
    ),
    (
        "Create Tenant",
        "Provision a new tenant and set up their initial admin account.",
    ),
    (
        "Audit Log",
        "Browse the tamper-evident record of every platform action.",
    ),
    (
        "Health",
        "Check real-time status of the backend, model server, and guardrails.",
    ),
    (
        "NeMo Guardrails",
        "Test input and output rails against a tenant's guardrail config.",
    ),
    (
        "Widget Embed",
        "Generate and preview the embed snippet for a tenant's website.",
    ),
]


def render(backend_url: str, token: str) -> None:
    email: str = st.session_state.get("user_email", "")
    name = email.split("@")[0].replace(".", " ").replace("_", " ").title()

    st.title(f"Welcome, {name}!")
    st.caption("Concierge Platform — Manager Console")
    st.write("")

    if "tenants_data" not in st.session_state:
        with st.spinner("Loading..."):
            data = _get_json(f"{backend_url}/tenants/", token)
            st.session_state["tenants_data"] = data or []

    tenants = st.session_state.get("tenants_data", [])
    if tenants:
        active = sum(1 for t in tenants if t.get("is_active"))
        suspended = len(tenants) - active
        m1, m2, m3 = st.columns(3)
        m1.metric("Total tenants", len(tenants))
        m2.metric("Active", active)
        m3.metric("Suspended", suspended)
        st.write("")

    st.subheader("Quick access")
    col_a, col_b, col_c = st.columns(3)
    cols = [col_a, col_b, col_c, col_a, col_b, col_c]

    for (page, description), col in zip(_CARDS, cols):
        with col:
            with st.container(border=True):
                st.markdown(f"**{page}**")
                st.caption(description)
                if st.button("Go →", key=f"home_nav_{page}", use_container_width=True):
                    st.session_state["page"] = page
                    st.rerun()
