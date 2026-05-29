from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.content import router
from app.schemas import ContentCreate, ContentUpdate, UserContext


def _make_admin_context() -> UserContext:
    return UserContext(
        user_id=uuid4(),
        role="tenant_admin",
        tenant_id=uuid4(),
    )


def _fake_item(
    item_id: uuid4,
    tenant_id: uuid4,
    title: str = "Test FAQ",
) -> object:
    dt = type("dt", (), {"isoformat": lambda s: "2025-01-01T00:00:00"})
    return type(
        "FakeContentItem",
        (),
        {
            "id": item_id,
            "tenant_id": tenant_id,
            "title": title,
            "body": "Some body text.",
            "content_type": "faq",
            "created_at": dt(),
            "updated_at": dt(),
        },
    )()


@pytest.mark.asyncio
async def test_create_content_uses_admin_tenant_id() -> None:
    admin = _make_admin_context()
    item_id = uuid4()
    item = _fake_item(item_id, admin.tenant_id)

    async def fake_create(*, session, tenant_id, title, body, content_type) -> object:
        assert tenant_id == admin.tenant_id
        return item

    with (
        patch(
            "app.api.content.content_repo.create",
            side_effect=fake_create,
        ),
        patch(
            "app.api.content.get_admin_tenant_session",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        body = ContentCreate(
            title="FAQ Item", body="This is the answer.", content_type="faq"
        )
        coro = router.routes[0].endpoint  # type: ignore[attr-defined]
        result = await coro(
            body=body,
            user=admin,
            session=AsyncMock(),
        )
        assert result.id == item_id
        assert result.title == "Test FAQ"


@pytest.mark.asyncio
async def test_list_content_filters_by_admin_tenant() -> None:
    admin = _make_admin_context()
    item_id = uuid4()

    async def fake_list(*, session, tenant_id) -> list[object]:
        assert tenant_id == admin.tenant_id
        return [_fake_item(item_id, admin.tenant_id)]

    with (
        patch(
            "app.api.content.content_repo.list_by_tenant",
            side_effect=fake_list,
        ),
        patch(
            "app.api.content.get_admin_tenant_session",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        coro = router.routes[1].endpoint  # type: ignore[attr-defined]
        result = await coro(
            user=admin,
            session=AsyncMock(),
        )
        assert len(result) == 1
        assert result[0].id == item_id


@pytest.mark.asyncio
async def test_update_content_uses_admin_tenant() -> None:
    admin = _make_admin_context()
    item_id = uuid4()

    async def fake_update(
        *,
        session,
        tenant_id,
        content_id,
        title,
        body,
        content_type,
    ) -> object:
        assert tenant_id == admin.tenant_id
        assert content_id == item_id
        return _fake_item(item_id, admin.tenant_id, title=title or "Updated")

    with (
        patch(
            "app.api.content.content_repo.update",
            side_effect=fake_update,
        ),
        patch(
            "app.api.content.get_admin_tenant_session",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        body = ContentUpdate(title="Updated FAQ")
        coro = router.routes[2].endpoint  # type: ignore[attr-defined]
        result = await coro(
            content_id=item_id,
            body=body,
            user=admin,
            session=AsyncMock(),
        )
        assert result.title == "Updated FAQ"


@pytest.mark.asyncio
async def test_update_content_404_when_missing() -> None:
    admin = _make_admin_context()

    async def fake_update(
        *,
        session,
        tenant_id,
        content_id,
        title,
        body,
        content_type,
    ) -> None:
        return None

    with (
        patch(
            "app.api.content.content_repo.update",
            side_effect=fake_update,
        ),
        patch(
            "app.api.content.get_admin_tenant_session",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        body = ContentUpdate(title="Updated")
        coro = router.routes[2].endpoint  # type: ignore[attr-defined]
        with pytest.raises(HTTPException) as exc_info:
            await coro(
                content_id=uuid4(),
                body=body,
                user=admin,
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_content_uses_admin_tenant() -> None:
    admin = _make_admin_context()
    item_id = uuid4()

    async def fake_delete(*, session, tenant_id, content_id) -> bool:
        assert tenant_id == admin.tenant_id
        assert content_id == item_id
        return True

    with (
        patch(
            "app.api.content.content_repo.delete_by_id",
            side_effect=fake_delete,
        ),
        patch(
            "app.api.content.get_admin_tenant_session",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        coro = router.routes[3].endpoint  # type: ignore[attr-defined]
        result = await coro(
            content_id=item_id,
            user=admin,
            session=AsyncMock(),
        )
        assert result is None


@pytest.mark.asyncio
async def test_delete_content_404_when_missing() -> None:
    admin = _make_admin_context()

    async def fake_delete(*, session, tenant_id, content_id) -> bool:
        return False

    with (
        patch(
            "app.api.content.content_repo.delete_by_id",
            side_effect=fake_delete,
        ),
        patch(
            "app.api.content.get_admin_tenant_session",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        coro = router.routes[3].endpoint  # type: ignore[attr-defined]
        with pytest.raises(HTTPException) as exc_info:
            await coro(
                content_id=uuid4(),
                user=admin,
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 404
