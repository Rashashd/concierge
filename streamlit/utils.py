"""Shared HTTP helpers and UI utilities for the Streamlit admin app."""
from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000").rstrip("/")
MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "http://model-server:8001").rstrip("/")
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "http://guardrails:8002").rstrip("/")


@st.cache_resource
def _http_client() -> httpx.Client:
    """Shared HTTP client with connection pooling — one TCP connection reused across all requests."""
    return httpx.Client(
        timeout=httpx.Timeout(10.0, connect=5.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


_STATUS_MESSAGES: dict[int, str] = {
    400: "Invalid request. Please check your inputs.",
    401: "Your session has expired. Please log in again.",
    403: "You don't have permission to do that.",
    404: "The requested resource was not found.",
    409: "A conflict occurred.",
    422: "Some fields are invalid. Please check your inputs.",
    429: "Too many requests. Please wait a moment and try again.",
    500: "Server error. Please try again later.",
    502: "Server is temporarily unavailable. Please try again.",
    503: "Service unavailable. Please try again later.",
}


def _friendly_error(exc: httpx.HTTPError, login: bool = False) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:
            detail = ""
        if login and code in (400, 401):
            return "Incorrect email or password."
        if code == 409 and detail:
            return f"Conflict: {detail}"
        return _STATUS_MESSAGES.get(code, f"Unexpected error (HTTP {code}).")
    if isinstance(exc, httpx.ConnectError):
        return "Cannot reach the server. Make sure the backend is running."
    if isinstance(exc, httpx.TimeoutException):
        return "The request timed out. The server may be busy — please try again."
    return "An unexpected error occurred. Please try again."


def _handle_http_error(exc: httpx.HTTPError, login: bool = False) -> None:
    if not login and isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401:
        for key in ["auth_token", "user_role", "user_email", "user_tenant_id"]:
            st.session_state.pop(key, None)
        st.error("Your session has expired. Please log in again.")
        st.rerun()
    st.error(_friendly_error(exc, login=login))


def _get_json(url: str, token: str | None = None) -> Any:
    try:
        r = _http_client().get(url, headers=_headers(token))
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        _handle_http_error(exc)
        return None


def _post_json(url: str, payload: dict[str, Any], token: str | None = None) -> Any:
    try:
        r = _http_client().post(url, json=payload, headers=_headers(token))
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        _handle_http_error(exc)
        return None


def _post_form(url: str, data: dict[str, str]) -> Any:
    try:
        r = _http_client().post(url, data=data)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        _handle_http_error(exc, login=True)
        return None


def _patch_json(url: str, payload: dict[str, Any], token: str | None = None) -> Any:
    try:
        r = _http_client().patch(url, json=payload, headers=_headers(token))
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        _handle_http_error(exc)
        return None


def _put_json(url: str, payload: dict[str, Any], token: str | None = None) -> Any:
    try:
        r = _http_client().put(url, json=payload, headers=_headers(token))
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        _handle_http_error(exc)
        return None


def _delete(url: str, token: str | None = None) -> bool:
    try:
        r = _http_client().delete(url, headers=_headers(token))
        r.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        _handle_http_error(exc)
        return False


def _badge(is_active: bool) -> str:
    if is_active:
        return (
            '<span style="background:#DCFCE7;color:#15803D;padding:2px 10px;'
            'border-radius:9999px;font-size:0.82em;font-weight:600;">Active</span>'
        )
    return (
        '<span style="background:#FEE2E2;color:#DC2626;padding:2px 10px;'
        'border-radius:9999px;font-size:0.82em;font-weight:600;">Suspended</span>'
    )


def _format_dt(iso: str) -> str:
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%b %d, %Y  %H:%M UTC")
    except Exception:
        return iso


def _short_id(uid: str) -> str:
    return f"{uid[:8]}…" if len(uid) > 8 else uid


def _role_label(role: str) -> str:
    return {"tenant_manager": "Manager", "tenant_admin": "Admin"}.get(role, role)
