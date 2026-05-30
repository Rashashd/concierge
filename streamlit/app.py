"""Streamlit admin UI for Concierge — entry point and router."""
from __future__ import annotations

import streamlit as st

from utils import BACKEND_URL, GUARDRAILS_URL, MODEL_SERVER_URL, _get_json, _post_form
import views.admin.content as v_content
import views.admin.embed_snippet as v_embed
import views.admin.escalations as v_escalations
import views.admin.leads as v_leads
import views.admin.persona_guardrails as v_persona
import views.manager.audit_log as v_audit_log
import views.manager.connection_settings as v_connection
import views.manager.create_tenant as v_create_tenant
import views.manager.health as v_health
import views.manager.home as v_home
import views.manager.nemo_guardrails as v_nemo
import views.manager.tenants as v_tenants
import views.manager.widget_embed as v_widget_embed

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Concierge Admin", layout="wide", page_icon="🏨")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"], .stMarkdown, .stTextInput, .stButton, .stSelectbox,
    .stTextArea, .stCaption, .stSubheader, .stTitle, h1, h2, h3, p, label, div {
        font-family: 'Inter', sans-serif !important;
    }

    /* Consistent indigo accent for section subheaders */
    h3 { color: #3730A3; }

    /* Sidebar nav — active item looks like a selected state, not a CTA */
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background-color: #EEF2FF;
        color: #3730A3;
        border: 1px solid #C7D2FE;
        font-weight: 600;
        text-align: left;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
        background: transparent;
        border-color: transparent;
        color: inherit;
        text-align: left;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
        background-color: #F1F5F9;
        border-color: transparent;
    }

    /* Collapse the marker span's wrapper so it takes no vertical space */
    [data-testid="element-container"]:has(.danger-btn-marker),
    .element-container:has(.danger-btn-marker),
    [data-testid="element-container"]:has(.hot-danger-btn-marker),
    .element-container:has(.hot-danger-btn-marker),
    [data-testid="element-container"]:has(.warn-btn-marker),
    .element-container:has(.warn-btn-marker),
    [data-testid="element-container"]:has(.btn-spacer),
    .element-container:has(.btn-spacer) {
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        overflow: hidden !important;
    }

    /* Danger action button (erase / destructive) */
    [data-testid="element-container"]:has(.danger-btn-marker) ~ [data-testid="element-container"] .stButton > button,
    .element-container:has(.danger-btn-marker) ~ .element-container .stButton > button {
        background-color: #FEF2F2 !important;
        color: #DC2626 !important;
        border-color: #FECACA !important;
    }
    [data-testid="element-container"]:has(.danger-btn-marker) ~ [data-testid="element-container"] .stButton > button:hover,
    .element-container:has(.danger-btn-marker) ~ .element-container .stButton > button:hover {
        background-color: #FEE2E2 !important;
        border-color: #FCA5A5 !important;
    }

    /* Warning action button (suspend) */
    [data-testid="element-container"]:has(.warn-btn-marker) ~ [data-testid="element-container"] .stButton > button,
    .element-container:has(.warn-btn-marker) ~ .element-container .stButton > button {
        background-color: #FFFBEB !important;
        color: #B45309 !important;
        border-color: #FDE68A !important;
    }
    [data-testid="element-container"]:has(.warn-btn-marker) ~ [data-testid="element-container"] .stButton > button:hover,
    .element-container:has(.warn-btn-marker) ~ .element-container .stButton > button:hover {
        background-color: #FEF3C7 !important;
        border-color: #FCD34D !important;
    }

    /* Hot red delete button */
    [data-testid="element-container"]:has(.hot-danger-btn-marker) ~ [data-testid="element-container"] .stButton > button,
    .element-container:has(.hot-danger-btn-marker) ~ .element-container .stButton > button {
        background-color: #DC2626 !important;
        color: #FFFFFF !important;
        border-color: #DC2626 !important;
        font-weight: 700 !important;
    }
    [data-testid="element-container"]:has(.hot-danger-btn-marker) ~ [data-testid="element-container"] .stButton > button:hover,
    .element-container:has(.hot-danger-btn-marker) ~ .element-container .stButton > button:hover {
        background-color: #B91C1C !important;
        border-color: #B91C1C !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Login page ─────────────────────────────────────────────────────────────────

if not st.session_state.get("auth_token"):
    st.write("")
    st.write("")
    _, center, _ = st.columns([1, 1.6, 1])

    with center:
        st.markdown("## Welcome to Concierge Admin")
        st.markdown(
            "The central control panel for your multi-tenant AI concierge platform."
        )
        st.write("")
        with st.container(border=True):
            st.subheader("Sign in")
            st.write("")
            with st.form("login_form"):
                login_email = st.text_input("Email")
                login_password = st.text_input("Password", type="password")
                st.write("")
                submitted = st.form_submit_button(
                    "Sign in", use_container_width=True, type="primary"
                )
            if submitted:
                result = _post_form(
                    f"{BACKEND_URL}/auth/login",
                    {"username": login_email, "password": login_password},
                )
                if result and "access_token" in result:
                    token_tmp = result["access_token"]
                    me = _get_json(f"{BACKEND_URL}/users/me", token_tmp)
                    if me:
                        st.session_state["auth_token"] = token_tmp
                        st.session_state["user_role"] = me.get("role")
                        st.session_state["user_tenant_id"] = me.get("tenant_id")
                        st.session_state["user_email"] = me.get("email")
                        st.session_state["show_welcome"] = True
                        st.rerun()
    st.stop()

# ── Authenticated state ────────────────────────────────────────────────────────

role: str = st.session_state["user_role"]
token: str = st.session_state["auth_token"]
email: str = st.session_state["user_email"]

backend_url: str = st.session_state.get("cfg_backend_url") or BACKEND_URL
model_server_url: str = st.session_state.get("cfg_model_server_url") or MODEL_SERVER_URL
guardrails_url: str = st.session_state.get("cfg_guardrails_url") or GUARDRAILS_URL
service_token: str = st.session_state.get("cfg_service_token") or ""

# ── Sidebar ────────────────────────────────────────────────────────────────────

if role == "tenant_manager":
    nav_items = [
        "Home",
        "Tenants",
        "Create Tenant",
        "Audit Log",
        "Health",
        "NeMo Guardrails",
        "Widget Embed",
        "Connection Settings",
    ]
else:
    nav_items = ["Persona & Guardrails", "Content", "Leads", "Escalations", "Embed Snippet"]

with st.sidebar:
    st.markdown("### Concierge Admin")
    st.caption(email)
    role_label = "Manager" if role == "tenant_manager" else "Admin"
    st.caption(f"Role: {role_label}")
    st.divider()

    if "page" not in st.session_state or st.session_state["page"] not in nav_items:
        st.session_state["page"] = nav_items[0]

    for _nav_item in nav_items:
        _active = st.session_state["page"] == _nav_item
        if st.button(
            _nav_item,
            key=f"nav_{_nav_item}",
            use_container_width=True,
            type="primary" if _active else "secondary",
        ):
            st.session_state["page"] = _nav_item
            st.rerun()

    st.divider()
    if st.button("Logout", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

page = st.session_state["page"]

if st.session_state.pop("show_welcome", False):
    _name = email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
    st.success(f"Welcome back, {_name}!")

# ── Route to page ──────────────────────────────────────────────────────────────

if role == "tenant_manager":
    if page == "Home":
        v_home.render(backend_url, token)
    elif page == "Tenants":
        v_tenants.render(backend_url, token)
    elif page == "Create Tenant":
        v_create_tenant.render(backend_url, token)
    elif page == "Audit Log":
        v_audit_log.render(backend_url, token)
    elif page == "Health":
        v_health.render(backend_url, model_server_url, guardrails_url)
    elif page == "NeMo Guardrails":
        v_nemo.render(guardrails_url, service_token, backend_url, token)
    elif page == "Widget Embed":
        v_widget_embed.render(backend_url, token)
    elif page == "Connection Settings":
        v_connection.render()

elif role == "tenant_admin":
    if page == "Persona & Guardrails":
        v_persona.render(backend_url, token)
    elif page == "Content":
        v_content.render(backend_url, token)
    elif page == "Leads":
        v_leads.render(backend_url, token)
    elif page == "Escalations":
        v_escalations.render(backend_url, token)
    elif page == "Embed Snippet":
        v_embed.render(backend_url, token)
