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


ClusterKind = Literal["docker", "kubernetes", "remote"]
ClusterStatus = Literal["active", "disabled", "draining"]
ClusterHealthStatus = Literal["unknown", "healthy", "unhealthy"]


class ClusterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    region: str | None = Field(default=None, max_length=128)
    kind: ClusterKind = "remote"
    status: ClusterStatus = "active"
    provider: str | None = Field(default=None, max_length=64)
    external_cluster_id: str | None = Field(default=None, max_length=256)
    namespace: str | None = Field(default=None, max_length=128)
    registry_url: str | None = Field(default=None, max_length=512)
    kubeconfig_secret_ref: str | None = Field(default=None, max_length=256)
    opensandbox_base_url: str = Field(min_length=1, max_length=512)
    api_key_env: str = Field(min_length=1, max_length=128)
    weight: int = Field(default=100, ge=0)
    capabilities: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ClusterResponse(BaseModel):
    id: str
    name: str
    region: str | None = None
    kind: ClusterKind
    status: ClusterStatus
    health_status: ClusterHealthStatus
    provider: str | None = None
    external_cluster_id: str | None = None
    namespace: str | None = None
    registry_url: str | None = None
    kubeconfig_secret_ref: str | None = None
    opensandbox_base_url: str
    api_key_env: str
    weight: int
    capabilities: dict[str, Any]
    metadata: dict[str, Any]
    last_checked_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


AckDeploymentStatus = Literal[
    "draft",
    "prechecking",
    "ready",
    "deploying",
    "deployed",
    "failed",
    "disabled",
]


class AckDeploymentRequest(BaseModel):
    runtime_backend_id: str | None = Field(default=None, max_length=128)
    aliyun_cluster_id: str = Field(min_length=1, max_length=256)
    region: str = Field(min_length=1, max_length=128)
    namespace: str = Field(default="opensandbox", min_length=1, max_length=128)
    vpc_id: str | None = Field(default=None, max_length=128)
    registry_url: str | None = Field(default=None, max_length=512)
    kubeconfig_secret_ref: str | None = Field(default=None, max_length=256)
    precheck_payload: dict[str, Any] | None = None
    deployment_payload: dict[str, Any] | None = None


class AckDeploymentResponse(BaseModel):
    id: str
    runtime_backend_id: str | None = None
    aliyun_cluster_id: str
    region: str
    namespace: str
    vpc_id: str | None = None
    registry_url: str | None = None
    kubeconfig_secret_ref: str | None = None
    status: AckDeploymentStatus
    precheck_payload: dict[str, Any] | None = None
    deployment_payload: dict[str, Any] | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


ImageSourceType = Literal["manual_upload", "external_registry"]
ImageRiskLevel = Literal["low", "medium", "high"]
ImageStatus = Literal["draft", "active", "disabled"]
ImageDistributionStatus = Literal["pending", "uploading", "available", "failed", "disabled"]


class SandboxImageRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=128)
    source_type: ImageSourceType = "manual_upload"
    source_uri: str | None = Field(default=None, max_length=1024)
    architecture: str = Field(default="amd64", min_length=1, max_length=64)
    runtime_profile_id: str | None = Field(default=None, max_length=128)
    risk_level: ImageRiskLevel = "low"
    status: ImageStatus = "draft"
    description: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, Any] | None = None


class SandboxImageResponse(BaseModel):
    id: str
    name: str
    version: str
    source_type: ImageSourceType
    source_uri: str | None = None
    architecture: str
    runtime_profile_id: str | None = None
    risk_level: ImageRiskLevel
    status: ImageStatus
    description: str | None = None
    created_by_subject_id: str | None = None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ImageDistributionResponse(BaseModel):
    id: str
    image_id: str
    runtime_backend_id: str
    registry_url: str | None = None
    target_ref: str | None = None
    status: ImageDistributionStatus
    retry_count: int
    last_error: str | None = None
    last_synced_at: datetime | None = None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SandboxImageUploadResponse(BaseModel):
    image: SandboxImageResponse
    distributions: list[ImageDistributionResponse]
