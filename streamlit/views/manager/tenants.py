"""Manager — Tenants list page."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

from utils import _badge, _delete, _get_json, _post_json, _role_label, _short_id


def render(backend_url: str, token: str) -> None:
    st.title("Tenants")
    st.caption("View and manage all tenants on the platform.")

    _, hdr_right = st.columns([5, 1])
    with hdr_right:
        if st.button("Refresh", use_container_width=True):
            for _k in [k for k in st.session_state if k == "tenants_data"
                       or k.startswith(("users_data_", "cost_result_"))]:
                del st.session_state[_k]

    if "tenants_data" not in st.session_state:
        with st.spinner("Loading tenants..."):
            data = _get_json(f"{backend_url}/tenants/", token)
            st.session_state["tenants_data"] = data or []

    tenants: list[dict[str, Any]] = st.session_state.get("tenants_data", [])

    if not tenants:
        st.info("No tenants yet. Go to **Create Tenant** to add your first one.")
        return

    for tenant in tenants:
        tid = tenant["id"]
        with st.container(border=True):
            # Header row: name + badge left, Suspend + Erase + Delete right
            name_col, _, suspend_col, erase_col, delete_col = st.columns([4, 1, 1.2, 1.2, 1.2])
            with name_col:
                st.markdown(
                    f"**{tenant['name']}**  " + _badge(tenant["is_active"]),
                    unsafe_allow_html=True,
                )
                st.caption(f"`/{tenant['slug']}`   ·   `{_short_id(tid)}`")
            with suspend_col:
                if tenant["is_active"]:
                    st.markdown('<span class="warn-btn-marker"></span>', unsafe_allow_html=True)
                    if st.button("Suspend", key=f"suspend_{tid}", use_container_width=True):
                        cur = st.session_state.get(f"show_suspend_confirm_{tid}", False)
                        st.session_state[f"show_suspend_confirm_{tid}"] = not cur
                else:
                    st.markdown('<span class="btn-spacer"></span>', unsafe_allow_html=True)
                    if st.button("Unsuspend", key=f"unsuspend_{tid}", use_container_width=True):
                        result = _post_json(
                            f"{backend_url}/tenants/{tid}/unsuspend", {}, token
                        )
                        if result:
                            st.session_state.pop("tenants_data", None)
                            st.rerun()
            with erase_col:
                st.markdown('<span class="danger-btn-marker"></span>', unsafe_allow_html=True)
                if st.button("Erase data", key=f"erase_open_{tid}", use_container_width=True):
                    cur = st.session_state.get(f"show_erase_{tid}", False)
                    st.session_state[f"show_erase_{tid}"] = not cur
            with delete_col:
                st.markdown('<span class="hot-danger-btn-marker"></span>', unsafe_allow_html=True)
                if st.button("DELETE", key=f"delete_open_{tid}", use_container_width=True):
                    cur = st.session_state.get(f"show_delete_{tid}", False)
                    st.session_state[f"show_delete_{tid}"] = not cur

            st.write("")
            # Action row: secondary buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Users", key=f"users_open_{tid}", use_container_width=True):
                    cur = st.session_state.get(f"show_users_{tid}", False)
                    st.session_state[f"show_users_{tid}"] = not cur
                    if not cur:
                        st.session_state.pop(f"show_cost_{tid}", None)
                        st.session_state.pop(f"show_embed_{tid}", None)
            with col2:
                if st.button("View cost", key=f"cost_open_{tid}", use_container_width=True):
                    cur = st.session_state.get(f"show_cost_{tid}", False)
                    st.session_state[f"show_cost_{tid}"] = not cur
                    if not cur:
                        st.session_state.pop(f"show_users_{tid}", None)
                        st.session_state.pop(f"show_embed_{tid}", None)
            with col3:
                if st.button("Embed code", key=f"embed_open_{tid}", use_container_width=True):
                    cur = st.session_state.get(f"show_embed_{tid}", False)
                    st.session_state[f"show_embed_{tid}"] = not cur
                    if not cur:
                        st.session_state.pop(f"show_users_{tid}", None)
                        st.session_state.pop(f"show_cost_{tid}", None)

            # Embed code panel
            if st.session_state.get(f"show_embed_{tid}"):
                with st.container(border=True):
                    st.markdown("**Embed code**")
                    st.caption("Paste this snippet into any page where the widget should appear.")
                    st.code(
                        f'<script src="{backend_url}/widget.js"'
                        f' data-widget-id="{tid}" async></script>',
                        language="html",
                    )

            # Users panel
            if st.session_state.get(f"show_users_{tid}"):
                with st.container(border=True):
                    st.markdown("**Users**")
                    if f"users_data_{tid}" not in st.session_state:
                        with st.spinner("Loading users..."):
                            users_data = _get_json(
                                f"{backend_url}/tenants/{tid}/users", token
                            )
                            st.session_state[f"users_data_{tid}"] = users_data or []
                    users_list = st.session_state.get(f"users_data_{tid}", [])
                    if not users_list:
                        st.info("No users for this tenant.")
                    else:
                        for u in users_list:
                            uid = u["id"]
                            ucol1, ucol2, ucol3, ucol4 = st.columns([3, 2, 1, 1])
                            ucol1.write(u["email"])
                            ucol2.caption(_role_label(u["role"]))
                            ucol3.caption("Active" if u["is_active"] else "Inactive")
                            with ucol4:
                                st.markdown('<span class="danger-btn-marker"></span>', unsafe_allow_html=True)
                                if st.button("DELETE", key=f"del_user_{uid}", use_container_width=True):
                                    cur = st.session_state.get(f"show_del_user_{uid}", False)
                                    st.session_state[f"show_del_user_{uid}"] = not cur

                            if st.session_state.get(f"show_del_user_{uid}"):
                                with st.container(border=True):
                                    st.warning(f"Delete **{u['email']}**? This cannot be undone.")
                                    dc_ok, dc_cancel = st.columns(2)
                                    with dc_ok:
                                        if st.button("Yes, delete", key=f"confirm_del_user_{uid}", type="primary"):
                                            if _delete(f"{backend_url}/users/{uid}", token):
                                                st.session_state.pop(f"users_data_{tid}", None)
                                                st.session_state.pop(f"show_del_user_{uid}", None)
                                                st.rerun()
                                    with dc_cancel:
                                        if st.button("Cancel", key=f"cancel_del_user_{uid}"):
                                            st.session_state.pop(f"show_del_user_{uid}", None)
                                            st.rerun()

            # Cost panel
            if st.session_state.get(f"show_cost_{tid}"):
                with st.container(border=True):
                    today = date.today()
                    period = st.date_input(
                        "Period",
                        value=(today - timedelta(days=6), today),
                        key=f"cost_period_{tid}",
                    )
                    if len(period) == 2:
                        start_day, end_day = period
                    else:
                        start_day = end_day = period[0] if period else today
                    if st.button("Fetch", key=f"fetch_cost_{tid}"):
                        with st.spinner("Fetching cost data..."):
                            cost = _get_json(
                                f"{backend_url}/tenants/{tid}/cost"
                                f"?start_day={start_day}&end_day={end_day}",
                                token,
                            )
                        if cost is not None:
                            st.session_state[f"cost_result_{tid}"] = {
                                "data": cost,
                                "start": str(start_day),
                                "end": str(end_day),
                            }
                    stored_cost = st.session_state.get(f"cost_result_{tid}")
                    if stored_cost is not None:
                        if stored_cost["start"] != str(start_day) or stored_cost["end"] != str(end_day):
                            st.caption(
                                f"Showing results for {stored_cost['start']} – {stored_cost['end']}"
                                " — click Fetch to update."
                            )
                        c1, c2, c3 = st.columns(3)
                        cost_data = stored_cost["data"]
                        c1.metric("Total tokens", cost_data["total_tokens"])
                        c2.metric("Prompt tokens", cost_data["prompt_tokens"])
                        c3.metric("Completion tokens", cost_data["completion_tokens"])

            # Delete tenant confirmation panel
            if st.session_state.get(f"show_delete_{tid}"):
                with st.container(border=True):
                    st.error(
                        f"You are about to permanently delete **{tenant['name']}** and everything under it: "
                        "all users, content, leads, sessions, and files. "
                        "This action is irreversible."
                    )
                    st.caption(
                        f"To confirm, type the tenant's unique identifier (slug) below: `{tenant['slug']}`"
                    )
                    confirm_del = st.text_input(
                        "Tenant slug",
                        placeholder=tenant["slug"],
                        key=f"confirm_delete_slug_{tid}",
                        label_visibility="collapsed",
                    )
                    dc_ok, dc_cancel = st.columns(2)
                    with dc_ok:
                        if st.button("Yes, delete tenant", key=f"do_delete_{tid}", type="primary"):
                            if confirm_del != tenant["slug"]:
                                st.error(f'Slug mismatch — you typed "{confirm_del}", expected "{tenant["slug"]}".')
                            else:
                                if _delete(f"{backend_url}/tenants/{tid}", token):
                                    st.session_state.pop("tenants_data", None)
                                    st.session_state.pop(f"show_delete_{tid}", None)
                                    st.rerun()
                    with dc_cancel:
                        if st.button("Cancel", key=f"cancel_delete_{tid}"):
                            st.session_state.pop(f"show_delete_{tid}", None)
                            st.rerun()

            # Suspend confirmation panel
            if st.session_state.get(f"show_suspend_confirm_{tid}"):
                with st.container(border=True):
                    st.warning(
                        f"Suspend **{tenant['name']}**? "
                        "The tenant's widget will stop accepting new conversations."
                    )
                    c_ok, c_cancel = st.columns(2)
                    with c_ok:
                        if st.button("Yes, suspend", key=f"do_suspend_{tid}", type="primary"):
                            result = _post_json(
                                f"{backend_url}/tenants/{tid}/suspend", {}, token
                            )
                            if result:
                                st.session_state.pop("tenants_data", None)
                                st.session_state.pop(f"show_suspend_confirm_{tid}", None)
                                st.rerun()
                    with c_cancel:
                        if st.button("Cancel", key=f"cancel_suspend_{tid}"):
                            st.session_state.pop(f"show_suspend_confirm_{tid}", None)
                            st.rerun()

            # Erase confirmation panel
            if st.session_state.get(f"show_erase_{tid}"):
                with st.container(border=True):
                    st.warning(
                        "This permanently deletes all tenant data "
                        "(DB rows, vectors, blobs, sessions)."
                    )
                    confirm_slug = st.text_input(
                        f"Type **{tenant['slug']}** to confirm",
                        key=f"confirm_slug_{tid}",
                    )
                    c_ok, c_cancel = st.columns(2)
                    with c_ok:
                        if st.button("Confirm erase", key=f"do_erase_{tid}", type="primary"):
                            if confirm_slug != tenant["slug"]:
                                st.error("Slug does not match.")
                            else:
                                result = _post_json(
                                    f"{backend_url}/tenants/{tid}/erase", {}, token
                                )
                                if result:
                                    st.success("Tenant data erased.")
                                    st.session_state.pop("tenants_data", None)
                                    st.session_state.pop(f"show_erase_{tid}", None)
                                    st.rerun()
                    with c_cancel:
                        if st.button("Cancel", key=f"cancel_erase_{tid}"):
                            st.session_state.pop(f"show_erase_{tid}", None)
                            st.rerun()
