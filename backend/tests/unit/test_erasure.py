from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.minio import MinioClient
from app.services.erasure import ErasureReport, erase_tenant
from app.services.memory import RedisMemoryClient

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeTransaction:
    async def __aenter__(self) -> "_FakeTransaction":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class FakeSession:
    def __init__(self) -> None:
        self.execute_calls: list[dict] = []

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction()

    async def execute(self, stmt: object, params: object = None) -> None:
        self.execute_calls.append({"stmt": stmt, "params": params})

    def add(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass


class FakeRedis:
    def __init__(self, session_count: int = 3) -> None:
        self._count = session_count

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        if cursor == 0 and self._count > 0:
            return 0, [f"session:key:{i}" for i in range(self._count)]
        return 0, []

    async def delete(self, *names: str) -> int:
        return len(names)


class FakeMinio:
    def __init__(self, object_count: int = 5) -> None:
        self._count = object_count
        self.called_with: list[UUID] = []

    async def delete_tenant_prefix(self, tenant_id: UUID) -> int:
        self.called_with.append(tenant_id)
        return self._count


def _patch_repos(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chunks: int = 10,
    content_items: int = 3,
    leads: int = 2,
    widget_configs: int = 1,
    call_order: list[str] | None = None,
) -> None:
    async def fake_chunks(session: object, tenant_id: object) -> int:
        if call_order is not None:
            call_order.append("chunks")
        return chunks

    async def fake_content(session: object, tenant_id: object) -> int:
        if call_order is not None:
            call_order.append("content_items")
        return content_items

    async def fake_leads(session: object, tenant_id: object) -> int:
        if call_order is not None:
            call_order.append("leads")
        return leads

    async def fake_widget_configs(session: object, tenant_id: object) -> int:
        if call_order is not None:
            call_order.append("widget_configs")
        return widget_configs

    async def fake_audit_create(session: object, **kwargs: object) -> object:
        return object()

    monkeypatch.setattr("app.services.erasure.chunk_repo.delete_by_tenant", fake_chunks)
    monkeypatch.setattr(
        "app.services.erasure.content_repo.delete_by_tenant", fake_content
    )
    monkeypatch.setattr("app.services.erasure.lead_repo.delete_by_tenant", fake_leads)
    monkeypatch.setattr(
        "app.services.erasure.widget_config_repo.delete_by_tenant", fake_widget_configs
    )
    monkeypatch.setattr("app.services.erasure.audit_repo.create", fake_audit_create)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_erase_tenant_returns_correct_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_repos(monkeypatch, chunks=10, content_items=3, leads=2, widget_configs=1)

    report = await erase_tenant(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        actor_role="tenant_manager",
        session=cast(AsyncSession, FakeSession()),
        redis=cast(RedisMemoryClient, FakeRedis(session_count=4)),
        minio=cast(MinioClient, FakeMinio(object_count=7)),
    )

    assert isinstance(report, ErasureReport)
    assert report.chunks_deleted == 10
    assert report.content_items_deleted == 3
    assert report.leads_deleted == 2
    assert report.widget_configs_deleted == 1
    assert report.redis_sessions_deleted == 4
    assert report.minio_objects_deleted == 7


@pytest.mark.asyncio
async def test_erase_tenant_sets_rls_for_target_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_repos(monkeypatch)
    tenant_id = uuid4()
    session = FakeSession()

    await erase_tenant(
        tenant_id=tenant_id,
        actor_id=uuid4(),
        actor_role="tenant_manager",
        session=cast(AsyncSession, session),
        redis=cast(RedisMemoryClient, FakeRedis()),
        minio=cast(MinioClient, FakeMinio()),
    )

    # First execute call must set the RLS config to the target tenant.
    assert session.execute_calls, "session.execute was never called"
    first_params = session.execute_calls[0]["params"]
    assert first_params == {"tid": str(tenant_id)}


@pytest.mark.asyncio
async def test_erase_tenant_deletes_chunks_before_content_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    _patch_repos(monkeypatch, call_order=order)

    await erase_tenant(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        actor_role="tenant_manager",
        session=cast(AsyncSession, FakeSession()),
        redis=cast(RedisMemoryClient, FakeRedis()),
        minio=cast(MinioClient, FakeMinio()),
    )

    chunks_idx = order.index("chunks")
    content_idx = order.index("content_items")
    assert chunks_idx < content_idx, (
        "chunks must be deleted before content_items (FK order)"
    )


@pytest.mark.asyncio
async def test_erase_tenant_writes_audit_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_calls: list[dict] = []

    async def capturing_audit_create(session: object, **kwargs: object) -> object:
        audit_calls.append(kwargs)
        return object()

    _patch_repos(monkeypatch)
    monkeypatch.setattr(
        "app.services.erasure.audit_repo.create",
        capturing_audit_create,
    )
    tenant_id = uuid4()
    actor_id = uuid4()

    await erase_tenant(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role="tenant_manager",
        session=cast(AsyncSession, FakeSession()),
        redis=cast(RedisMemoryClient, FakeRedis()),
        minio=cast(MinioClient, FakeMinio()),
    )

    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["action"] == "tenant.erased"
    assert call["tenant_id"] == tenant_id
    assert call["actor_id"] == actor_id
    assert call["actor_role"] == "tenant_manager"
    assert "chunks_deleted" in call["payload"]


@pytest.mark.asyncio
async def test_erase_tenant_redis_failure_does_not_abort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_repos(monkeypatch)

    class BrokenRedis:
        async def scan(self, **kwargs: object) -> tuple:
            raise ConnectionError("Redis unreachable")

        async def delete(self, *names: str) -> int:
            return 0

    report = await erase_tenant(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        actor_role="tenant_manager",
        session=cast(AsyncSession, FakeSession()),
        redis=cast(RedisMemoryClient, BrokenRedis()),
        minio=cast(MinioClient, FakeMinio()),
    )

    assert isinstance(report, ErasureReport)
    assert report.redis_sessions_deleted == 0
    assert report.minio_objects_deleted == 5  # MinIO still ran


@pytest.mark.asyncio
async def test_erase_tenant_minio_failure_does_not_abort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_repos(monkeypatch)

    class BrokenMinio:
        async def delete_tenant_prefix(self, tenant_id: UUID) -> int:
            raise OSError("MinIO unreachable")

    report = await erase_tenant(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        actor_role="tenant_manager",
        session=cast(AsyncSession, FakeSession()),
        redis=cast(RedisMemoryClient, FakeRedis(session_count=2)),
        minio=cast(MinioClient, BrokenMinio()),
    )

    assert isinstance(report, ErasureReport)
    assert report.minio_objects_deleted == 0
    assert report.redis_sessions_deleted == 2  # Redis still ran


@pytest.mark.asyncio
async def test_erase_tenant_report_carries_tenant_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_repos(monkeypatch)
    tenant_id = uuid4()

    report = await erase_tenant(
        tenant_id=tenant_id,
        actor_id=uuid4(),
        actor_role="tenant_manager",
        session=cast(AsyncSession, FakeSession()),
        redis=cast(RedisMemoryClient, FakeRedis()),
        minio=cast(MinioClient, FakeMinio()),
    )

    assert report.tenant_id == tenant_id
