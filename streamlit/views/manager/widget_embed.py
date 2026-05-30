"""Manager — Widget Embed Snippet page."""
from __future__ import annotations

import streamlit as st

from utils import _get_json


def render(backend_url: str, token: str) -> None:
    st.title("Widget Embed Snippet")
    st.caption("Generate the HTML snippet to embed the AI widget on a tenant's website.")
    st.write("")

    _, refresh_col = st.columns([5, 1])
    with refresh_col:
        if st.button("Refresh", use_container_width=True, key="embed_refresh"):
            st.session_state.pop("embed_tenants", None)
            st.rerun()

    if "embed_tenants" not in st.session_state:
        with st.spinner("Loading tenants..."):
            data = _get_json(f"{backend_url}/tenants/", token)
            st.session_state["embed_tenants"] = data or []

    tenants = st.session_state.get("embed_tenants", [])

    with st.container(border=True):
        if tenants:
            tenant_map = {t["id"]: f"{t['name']} (/{t['slug']})" for t in tenants}
            widget_id = st.selectbox(
                "Tenant",
                list(tenant_map.keys()),
                format_func=lambda x: tenant_map[x],
            )
        else:
            widget_id = st.text_input(
                "Widget ID",
                placeholder="Enter the tenant UUID",
            )

        st.write("")
        if widget_id:
            st.code(
                f'<script src="{backend_url}/widget.js" '
                f'data-widget-id="{widget_id}" async></script>',
                language="html",
            )
            st.info(
                "The widget authenticates each session with a signed, short-lived token. "
                "CORS and CSP headers are browser defense-in-depth only."
            )
