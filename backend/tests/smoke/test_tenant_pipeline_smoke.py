"""Smoke tests for the tenant admin pipeline.

These call the real route handlers + real repo functions against a fake session.
The unit tests in test_tenants.py monkeypatch individual repo functions; these
tests let the full code path run so that wiring bugs (e.g. missing audit log)
are caught without a live database.
"""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tenants import create_tenant
from app.db.models import AuditLog, Tenant
from app.schemas import TenantCreate, UserContext
from app.services.erasure import ErasureReport, erase_tenant
from app.services.memory import RedisMemoryClient

# ── Shared fakes ──────────────────────────────────────────────────────────────


class FakeResult:
    def __init__(self, rows: list | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object:
        return self._rows[0] if self._rows else None

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list:
        return self._rows


class FakeSession:
    """Fake SQLAlchemy session. Accepts a pre-loaded results queue for execute()."""

    def __init__(self, results: list[FakeResult] | None = None) -> None:
        self.added: list = []
        self._results: list[FakeResult] = list(results or [])

    # Async context manager for session.begin()
    def begin(self) -> "FakeSession":
        return self

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        now = datetime.now(UTC)
        if not getattr(obj, "id", None):
            try:
                obj.id = uuid4()
            except Exception:
                pass
        if getattr(obj, "is_active", None) is None and hasattr(obj, "is_active"):
            try:
                obj.is_active = True
            except Exception:
                pass
        if not getattr(obj, "created_at", None):
            try:
                obj.created_at = now
            except Exception:
                pass

    async def execute(
        self, stmt: object, *args: object, **kwargs: object
    ) -> FakeResult:
        if self._results:
            return self._results.pop(0)
        return FakeResult()


class FakeRedis:
    def __init__(self, key_count: int = 3) -> None:
        self._key_count = key_count

    async def keys(self, pattern: str) -> list[str]:
        return [f"session:key{i}" for i in range(self._key_count)]

    async def delete(self, *keys: str) -> int:
        return len(keys)

    async def scan_iter(self, match: str) -> list[str]:
        return [f"session:key{i}" for i in range(self._key_count)]


class FakeMinio:
    def __init__(self, objects_deleted: int = 2) -> None:
        self._objects_deleted = objects_deleted

    async def delete_tenant_prefix(self, tenant_id: object) -> int:
        return self._objects_deleted


# ── create_tenant: audit log must be written ──────────────────────────────────


@pytest.mark.asyncio
async def test_smoke_create_tenant_writes_both_tenant_and_audit_log() -> None:
    """create_tenant must persist a Tenant AND an AuditLog in the same transaction."""
    actor_id = uuid4()
    user = UserContext(user_id=actor_id, role="tenant_manager", tenant_id=None)

    # get_by_slug returns None (no duplicate); create + audit both call add()
    session = FakeSession(results=[FakeResult(rows=[])])

    result = await create_tenant(
        TenantCreate(name="Acme Corp", slug="acme"),
        user,
        cast(AsyncSession, session),
    )

    assert result.slug == "acme"
    assert result.name == "Acme Corp"

    tenant_adds = [o for o in session.added if isinstance(o, Tenant)]
    audit_adds = [o for o in session.added if isinstance(o, AuditLog)]

    assert len(tenant_adds) == 1, "tenant_repo.create must add a Tenant"
    assert len(audit_adds) == 1, "audit_repo.create must add an AuditLog"
    assert audit_adds[0].action == "tenant.created"
    assert audit_adds[0].actor_id == actor_id
    assert audit_adds[0].payload["slug"] == "acme"


# ── erase_tenant: all repos called + audit log written ────────────────────────


@pytest.mark.asyncio
async def test_smoke_erasure_pipeline_calls_all_repos_and_writes_audit() -> None:
    """erase_tenant must delete from all 4 tables, write an audit log, and
    call Redis + MinIO cleanup."""
    tenant_id = uuid4()
    actor_id = uuid4()

    # Execute calls in order inside erase_tenant:
    # 1. set_config (result ignored)
    # 2. chunk_repo.delete_by_tenant       → rowcount 5
    # 3. content_repo.delete_by_tenant     → rowcount 2
    # 4. lead_repo.delete_by_tenant        → rowcount 3
    # 5. widget_config_repo.delete_by_tenant → rowcount 1
    # 6. audit_repo.create calls add() + flush(), no execute
    session = FakeSession(
        results=[
            FakeResult(rowcount=0),  # set_config
            FakeResult(rowcount=5),  # chunks
            FakeResult(rowcount=2),  # content_items
            FakeResult(rowcount=3),  # leads
            FakeResult(rowcount=1),  # widget_configs
        ]
    )

    report = await erase_tenant(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role="superadmin",
        session=cast(AsyncSession, session),
        redis=cast(RedisMemoryClient, FakeRedis(key_count=4)),
        minio=cast(object, FakeMinio(objects_deleted=7)),
    )

    assert isinstance(report, ErasureReport)
    assert report.chunks_deleted == 5
    assert report.content_items_deleted == 2
    assert report.leads_deleted == 3
    assert report.widget_configs_deleted == 1
    assert report.minio_objects_deleted == 7

    audit_adds = [o for o in session.added if isinstance(o, AuditLog)]
    assert len(audit_adds) == 1, "audit_repo.create must add an AuditLog"
    assert audit_adds[0].action == "tenant.erased"
    assert audit_adds[0].tenant_id == tenant_id
    assert audit_adds[0].payload["chunks_deleted"] == 5


@pytest.mark.asyncio
async def test_smoke_erasure_continues_if_redis_fails() -> None:
    """Redis failure must not abort the erasure — report still returns."""
    tenant_id = uuid4()

    class BrokenRedis:
        async def keys(self, pattern: str) -> list:
            raise ConnectionError("redis down")

        async def scan_iter(self, match: str) -> list:
            raise ConnectionError("redis down")

    session = FakeSession(
        results=[
            FakeResult(rowcount=0),
            FakeResult(rowcount=0),
            FakeResult(rowcount=0),
            FakeResult(rowcount=0),
            FakeResult(rowcount=0),
        ]
    )

    report = await erase_tenant(
        tenant_id=tenant_id,
        actor_id=uuid4(),
        actor_role="superadmin",
        session=cast(AsyncSession, session),
        redis=cast(RedisMemoryClient, BrokenRedis()),
        minio=cast(object, FakeMinio(objects_deleted=0)),
    )

    assert report.redis_sessions_deleted == 0
