"""Admin — Embed Snippet page."""
from __future__ import annotations

import streamlit as st

from utils import _get_json


def render(backend_url: str, token: str) -> None:
    st.title("Embed Snippet")
    st.caption("Add the AI assistant widget to your website.")
    st.write("")

    if "tenant_detail" not in st.session_state:
        with st.spinner("Loading..."):
            detail = _get_json(f"{backend_url}/tenants/me", token)
            if detail:
                st.session_state["tenant_detail"] = detail

    default_id: str = st.session_state.get("tenant_detail", {}).get("id", "")

    with st.container(border=True):
        widget_id = st.text_input(
            "Widget ID",
            value=default_id,
            key="admin_widget_id",
        )
        if widget_id:
            st.write("")
            st.code(
                f'<script src="{backend_url}/widget.js" '
                f'data-widget-id="{widget_id}" async></script>',
                language="html",
            )
            st.info(
                "The widget uses a signed, short-lived token for every session. "
                "CORS and CSP are browser defense-in-depth only."
            )
