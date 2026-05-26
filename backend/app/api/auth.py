"""Auth router — login/register/me via fastapi-users."""

from fastapi import APIRouter

from app.db.user_manager import auth_backend, fastapi_users
from app.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter()

# POST /auth/login, POST /auth/logout
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth",
    tags=["auth"],
)

# POST /auth/register
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

# GET /users/me, PATCH /users/me, GET /users/{id}
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
