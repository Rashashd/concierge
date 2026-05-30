"""Smoke tests for the content management pipeline.

Calls the real route handlers + real repo functions against a fake session.
Verifies the full create → list → update → delete lifecycle without a live DB.
"""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.content import create_content, delete_content, list_content, update_content
from app.db.models import ContentItem
from app.schemas import ContentCreate, ContentUpdate, UserContext

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
    def __init__(self, results: list[FakeResult] | None = None) -> None:
        self.added: list = []
        self._results: list[FakeResult] = list(results or [])

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
        for field in ("created_at", "updated_at"):
            if not getattr(obj, field, None):
                try:
                    setattr(obj, field, now)
                except Exception:
                    pass

    async def execute(
        self, stmt: object, *args: object, **kwargs: object
    ) -> FakeResult:
        if self._results:
            return self._results.pop(0)
        return FakeResult()


def _admin(tenant_id: object = None) -> UserContext:
    return UserContext(
        user_id=uuid4(),
        role="tenant_admin",
        tenant_id=tenant_id or uuid4(),
    )


def _item(tenant_id: object) -> ContentItem:
    item = ContentItem(
        tenant_id=tenant_id,  # type: ignore[arg-type]
        title="FAQ",
        body="We are open 9-5.",
        content_type="faq",
    )
    item.id = uuid4()  # type: ignore[assignment]
    item.created_at = datetime.now(UTC)
    item.updated_at = datetime.now(UTC)
    return item


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_smoke_create_content_persists_item_with_correct_tenant(monkeypatch) -> None:
    user = _admin()
    session = FakeSession()
    monkeypatch.setattr("app.api.content.indexing.index_content", AsyncMock())

    result = await create_content(
        ContentCreate(title="FAQ", body="Open 9-5.", content_type="faq"),
        user,
        cast(AsyncSession, session),
        AsyncMock(),
        MagicMock(delete_content=AsyncMock()),
    )

    assert result.title == "FAQ"
    assert result.content_type == "faq"

    content_adds = [o for o in session.added if isinstance(o, ContentItem)]
    assert len(content_adds) == 1
    assert content_adds[0].tenant_id == user.tenant_id


@pytest.mark.asyncio
async def test_smoke_list_content_returns_tenant_items() -> None:
    user = _admin()
    items = [_item(user.tenant_id), _item(user.tenant_id)]
    session = FakeSession(results=[FakeResult(rows=items)])

    result = await list_content(user, cast(AsyncSession, session))

    assert len(result) == 2
    assert all(r.title == "FAQ" for r in result)


@pytest.mark.asyncio
async def test_smoke_update_content_applies_change(monkeypatch) -> None:
    user = _admin()
    item = _item(user.tenant_id)
    session = FakeSession(results=[FakeResult(rows=[item])])
    monkeypatch.setattr("app.api.content.indexing.index_content", AsyncMock())

    result = await update_content(
        item.id,  # type: ignore[arg-type]
        ContentUpdate(title="Updated FAQ", body=None, content_type=None),
        user,
        cast(AsyncSession, session),
        AsyncMock(),
        MagicMock(delete_content=AsyncMock()),
    )

    assert result.title == "Updated FAQ"
    assert result.body == "We are open 9-5."


@pytest.mark.asyncio
async def test_smoke_update_content_raises_404_when_item_not_found(monkeypatch) -> None:
    user = _admin()
    session = FakeSession(results=[FakeResult(rows=[])])
    monkeypatch.setattr("app.api.content.indexing.index_content", AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await update_content(
            uuid4(),
            ContentUpdate(title="X", body=None, content_type=None),
            user,
            cast(AsyncSession, session),
            AsyncMock(),
            MagicMock(delete_content=AsyncMock()),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_smoke_delete_content_returns_none_on_success() -> None:
    user = _admin()
    # First execute: chunk delete (rowcount ignored). Second: content delete (rowcount=1).
    session = FakeSession(results=[FakeResult(rowcount=0), FakeResult(rowcount=1)])
    minio = MagicMock(delete_content=AsyncMock())

    result = await delete_content(uuid4(), user, cast(AsyncSession, session), minio)

    assert result is None


@pytest.mark.asyncio
async def test_smoke_delete_content_raises_404_when_not_found() -> None:
    user = _admin()
    session = FakeSession(results=[FakeResult(rowcount=0), FakeResult(rowcount=0)])
    minio = MagicMock(delete_content=AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await delete_content(uuid4(), user, cast(AsyncSession, session), minio)

    assert exc_info.value.status_code == 404
