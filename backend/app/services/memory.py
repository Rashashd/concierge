import json
from collections.abc import Sequence
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SESSION_KEY_PREFIX = "session"
DEFAULT_SESSION_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MAX_HISTORY_MESSAGES = 200


class RedisMemoryClient(Protocol):
    async def rpush(self, name: str, *values: str) -> object: ...

    async def expire(self, name: str, time: int) -> object: ...

    async def lrange(
        self,
        name: str,
        start: int,
        end: int,
    ) -> Sequence[str | bytes]: ...

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, Sequence[str | bytes]]: ...

    async def delete(self, *names: str) -> int: ...


class MemoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")


def build_session_key(tenant_id: UUID, session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}:{tenant_id}:{session_id}"


def build_tenant_session_pattern(tenant_id: UUID) -> str:
    return f"{SESSION_KEY_PREFIX}:{tenant_id}:*"


async def save_turn(
    redis: RedisMemoryClient,
    tenant_id: UUID,
    session_id: str,
    user_message: str,
    assistant_message: str,
    ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
) -> None:
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be greater than zero.")

    key = build_session_key(tenant_id=tenant_id, session_id=session_id)
    messages = [
        MemoryMessage(role="user", content=user_message),
        MemoryMessage(role="assistant", content=assistant_message),
    ]

    await redis.rpush(key, *(message.model_dump_json() for message in messages))
    await redis.expire(key, ttl_seconds)


async def load_history(
    redis: RedisMemoryClient,
    tenant_id: UUID,
    session_id: str,
    max_messages: int = DEFAULT_MAX_HISTORY_MESSAGES,
) -> list[MemoryMessage]:
    if max_messages <= 0:
        raise ValueError("max_messages must be greater than zero.")

    key = build_session_key(tenant_id=tenant_id, session_id=session_id)
    raw_messages = await redis.lrange(key, 0, -1)
    messages = [_decode_message(raw_message) for raw_message in raw_messages]
    return messages[-max_messages:]


async def delete_tenant_sessions(
    redis: RedisMemoryClient,
    tenant_id: UUID,
    scan_count: int = 100,
) -> int:
    if scan_count <= 0:
        raise ValueError("scan_count must be greater than zero.")

    pattern = build_tenant_session_pattern(tenant_id)
    cursor = 0
    deleted = 0

    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=scan_count)
        if keys:
            deleted += await redis.delete(*[_normalize_key(key) for key in keys])
        if cursor == 0:
            return deleted


def _decode_message(raw_message: str | bytes) -> MemoryMessage:
    try:
        payload = json.loads(_normalize_key(raw_message))
        return MemoryMessage.model_validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        raise ValueError("Stored session memory contains an invalid message.") from exc


def _normalize_key(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value
