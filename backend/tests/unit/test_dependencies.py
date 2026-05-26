from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr

from app.core.config import Settings
from app.core.dependencies import (
    get_admin_tenant_session,
    get_current_tenant,
    get_current_user,
    require_tenant_admin,
    require_tenant_manager,
)
from app.db.models import User
from app.schemas import TenantContext, UserContext
from app.security.widget_token import issue_widget_token

WIDGET_SECRET = "0123456789abcdef0123456789abcdef"


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="bearer", credentials=token)


def _widget_settings() -> Settings:
    return Settings(
        vault_addr="http://localhost:8200",
        vault_token=SecretStr("root"),
        widget_token_secret=SecretStr(WIDGET_SECRET),
    )


def _widget_token(tenant_id=None, widget_id=None, session_id="s1") -> str:
    ctx = TenantContext(
        tenant_id=tenant_id or uuid4(),
        widget_id=widget_id or uuid4(),
        session_id=session_id,
    )
    return issue_widget_token(ctx, WIDGET_SECRET, 900)


# get_current_tenant


@pytest.mark.asyncio
async def test_get_current_tenant_returns_context_for_valid_token() -> None:
    tenant_id = uuid4()
    widget_id = uuid4()
    token = _widget_token(tenant_id=tenant_id, widget_id=widget_id)
    ctx = await get_current_tenant(_bearer(token), _widget_settings())
    assert ctx.tenant_id == tenant_id
    assert ctx.widget_id == widget_id


@pytest.mark.asyncio
async def test_get_current_tenant_raises_401_when_no_credentials() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_tenant(None, _widget_settings())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_tenant_raises_401_for_non_bearer_scheme() -> None:
    creds = HTTPAuthorizationCredentials(scheme="basic", credentials="user:pass")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_tenant(creds, _widget_settings())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_tenant_raises_401_for_tampered_token() -> None:
    token = _widget_token() + "tampered"
    with pytest.raises(HTTPException) as exc_info:
        await get_current_tenant(_bearer(token), _widget_settings())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_tenant_raises_401_when_secret_is_empty() -> None:
    token = _widget_token()
    settings = Settings(
        vault_addr="http://localhost:8200",
        vault_token=SecretStr("root"),
        widget_token_secret=SecretStr(""),
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_tenant(_bearer(token), settings)
    assert exc_info.value.status_code == 401


# get_current_user — now maps ORM User → UserContext (JWT verified by fastapi-users)


@pytest.mark.asyncio
async def test_get_current_user_maps_tenant_admin_to_context() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    orm_user = User(
        id=user_id,
        email="admin@example.com",
        hashed_password="x",
        role="tenant_admin",
        tenant_id=tenant_id,
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )
    ctx = await get_current_user(orm_user)
    assert ctx.user_id == user_id
    assert ctx.role == "tenant_admin"
    assert ctx.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_get_current_user_maps_manager_with_no_tenant() -> None:
    user_id = uuid4()
    orm_user = User(
        id=user_id,
        email="mgr@example.com",
        hashed_password="x",
        role="tenant_manager",
        tenant_id=None,
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )
    ctx = await get_current_user(orm_user)
    assert ctx.user_id == user_id
    assert ctx.role == "tenant_manager"
    assert ctx.tenant_id is None


# get_admin_tenant_session guard


@pytest.mark.asyncio
async def test_get_admin_tenant_session_raises_403_when_user_has_no_tenant_id() -> None:
    user = UserContext(user_id=uuid4(), role="tenant_manager", tenant_id=None)
    gen = get_admin_tenant_session(request=None, user=user)
    with pytest.raises(HTTPException) as exc_info:
        await gen.__anext__()
    assert exc_info.value.status_code == 403


# require_tenant_manager


def test_require_tenant_manager_passes_for_manager_role() -> None:
    user = UserContext(user_id=uuid4(), role="tenant_manager", tenant_id=None)
    assert require_tenant_manager(user) is user


def test_require_tenant_manager_raises_403_for_admin_role() -> None:
    user = UserContext(user_id=uuid4(), role="tenant_admin", tenant_id=uuid4())
    with pytest.raises(HTTPException) as exc_info:
        require_tenant_manager(user)
    assert exc_info.value.status_code == 403


# require_tenant_admin


def test_require_tenant_admin_passes_for_admin_role() -> None:
    user = UserContext(user_id=uuid4(), role="tenant_admin", tenant_id=uuid4())
    assert require_tenant_admin(user) is user


def test_require_tenant_admin_raises_403_for_manager_role() -> None:
    user = UserContext(user_id=uuid4(), role="tenant_manager", tenant_id=None)
    with pytest.raises(HTTPException) as exc_info:
        require_tenant_admin(user)
    assert exc_info.value.status_code == 403
