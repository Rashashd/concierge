"""Manager — Create Tenant page."""
from __future__ import annotations

import re

import streamlit as st

from utils import _post_json

_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')


def render(backend_url: str, token: str) -> None:
    st.title("Create Tenant")
    st.caption("Set up a new tenant and their initial admin account.")
    st.write("")

    if st.session_state.pop("create_tenant_success", None):
        st.success("Tenant created successfully. The form has been cleared.")

    form_key = st.session_state.get("create_tenant_form_ver", 0)

    _, form_col, _ = st.columns([1, 2, 1])
    with form_col:
        with st.container(border=True):
            st.subheader("New tenant")
            with st.form(f"create_tenant_form_{form_key}"):
                new_name = st.text_input("Tenant name", key="new_tenant_name")
                new_slug = st.text_input(
                    "Slug  (lowercase letters, numbers, hyphens)", key="new_tenant_slug"
                )
                st.divider()
                st.caption("Initial admin account")
                admin_email = st.text_input("Admin email", key="new_admin_email")
                admin_password = st.text_input(
                    "Admin password", type="password", key="new_admin_password"
                )
                st.write("")
                submitted = st.form_submit_button(
                    "Create tenant", use_container_width=True, type="primary"
                )

            if submitted:
                if not new_name or not new_slug:
                    st.warning("Tenant name and slug are required.")
                elif not _SLUG_RE.match(new_slug):
                    st.warning(
                        "Slug must start with a letter or number and contain only "
                        "lowercase letters, numbers, and hyphens."
                    )
                elif not admin_email or not admin_password:
                    st.warning("Admin email and password are required.")
                elif len(admin_password) < 8:
                    st.warning("Admin password must be at least 8 characters.")
                else:
                    tenant_result = _post_json(
                        f"{backend_url}/tenants/",
                        {"name": new_name, "slug": new_slug},
                        token,
                    )
                    if tenant_result:
                        user_result = _post_json(
                            f"{backend_url}/auth/register",
                            {
                                "email": admin_email,
                                "password": admin_password,
                                "role": "tenant_admin",
                                "tenant_id": tenant_result["id"],
                            },
                        )
                        if user_result:
                            st.session_state["create_tenant_form_ver"] = form_key + 1
                            st.session_state["create_tenant_success"] = True
                            st.session_state.pop("tenants_data", None)
                            st.rerun()
                        else:
                            st.warning(
                                f"Tenant **{new_name}** was created but the admin account "
                                "could not be set up. Go to **Tenants**, erase this tenant, "
                                "and try again."
                            )
