from uuid import uuid4

import jwt
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
from app.schemas import TenantContext, UserContext
from app.security.widget_token import issue_widget_token

WIDGET_SECRET = "0123456789abcdef0123456789abcdef"
BACKEND_SECRET = "backend-secret-32-chars-for-test"


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="bearer", credentials=token)


def _widget_settings() -> Settings:
    return Settings(
        vault_addr="http://localhost:8200",
        vault_token=SecretStr("root"),
        widget_token_secret=SecretStr(WIDGET_SECRET),
    )


def _user_settings(secret: str = BACKEND_SECRET) -> Settings:
    return Settings(
        vault_addr="http://localhost:8200",
        vault_token=SecretStr("root"),
        backend_secret_key=SecretStr(secret),
    )


def _widget_token(tenant_id=None, widget_id=None, session_id="s1") -> str:
    ctx = TenantContext(
        tenant_id=tenant_id or uuid4(),
        widget_id=widget_id or uuid4(),
        session_id=session_id,
    )
    return issue_widget_token(ctx, WIDGET_SECRET, 900)


def _user_jwt(user_id=None, role="tenant_manager", tenant_id=None) -> str:
    payload: dict = {"sub": str(user_id or uuid4()), "role": role}
    if tenant_id is not None:
        payload["tenant_id"] = str(tenant_id)
    return jwt.encode(payload, BACKEND_SECRET, algorithm="HS256")


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


# get_current_user


@pytest.mark.asyncio
async def test_get_current_user_returns_context_for_valid_jwt() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    token = _user_jwt(user_id=user_id, role="tenant_admin", tenant_id=tenant_id)
    user = await get_current_user(_bearer(token), _user_settings(), None)
    assert user.user_id == user_id
    assert user.role == "tenant_admin"
    assert user.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_get_current_user_allows_null_tenant_id_for_manager() -> None:
    token = _user_jwt(role="tenant_manager")
    user = await get_current_user(_bearer(token), _user_settings(), None)
    assert user.role == "tenant_manager"
    assert user.tenant_id is None


@pytest.mark.asyncio
async def test_get_current_user_raises_401_when_no_credentials() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(None, _user_settings(), None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_invalid_jwt() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_bearer("not-a-jwt"), _user_settings(), None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_missing_sub_claim() -> None:
    token = jwt.encode({"role": "tenant_manager"}, BACKEND_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_bearer(token), _user_settings(), None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_wrong_secret() -> None:
    token = _user_jwt()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_bearer(token), _user_settings("wrong-secret-32chars!!"), None)
    assert exc_info.value.status_code == 401


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
