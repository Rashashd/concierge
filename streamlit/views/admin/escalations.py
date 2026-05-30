"""Admin — Escalations page."""
from __future__ import annotations

from typing import Any

import streamlit as st

from utils import _format_dt, _get_json, _short_id


def render(backend_url: str, token: str) -> None:
    st.title("Escalations")
    st.caption("Conversations handed off to a human agent by the AI assistant.")

    _, refresh_col = st.columns([5, 1])
    with refresh_col:
        if st.button("Refresh", use_container_width=True):
            st.session_state.pop("escalations_data", None)

    if "escalations_data" not in st.session_state:
        with st.spinner("Loading escalations..."):
            data = _get_json(f"{backend_url}/escalations", token)
            st.session_state["escalations_data"] = data or []

    escalations: list[dict[str, Any]] = st.session_state.get("escalations_data", [])

    if not escalations:
        st.info(
            "No escalations yet. "
            "When the AI assistant hands a conversation off to a human agent, it will appear here."
        )
        return

    for esc in escalations:
        with st.container(border=True):
            conv_id = esc.get("conversation_id", "")
            st.markdown(f"**Conversation** `{_short_id(conv_id) if conv_id else '—'}`")
            raised = _format_dt(esc["created_at"]) if esc.get("created_at") else "—"
            esc_id = esc.get("id", "")
            st.caption(f"Raised {raised}   ·   ID: `{_short_id(esc_id) if esc_id else '—'}`")
            st.write(esc.get("reason") or "No reason provided.")
