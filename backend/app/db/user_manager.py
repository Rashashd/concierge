"""fastapi-users wiring: UserDatabase adapter, UserManager, auth backend."""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from app.core.config import Settings, get_settings
from app.db.models import User


async def get_user_db(
    request: Request,
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID], None]:  # type: ignore[type-var]
    """SQLAlchemy adapter using the lifespan session factory."""
    async with request.app.state.session_factory() as session:
        yield SQLAlchemyUserDatabase(session, User)  # type: ignore[type-var]


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):  # type: ignore[type-var]
    """Reads reset/verification secrets from settings at instantiation time."""

    # Class-level placeholders — overridden per-instance in __init__
    reset_password_token_secret: str = ""
    verification_token_secret: str = ""

    def __init__(
        self,
        user_db: SQLAlchemyUserDatabase,  # type: ignore[type-arg]
        secret: str,
    ) -> None:
        super().__init__(user_db)
        self.reset_password_token_secret = secret
        self.verification_token_secret = secret

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        pass


async def get_user_manager(
    user_db: Annotated[SQLAlchemyUserDatabase, Depends(get_user_db)],  # type: ignore[type-arg]
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db, settings.backend_secret_key.get_secret_value())


# Auth backend — secret read at request time so Vault-loaded values are used

_bearer = BearerTransport(tokenUrl="/auth/login")


def _get_jwt_strategy(
    settings: Annotated[Settings, Depends(get_settings)],
) -> JWTStrategy:  # type: ignore[type-arg]
    return JWTStrategy(
        secret=settings.backend_secret_key.get_secret_value(),
        lifetime_seconds=3600,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=_bearer,
    get_strategy=_get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])  # type: ignore[type-var]
