from fnmatch import fnmatch
from uuid import uuid4

import pytest

from app.services.memory import (
    build_session_key,
    build_tenant_session_pattern,
    delete_tenant_sessions,
    load_history,
    save_turn,
)


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str | bytes]] = {}
        self.ttls: dict[str, int] = {}
        self.deleted_names: list[str] = []
        self._scan_keys: list[str | bytes] = []

    async def rpush(self, name: str, *values: str) -> int:
        self.lists.setdefault(name, []).extend(values)
        return len(self.lists[name])

    async def expire(self, name: str, time: int) -> bool:
        self.ttls[name] = time
        return True

    async def lrange(self, name: str, start: int, end: int) -> list[str | bytes]:
        values = self.lists.get(name, [])
        if start < 0:
            start = max(len(values) + start, 0)
        if end < 0:
            end = len(values) + end
        return values[start : end + 1]

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str | bytes]]:
        if cursor == 0:
            self._scan_keys = []
            for key in sorted(self.lists):
                if match is None or fnmatch(key, match):
                    self._scan_keys.append(key)
        batch_size = count or len(self._scan_keys) or 1
        batch: list[str | bytes] = self._scan_keys[cursor : cursor + batch_size]
        next_cursor = cursor + batch_size
        if next_cursor >= len(self._scan_keys):
            next_cursor = 0
            self._scan_keys = []
        return next_cursor, batch

    async def delete(self, *names: str) -> int:
        for name in names:
            assert "*" not in name

        deleted = 0
        for name in names:
            if name in self.lists:
                deleted += 1
                self.deleted_names.append(name)
                del self.lists[name]
        return deleted


def test_memory_key_format_is_tenant_scoped() -> None:
    tenant_id = uuid4()

    assert build_session_key(tenant_id, "visitor-1") == (
        f"session:{tenant_id}:visitor-1"
    )
    assert build_tenant_session_pattern(tenant_id) == f"session:{tenant_id}:*"


@pytest.mark.asyncio
async def test_save_turn_and_load_history_round_trip() -> None:
    redis = FakeRedis()
    tenant_id = uuid4()

    await save_turn(
        redis=redis,
        tenant_id=tenant_id,
        session_id="visitor-1",
        user_message="Hello",
        assistant_message="Hi, how can I help?",
        ttl_seconds=60,
    )

    history = await load_history(
        redis=redis,
        tenant_id=tenant_id,
        session_id="visitor-1",
    )

    assert [(message.role, message.content) for message in history] == [
        ("user", "Hello"),
        ("assistant", "Hi, how can I help?"),
    ]
    assert redis.ttls[f"session:{tenant_id}:visitor-1"] == 60


@pytest.mark.asyncio
async def test_delete_tenant_sessions_deletes_only_matching_tenant_prefix() -> None:
    redis = FakeRedis()
    tenant_id = uuid4()
    other_tenant_id = uuid4()

    redis.lists = {
        f"session:{tenant_id}:a": ["{}"],
        f"session:{tenant_id}:b": ["{}"],
        f"session:{other_tenant_id}:a": ["{}"],
        "unrelated:key": ["{}"],
    }

    deleted = await delete_tenant_sessions(
        redis=redis,
        tenant_id=tenant_id,
        scan_count=1,
    )

    assert deleted == 2
    assert sorted(redis.deleted_names) == [
        f"session:{tenant_id}:a",
        f"session:{tenant_id}:b",
    ]
    assert f"session:{other_tenant_id}:a" in redis.lists
    assert "unrelated:key" in redis.lists
