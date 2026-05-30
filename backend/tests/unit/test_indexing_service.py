"""Unit tests for the indexing service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.indexing import _embed_item, index_content, reindex_tenant


def _session() -> MagicMock:
    return MagicMock()


def _embeddings(vectors=None) -> MagicMock:
    e = MagicMock()
    e.aembed_documents = AsyncMock(return_value=vectors or [[0.1, 0.2, 0.3]])
    return e


def _embeddings_no_fn() -> MagicMock:
    return MagicMock(spec=[])  # no aembed_documents attribute


# _embed_item


@pytest.mark.asyncio
async def test_embed_item_skips_when_no_embed_fn(monkeypatch) -> None:
    delete_mock = AsyncMock()
    create_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.indexing.chunk_repo.delete_by_content_item", delete_mock
    )
    monkeypatch.setattr("app.services.indexing.chunk_repo.create_bulk", create_mock)

    await _embed_item(_session(), _embeddings_no_fn(), uuid4(), uuid4(), "T", "B")

    delete_mock.assert_not_called()
    create_mock.assert_not_called()


@pytest.mark.asyncio
async def test_embed_item_deletes_old_chunks_then_creates_new(monkeypatch) -> None:
    tenant_id, content_id = uuid4(), uuid4()
    vectors = [[0.1, 0.2]]
    delete_mock = AsyncMock()
    create_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.indexing.chunk_repo.delete_by_content_item", delete_mock
    )
    monkeypatch.setattr("app.services.indexing.chunk_repo.create_bulk", create_mock)
    session = _session()

    await _embed_item(
        session, _embeddings(vectors), tenant_id, content_id, "Title", "Body"
    )

    delete_mock.assert_awaited_once_with(session, tenant_id, content_id)
    create_mock.assert_awaited_once()
    kwargs = create_mock.call_args.kwargs
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["content_item_id"] == content_id
    assert kwargs["embeddings"] == vectors


@pytest.mark.asyncio
async def test_embed_item_concatenates_title_and_body(monkeypatch) -> None:
    captured: list[str] = []

    async def fake_embed(texts):
        captured.extend(texts)
        return [[0.0]]

    embeddings = MagicMock()
    embeddings.aembed_documents = fake_embed
    monkeypatch.setattr(
        "app.services.indexing.chunk_repo.delete_by_content_item", AsyncMock()
    )
    monkeypatch.setattr("app.services.indexing.chunk_repo.create_bulk", AsyncMock())

    await _embed_item(_session(), embeddings, uuid4(), uuid4(), "My Title", "My Body")

    assert captured == ["My Title\n\nMy Body"]


# index_content


@pytest.mark.asyncio
async def test_index_content_writes_minio_blob(monkeypatch) -> None:
    tenant_id, content_id = uuid4(), uuid4()
    minio = MagicMock()
    minio.put_content = AsyncMock()
    monkeypatch.setattr(
        "app.services.indexing.chunk_repo.delete_by_content_item", AsyncMock()
    )
    monkeypatch.setattr("app.services.indexing.chunk_repo.create_bulk", AsyncMock())

    await index_content(
        _session(),
        _embeddings(),
        minio,
        tenant_id,
        content_id,
        "Title",
        "Body",
        "faq",
    )

    minio.put_content.assert_awaited_once()
    payload = minio.put_content.call_args.kwargs["payload"]
    assert payload["id"] == str(content_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["title"] == "Title"
    assert payload["content_type"] == "faq"


@pytest.mark.asyncio
async def test_index_content_calls_embed_after_minio(monkeypatch) -> None:
    call_order: list[str] = []
    minio = MagicMock()

    async def fake_put(*args, **kwargs):
        call_order.append("minio")

    async def fake_delete(*args, **kwargs):
        call_order.append("delete_chunks")

    minio.put_content = fake_put
    monkeypatch.setattr(
        "app.services.indexing.chunk_repo.delete_by_content_item", fake_delete
    )
    monkeypatch.setattr("app.services.indexing.chunk_repo.create_bulk", AsyncMock())

    await index_content(
        _session(), _embeddings(), minio, uuid4(), uuid4(), "T", "B", "page"
    )

    assert call_order[0] == "minio"
    assert "delete_chunks" in call_order


# reindex_tenant


@pytest.mark.asyncio
async def test_reindex_tenant_embeds_all_items(monkeypatch) -> None:
    tenant_id = uuid4()
    items = [
        type("Item", (), {"id": uuid4(), "title": "T1", "body": "B1"})(),
        type("Item", (), {"id": uuid4(), "title": "T2", "body": "B2"})(),
    ]
    monkeypatch.setattr(
        "app.services.indexing.content_repo.list_by_tenant",
        AsyncMock(return_value=items),
    )
    embed_calls: list[tuple] = []

    async def fake_embed_item(session, embeddings, t_id, c_id, title, body):
        embed_calls.append((c_id, title))

    monkeypatch.setattr("app.services.indexing._embed_item", fake_embed_item)

    await reindex_tenant(_session(), MagicMock(), tenant_id)

    assert len(embed_calls) == 2
    assert embed_calls[0][1] == "T1"
    assert embed_calls[1][1] == "T2"


@pytest.mark.asyncio
async def test_reindex_tenant_handles_no_content(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.indexing.content_repo.list_by_tenant", AsyncMock(return_value=[])
    )
    embed_mock = AsyncMock()
    monkeypatch.setattr("app.services.indexing._embed_item", embed_mock)

    await reindex_tenant(_session(), MagicMock(), uuid4())

    embed_mock.assert_not_called()
