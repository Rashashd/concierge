"""Manager — Connection Settings page."""
from __future__ import annotations

import streamlit as st

from utils import BACKEND_URL, GUARDRAILS_URL, MODEL_SERVER_URL


def render() -> None:
    st.title("Connection Settings")
    st.caption("Override service URLs for local development or testing.")
    st.write("")

    with st.container(border=True):
        st.text_input("Backend URL", value=BACKEND_URL, key="cfg_backend_url")
        st.text_input("Model-server URL", value=MODEL_SERVER_URL, key="cfg_model_server_url")
        st.text_input("Guardrails URL", value=GUARDRAILS_URL, key="cfg_guardrails_url")
        st.text_input(
            "Service token for local testing",
            value="",
            type="password",
            key="cfg_service_token",
        )
        st.caption(
            "Changes apply immediately within this session. "
            "Settings reset to environment defaults on page refresh."
        )
