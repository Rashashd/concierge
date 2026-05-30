"""Admin — Persona & Guardrails page."""
from __future__ import annotations

from typing import Any

import streamlit as st

from utils import _get_json, _patch_json


_TOOL_LABELS: dict[str, str] = {
    "rag_search": "Answer questions from your content",
    "capture_lead": "Collect visitor contact details",
    "escalate": "Hand off to a human agent",
}


def render(backend_url: str, token: str) -> None:
    st.title("Persona & Guardrails")
    st.caption("Configure how the AI assistant presents itself and what it is allowed to discuss.")
    st.write("")

    _, refresh_col = st.columns([5, 1])
    with refresh_col:
        if st.button("Refresh", use_container_width=True):
            st.session_state.pop("tenant_detail", None)

    if "tenant_detail" not in st.session_state:
        with st.spinner("Loading configuration..."):
            detail = _get_json(f"{backend_url}/tenants/me", token)
            if detail:
                st.session_state["tenant_detail"] = detail

    detail: dict[str, Any] = st.session_state.get("tenant_detail", {})
    current_gc: dict[str, Any] = detail.get("guardrail_config", {})

    persona_col, guardrail_col = st.columns([3, 2], gap="large")

    with persona_col:
        with st.container(border=True):
            st.subheader("Agent persona")
            st.caption("Describe how the AI assistant should present itself to visitors.")
            persona_text = st.text_area(
                "LLM persona",
                value=detail.get("llm_persona", ""),
                height=220,
                label_visibility="collapsed",
                key="persona_input",
            )

    with guardrail_col:
        with st.container(border=True):
            st.subheader("Guardrail config")
            blocked_raw = st.text_input(
                "Blocked topics (comma-separated)",
                value=", ".join(current_gc.get("blocked_topics", [])),
                key="blocked_topics_admin",
            )
            refusal_text = st.text_input(
                "Refusal tone",
                value=current_gc.get("refusal_tone", "Sorry, I cannot help with that"),
                key="refusal_tone_admin",
            )

    st.write("")

    _default_enabled = list(_TOOL_LABELS.keys())
    _saved_enabled: list[str] = current_gc.get("enabled_tools", _default_enabled)

    with st.container(border=True):
        st.subheader("Assistant capabilities")
        st.caption("Choose which features the assistant offers to visitors.")
        tool_checks: dict[str, bool] = {}
        for tool_key, tool_label in _TOOL_LABELS.items():
            tool_checks[tool_key] = st.checkbox(
                tool_label,
                value=tool_key in _saved_enabled,
                key=f"tool_{tool_key}",
            )

    st.write("")
    _saved_persona = (detail.get("llm_persona") or "").strip()
    _current_blocked = [t.strip() for t in blocked_raw.split(",") if t.strip()]
    _current_tools = {k for k, v in tool_checks.items() if v}
    _has_changes = (
        persona_text.strip() != _saved_persona
        or _current_blocked != current_gc.get("blocked_topics", [])
        or refusal_text != current_gc.get("refusal_tone", "Sorry, I cannot help with that")
        or _current_tools != set(current_gc.get("enabled_tools", list(_TOOL_LABELS.keys())))
    )
    if _has_changes and detail:
        st.info("You have unsaved changes.")
    if st.button("Save configuration", type="primary"):
        new_gc = {
            "blocked_topics": [t.strip() for t in blocked_raw.split(",") if t.strip()],
            "refusal_tone": refusal_text,
            "enabled_tools": [k for k, v in tool_checks.items() if v],
        }
        result = _patch_json(
            f"{backend_url}/tenants/me/config",
            {"llm_persona": persona_text, "guardrail_config": new_gc},
            token,
        )
        if result:
            st.session_state["tenant_detail"] = result
            st.success("Configuration saved.")
