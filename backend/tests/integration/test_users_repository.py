"""Integration tests for the users repository."""

from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import users as users_repo


class FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> object:
        return self._rows[0] if self._rows else None

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list:
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    def __init__(self, rows: list | None = None) -> None:
        self._rows = rows or []
        self.deleted: list = []

    async def delete(self, obj: object) -> None:
        self.deleted.append(obj)

    async def flush(self) -> None:
        pass

    async def execute(self, stmt: object) -> FakeResult:
        return FakeResult(self._rows)


def _fake_user(tenant_id) -> MagicMock:
    u = MagicMock()
    u.id = uuid4()
    u.email = f"u-{uuid4().hex[:6]}@example.com"
    u.role = "tenant_admin"
    u.tenant_id = tenant_id
    return u


# get_emails_by_ids


@pytest.mark.asyncio
async def test_get_emails_by_ids_returns_empty_dict_for_empty_set() -> None:
    session = FakeSession()
    result = await users_repo.get_emails_by_ids(cast(AsyncSession, session), set())
    assert result == {}


@pytest.mark.asyncio
async def test_get_emails_by_ids_maps_id_to_email() -> None:
    uid1, uid2 = uuid4(), uuid4()
    r1 = type("Row", (), {"id": uid1, "email": "a@a.com"})()
    r2 = type("Row", (), {"id": uid2, "email": "b@b.com"})()
    session = FakeSession(rows=[r1, r2])

    result = await users_repo.get_emails_by_ids(
        cast(AsyncSession, session), {uid1, uid2}
    )

    assert result[uid1] == "a@a.com"
    assert result[uid2] == "b@b.com"


# list_by_tenant


@pytest.mark.asyncio
async def test_list_by_tenant_returns_users_for_tenant() -> None:
    tenant_id = uuid4()
    u = _fake_user(tenant_id)
    session = FakeSession(rows=[u])

    result = await users_repo.list_by_tenant(
        cast(AsyncSession, session), tenant_id=tenant_id
    )

    assert result == [u]


@pytest.mark.asyncio
async def test_list_by_tenant_returns_empty_list_when_none() -> None:
    session = FakeSession(rows=[])
    result = await users_repo.list_by_tenant(
        cast(AsyncSession, session), tenant_id=uuid4()
    )
    assert result == []


# delete_by_tenant


@pytest.mark.asyncio
async def test_delete_by_tenant_deletes_all_users_and_returns_count() -> None:
    tenant_id = uuid4()
    u1, u2 = _fake_user(tenant_id), _fake_user(tenant_id)
    session = FakeSession(rows=[u1, u2])

    count = await users_repo.delete_by_tenant(cast(AsyncSession, session), tenant_id)

    assert count == 2
    assert u1 in session.deleted
    assert u2 in session.deleted


@pytest.mark.asyncio
async def test_delete_by_tenant_returns_zero_when_no_users() -> None:
    session = FakeSession(rows=[])
    count = await users_repo.delete_by_tenant(cast(AsyncSession, session), uuid4())
    assert count == 0


# get_by_id


@pytest.mark.asyncio
async def test_get_by_id_returns_user_when_found() -> None:
    u = _fake_user(uuid4())
    session = FakeSession(rows=[u])
    result = await users_repo.get_by_id(cast(AsyncSession, session), u.id)
    assert result is u


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_not_found() -> None:
    session = FakeSession(rows=[])
    result = await users_repo.get_by_id(cast(AsyncSession, session), uuid4())
    assert result is None
