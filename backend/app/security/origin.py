"""Widget origin validation helpers.

Wiring note: `is_origin_allowed` is not currently called in the /chat handler
because there is no persisted per-tenant allowed-origin list yet.  Once each
tenant can configure its own allowed origins (stored on Tenant or a related
table), wire a check in the widget-token verification or chat route to compare
the incoming Origin/Referer header against the tenant's list.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlparse


def normalize_origin(origin: str) -> str:
    """Normalize an origin for comparison.

    Behavior:
    - Lowercase scheme and host.
    - Preserve explicit port.
    - Remove trailing slash.
    - Raise ValueError for invalid origins or non-http/https schemes.
    """
    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("Origin must include a hostname")
    normalized = f"{parsed.scheme}://{parsed.hostname.lower()}"
    if parsed.port is not None:
        normalized += f":{parsed.port}"
    return normalized


def is_origin_allowed(
    origin: str | None,
    allowed_origins: Sequence[str],
) -> bool:
    """Check whether *origin* is in the configured allow-list.

    Rules:
    - If *allowed_origins* is empty, return ``True`` (allow-all, temporary).
    - If *origin* is ``None`` / missing and the list is non-empty, return ``False``.
    - Invalid *origin* strings return ``False``.
    - Invalid entries in *allowed_origins* are silently skipped.
    """
    if not allowed_origins:
        return True
    if origin is None:
        return False

    try:
        norm_origin = normalize_origin(origin)
    except ValueError:
        return False

    for item in allowed_origins:
        try:
            if normalize_origin(item) == norm_origin:
                return True
        except ValueError:
            continue

    return False
