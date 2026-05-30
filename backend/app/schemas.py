"""Backward-compat re-export facade — prefer app.domain.* in new code."""

from app.domain.audit import AuditLogResponse, EscalationResponse
from app.domain.chat import ChatRequest, ChatResponse
from app.domain.content import (
    ContentCreate,
    ContentResponse,
    ContentType,
    ContentUpdate,
)
from app.domain.context import TenantContext, UserContext
from app.domain.leads import LeadResponse, LeadStatus, LeadStatusUpdate
from app.domain.tenants import (
    TenantConfigUpdate,
    TenantCostResponse,
    TenantCreate,
    TenantDetail,
    TenantResponse,
    TenantUserResponse,
)
from app.domain.tools import (
    CaptureLeadInput,
    CaptureLeadOutput,
    ChatRouteStatus,
    ChunkReference,
    EscalateInput,
    EscalateOutput,
    RAGSearchInput,
    RAGSearchOutput,
    ToolError,
)
from app.domain.users import UserCreate, UserRead, UserUpdate
from app.domain.widget import (
    WidgetConfigCreate,
    WidgetConfigPublic,
    WidgetTokenRequest,
    WidgetTokenResponse,
)

__all__ = [
    "AuditLogResponse",
    "CaptureLeadInput",
    "CaptureLeadOutput",
    "ChatRequest",
    "ChatResponse",
    "ChatRouteStatus",
    "ChunkReference",
    "ContentCreate",
    "ContentResponse",
    "ContentType",
    "ContentUpdate",
    "EscalateInput",
    "EscalateOutput",
    "EscalationResponse",
    "LeadResponse",
    "LeadStatus",
    "LeadStatusUpdate",
    "RAGSearchInput",
    "RAGSearchOutput",
    "TenantConfigUpdate",
    "TenantContext",
    "TenantCostResponse",
    "TenantCreate",
    "TenantDetail",
    "TenantResponse",
    "TenantUserResponse",
    "ToolError",
    "UserContext",
    "UserCreate",
    "UserRead",
    "UserUpdate",
    "WidgetConfigCreate",
    "WidgetConfigPublic",
    "WidgetTokenRequest",
    "WidgetTokenResponse",
]
