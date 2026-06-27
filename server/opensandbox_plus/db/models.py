from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserIdentity(Base, TimestampMixin):
    __tablename__ = "user_identities"
    __table_args__ = (CheckConstraint("status in ('active', 'disabled', 'deleted')"),)

    subject_id: Mapped[str] = mapped_column(Text, primary_key=True)
    casdoor_owner: Mapped[str] = mapped_column(Text, nullable=False)
    casdoor_user: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="active", nullable=False)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}", nullable=False)


class CloudSandboxCredential(Base, TimestampMixin):
    __tablename__ = "cloud_sandbox_credentials"
    __table_args__ = (
        CheckConstraint("status in ('active', 'disabled', 'revoked', 'expired')"),
        CheckConstraint("public_prefix ~ '^[A-Za-z0-9_-]{6,32}$'"),
        UniqueConstraint("owner_subject_id", "name", name="uq_credential_owner_name"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_subject_id: Mapped[str] = mapped_column(ForeignKey("user_identities.subject_id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    public_prefix: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    hash_algorithm: Mapped[str] = mapped_column(Text, server_default="hmac-sha256", nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_ip: Mapped[str | None] = mapped_column(INET)
    issued_by_agent_id: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RuntimeProfile(Base, TimestampMixin):
    __tablename__ = "runtime_profiles"
    __table_args__ = (
        CheckConstraint("status in ('active', 'disabled')"),
        CheckConstraint("timeout_seconds > 0"),
        CheckConstraint("max_renew_seconds is null or max_renew_seconds >= timeout_seconds"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    cpu_limit: Mapped[str | None] = mapped_column(Text)
    memory_limit: Mapped[str | None] = mapped_column(Text)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_renew_seconds: Mapped[int | None] = mapped_column(Integer)
    network_policy: Mapped[dict | None] = mapped_column(JSONB)
    image_policy_id: Mapped[str | None] = mapped_column(Text)
    secure_access_default: Mapped[bool] = mapped_column(server_default="true", nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="active", nullable=False)


class RuntimeBackend(Base, TimestampMixin):
    __tablename__ = "runtime_backends"
    __table_args__ = (
        CheckConstraint("kind in ('docker', 'kubernetes', 'remote')"),
        CheckConstraint("status in ('active', 'disabled', 'draining')"),
        CheckConstraint("health_status in ('unknown', 'healthy', 'unhealthy')"),
        CheckConstraint("weight >= 0"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="active", nullable=False)
    health_status: Mapped[str] = mapped_column(Text, server_default="unknown", nullable=False)
    opensandbox_base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_env: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, server_default="100", nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class Sandbox(Base, TimestampMixin):
    __tablename__ = "sandboxes"
    __table_args__ = (
        CheckConstraint(
            "state in ('pending', 'running', 'paused', 'stopping', 'stopped', "
            "'failed', 'deleted', 'unknown')"
        ),
        CheckConstraint("requested_timeout_seconds is null or requested_timeout_seconds > 0"),
        UniqueConstraint("owner_subject_id", "public_sandbox_id", name="uq_sandbox_owner_public"),
        UniqueConstraint("runtime_backend_id", "opensandbox_id", name="uq_sandbox_backend_open"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    public_sandbox_id: Mapped[str] = mapped_column(Text, nullable=False)
    opensandbox_id: Mapped[str] = mapped_column(Text, nullable=False)
    owner_subject_id: Mapped[str] = mapped_column(ForeignKey("user_identities.subject_id"))
    created_by_credential_id: Mapped[str | None] = mapped_column(
        ForeignKey("cloud_sandbox_credentials.id")
    )
    runtime_backend_id: Mapped[str] = mapped_column(ForeignKey("runtime_backends.id"))
    runtime_profile_id: Mapped[str | None] = mapped_column(ForeignKey("runtime_profiles.id"))
    image: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    requested_timeout_seconds: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_opensandbox_payload: Mapped[dict | None] = mapped_column(JSONB)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SandboxEvent(Base):
    __tablename__ = "sandbox_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sandbox_id: Mapped[str] = mapped_column(ForeignKey("sandboxes.id"))
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    old_state: Mapped[str | None] = mapped_column(Text)
    new_state: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QuotaRule(Base, TimestampMixin):
    __tablename__ = "quota_rules"
    __table_args__ = (
        CheckConstraint("scope_type in ('global', 'user')"),
        CheckConstraint("max_running_sandboxes is null or max_running_sandboxes >= 0"),
        CheckConstraint("max_timeout_seconds is null or max_timeout_seconds > 0"),
        CheckConstraint("max_create_per_minute is null or max_create_per_minute >= 0"),
        UniqueConstraint("scope_type", "scope_id", name="uq_quota_scope"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)
    max_running_sandboxes: Mapped[int | None] = mapped_column(Integer)
    max_timeout_seconds: Mapped[int | None] = mapped_column(Integer)
    max_create_per_minute: Mapped[int | None] = mapped_column(Integer)
    allowed_runtime_profile_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    allowed_image_patterns: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


class QuotaUsage(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (CheckConstraint("value >= 0"),)

    scope_type: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_id: Mapped[str] = mapped_column(Text, primary_key=True)
    metric: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (CheckConstraint("decision in ('allow', 'deny', 'error')"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    actor_subject_id: Mapped[str | None] = mapped_column(Text)
    credential_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
