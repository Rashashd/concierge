"""Integration tests for the content repository — tenant scoping and partial update."""

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentItem
from app.repositories import content as content_repo


class FakeResult:
    def __init__(self, rows: list, rowcount: int = 1) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object:
        return self._rows[0] if self._rows else None

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list:
        return self._rows


class FakeSession:
    def __init__(self, rows: list | None = None, rowcount: int = 1) -> None:
        self.added: list = []
        self._rows = rows or []
        self._rowcount = rowcount
        self.last_stmt: object = None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def execute(self, stmt: object) -> FakeResult:
        self.last_stmt = stmt
        return FakeResult(self._rows, self._rowcount)


@pytest.mark.asyncio
async def test_create_sets_all_fields() -> None:
    tenant_id = uuid4()
    session = FakeSession()

    item = await content_repo.create(
        cast(AsyncSession, session),
        tenant_id=tenant_id,
        title="FAQ",
        body="We are open 9-5.",
        content_type="faq",
    )

    assert item.tenant_id == tenant_id
    assert item.title == "FAQ"
    assert item.body == "We are open 9-5."
    assert item.content_type == "faq"
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_get_by_id_scopes_by_both_content_id_and_tenant_id() -> None:
    tenant_id = uuid4()
    content_id = uuid4()
    fake_item = ContentItem(
        tenant_id=tenant_id, title="T", body="B", content_type="faq"
    )
    session = FakeSession(rows=[fake_item])

    result = await content_repo.get_by_id(
        cast(AsyncSession, session), tenant_id, content_id
    )

    assert result is fake_item
    where_str = str(session.last_stmt.whereclause)
    assert "tenant_id" in where_str
    assert "content_items.id" in where_str


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_not_found() -> None:
    session = FakeSession(rows=[])
    result = await content_repo.get_by_id(cast(AsyncSession, session), uuid4(), uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_update_applies_only_provided_fields() -> None:
    tenant_id = uuid4()
    fake_item = ContentItem(
        tenant_id=tenant_id, title="Old Title", body="Old Body", content_type="faq"
    )
    session = FakeSession(rows=[fake_item])

    result = await content_repo.update(
        cast(AsyncSession, session),
        tenant_id,
        uuid4(),
        title="New Title",
    )

    assert result is fake_item
    assert result.title == "New Title"
    assert result.body == "Old Body"
    assert result.content_type == "faq"


@pytest.mark.asyncio
async def test_update_returns_none_when_item_not_found() -> None:
    session = FakeSession(rows=[])
    result = await content_repo.update(
        cast(AsyncSession, session), uuid4(), uuid4(), title="X"
    )
    assert result is None


@pytest.mark.asyncio
async def test_delete_by_id_scopes_where_clause_by_tenant() -> None:
    session = FakeSession(rows=[], rowcount=1)

    deleted = await content_repo.delete_by_id(
        cast(AsyncSession, session), uuid4(), uuid4()
    )

    assert deleted is True
    where_str = str(session.last_stmt.whereclause)
    assert "tenant_id" in where_str
    assert "content_items.id" in where_str


@pytest.mark.asyncio
async def test_delete_by_id_returns_false_when_nothing_deleted() -> None:
    session = FakeSession(rows=[], rowcount=0)
    deleted = await content_repo.delete_by_id(
        cast(AsyncSession, session), uuid4(), uuid4()
    )
    assert deleted is False
