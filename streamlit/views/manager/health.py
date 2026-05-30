"""Manager — Service Health page."""
from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from utils import _get_json


def _service_card(url: str, key: str, label: str) -> None:
    with st.container(border=True):
        st.subheader(label)
        st.caption(url)
        if st.button("Check", key=f"hc_btn_{key}", use_container_width=True):
            with st.spinner("Checking..."):
                result = _get_json(f"{url}/healthz")
            if result is not None:
                st.session_state[f"hc_{key}"] = {
                    "data": result,
                    "at": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                }
        stored = st.session_state.get(f"hc_{key}")
        if stored is not None:
            st.caption(f"Last checked: {stored['at']}")
            st.json(stored["data"])


def render(backend_url: str, model_server_url: str, guardrails_url: str) -> None:
    st.title("Service Health")
    st.caption("Real-time status of all connected services.")
    st.write("")

    col1, col2, col3 = st.columns(3)
    with col1:
        _service_card(backend_url, "backend", "Backend")
    with col2:
        _service_card(model_server_url, "model", "Model server")
    with col3:
        _service_card(guardrails_url, "guardrails", "Guardrails")
