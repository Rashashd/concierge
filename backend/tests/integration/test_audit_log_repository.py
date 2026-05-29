"""Integration tests for the audit log repository."""

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import audit_log as audit_log_repo


class FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows


class FakeSession:
    def __init__(self) -> None:
        self.added: list = []
        self.last_stmt: object = None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def execute(self, stmt: object) -> FakeResult:
        self.last_stmt = stmt
        return FakeResult([])


@pytest.mark.asyncio
async def test_create_sets_required_fields() -> None:
    actor_id = uuid4()
    tenant_id = uuid4()
    session = FakeSession()

    log = await audit_log_repo.create(
        cast(AsyncSession, session),
        actor_id=actor_id,
        actor_role="superadmin",
        action="tenant.create",
        tenant_id=tenant_id,
        payload={"name": "Acme"},
    )

    assert log.actor_id == actor_id
    assert log.actor_role == "superadmin"
    assert log.action == "tenant.create"
    assert log.tenant_id == tenant_id
    assert log.payload == {"name": "Acme"}
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_create_defaults_payload_to_empty_dict() -> None:
    session = FakeSession()

    log = await audit_log_repo.create(
        cast(AsyncSession, session),
        actor_id=uuid4(),
        actor_role="superadmin",
        action="tenant.suspend",
    )

    assert log.payload == {}


@pytest.mark.asyncio
async def test_create_allows_null_tenant_id() -> None:
    session = FakeSession()

    log = await audit_log_repo.create(
        cast(AsyncSession, session),
        actor_id=uuid4(),
        actor_role="superadmin",
        action="system.healthcheck",
        tenant_id=None,
    )

    assert log.tenant_id is None
    assert log.action == "system.healthcheck"
