"""Manager — Audit Log page."""
from __future__ import annotations

from typing import Any

import streamlit as st

from utils import _format_dt, _get_json, _role_label, _short_id

_ACTION_LABELS: dict[str, str] = {
    "tenant.created": "Tenant created",
    "tenant.suspended": "Tenant suspended",
    "tenant.unsuspended": "Tenant unsuspended",
    "tenant.erased": "Tenant data erased",
    "conversation.escalated": "Conversation escalated",
    "lead.captured": "Lead captured",
}


def _action_label(action: str) -> str:
    return _ACTION_LABELS.get(action, action.replace(".", " ").title())


def render(backend_url: str, token: str) -> None:
    st.title("Audit Log")
    st.caption("A tamper-evident record of all platform actions.")

    _, refresh_col, limit_col = st.columns([4, 1, 1])
    with refresh_col:
        if st.button("Refresh", use_container_width=True):
            st.session_state.pop("audit_data", None)
            st.session_state.pop("audit_limit", None)
    with limit_col:
        limit = st.selectbox(
            "Show", [50, 100, 250, 500], index=1, label_visibility="collapsed"
        )

    if "audit_data" not in st.session_state or st.session_state.get("audit_limit") != limit:
        with st.spinner("Loading audit log..."):
            data = _get_json(f"{backend_url}/tenants/audit?limit={limit}", token)
            st.session_state["audit_data"] = data or []
            st.session_state["audit_limit"] = limit

    entries: list[dict[str, Any]] = st.session_state.get("audit_data", [])

    if not entries:
        st.info("No audit log entries yet.")
        return

    tenant_map = {
        str(t["id"]): t["name"]
        for t in st.session_state.get("tenants_data", [])
    }

    rows = [
        {
            "Time": _format_dt(e["created_at"]),
            "Action": _action_label(e["action"]),
            "By": e.get("actor_email") or _short_id(str(e["actor_id"])),
            "Role": _role_label(e["actor_role"]),
            "Tenant": tenant_map.get(str(e["tenant_id"]), _short_id(str(e["tenant_id"]))) if e.get("tenant_id") else "—",
        }
        for e in entries
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
