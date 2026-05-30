"""Widget business logic — config upsert and tenant resolution."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WidgetConfig
from app.repositories import widget_configs as widget_config_repo

logger = structlog.get_logger(__name__)


async def upsert_widget_config(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    greeting: str,
    theme_color: str,
    enabled_tools: list[str],
) -> WidgetConfig:
    """Create or update the widget config for a tenant. Idempotent."""
    async with session.begin():
        existing = await widget_config_repo.get_first_by_tenant(session, tenant_id)
        if existing:
            config = await widget_config_repo.update_fields(
                session,
                existing.widget_id,
                greeting=greeting,
                theme_color=theme_color,
                enabled_tools=enabled_tools,
            )
        else:
            config = await widget_config_repo.create(session, tenant_id=tenant_id)
            config.greeting = greeting
            config.theme_color = theme_color
            config.enabled_tools = enabled_tools
    assert config is not None
    logger.info("widget.config_upserted", tenant_id=str(tenant_id))
    return config


async def resolve_widget_tenant(
    session: AsyncSession,
    widget_id: uuid.UUID,
) -> uuid.UUID:
    """Resolve a widget_id to its tenant_id.

    Looks up the widget_configs table first. Falls back to treating the
    widget_id as a tenant_id directly (used in the demo path where the
    seeder injects the tenant's own UUID as the widget ID).
    """
    config = await widget_config_repo.get_by_widget_id(session, widget_id)
    if config:
        return config.tenant_id
    return widget_id
