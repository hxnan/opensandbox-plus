from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total: int = Field(ge=0)


class CurrentUserResponse(BaseModel):
    subject_id: str
    username: str | None = None
    email: str | None = None
    display_name: str | None = None
    roles: list[str]
    features: dict[str, bool]


class CredentialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    agent_id: str | None = Field(default=None, max_length=128)
    expires_in_days: int | None = Field(default=None, ge=1)


class CredentialCreateResponse(BaseModel):
    id: str
    name: str
    public_prefix: str
    key: str
    status: str
    expires_at: datetime | None = None
    created_at: datetime


class CredentialSummary(BaseModel):
    id: str
    name: str
    public_prefix: str
    status: str
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    issued_by_agent_id: str | None = None
    created_at: datetime


class AdminCredentialSummary(CredentialSummary):
    owner_subject_id: str


class StatusResponse(BaseModel):
    id: str
    status: str
    updated_at: datetime


class AdminUserSummaryResponse(BaseModel):
    subject_id: str
    casdoor_owner: str
    casdoor_user: str
    username: str | None = None
    email: str | None = None
    display_name: str | None = None
    status: str
    roles: list[str]
    active_credentials: int
    active_sandboxes: int
    created_at: datetime
    updated_at: datetime


QuotaScopeType = Literal["global", "user"]


class QuotaRuleRequest(BaseModel):
    scope_type: QuotaScopeType
    scope_id: str = Field(min_length=1, max_length=256)
    max_running_sandboxes: int | None = Field(default=None, ge=0)
    max_timeout_seconds: int | None = Field(default=None, ge=1)
    max_create_per_minute: int | None = Field(default=None, ge=0)
    allowed_runtime_profile_ids: list[str] | None = None
    allowed_image_patterns: list[str] | None = None


class QuotaRuleResponse(BaseModel):
    id: str
    scope_type: QuotaScopeType
    scope_id: str
    max_running_sandboxes: int | None = None
    max_timeout_seconds: int | None = None
    max_create_per_minute: int | None = None
    allowed_runtime_profile_ids: list[str] | None = None
    allowed_image_patterns: list[str] | None = None
    created_at: datetime
    updated_at: datetime


AuditDecision = Literal["allow", "deny", "error"]


class AuditEventResponse(BaseModel):
    id: int
    request_id: str
    actor_subject_id: str | None = None
    credential_id: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    decision: AuditDecision
    ip: str | None = None
    user_agent: str | None = None
    error_code: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime
