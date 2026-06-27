from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.auth.principal import CloudSandboxPrincipal
from opensandbox_plus.db.models import QuotaRule
from opensandbox_plus.quotas.repository import (
    QuotaScopeType,
    count_active_sandboxes,
    count_created_sandboxes_since,
    get_quota_rule,
    list_quota_rules as list_quota_rules_from_db,
    upsert_quota_rule,
)

DEFAULT_MAX_RUNNING_SANDBOXES = 10
DEFAULT_MAX_TIMEOUT_SECONDS = 3600
DEFAULT_MAX_CREATE_PER_MINUTE = 20
GLOBAL_SCOPE_ID = "*"


class QuotaServiceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


@dataclass(frozen=True)
class EffectiveQuota:
    scope_type: str
    scope_id: str
    max_running_sandboxes: int | None
    max_timeout_seconds: int | None
    max_create_per_minute: int | None
    allowed_runtime_profile_ids: list[str] | None
    allowed_image_patterns: list[str] | None
    global_rule_id: str | None
    user_rule_id: str | None


@dataclass(frozen=True)
class QuotaUsage:
    active_sandboxes: int
    created_sandboxes_last_minute: int


async def get_effective_quota(
    session: AsyncSession,
    *,
    subject_id: str,
) -> EffectiveQuota:
    global_rule = await get_quota_rule(
        session,
        scope_type="global",
        scope_id=GLOBAL_SCOPE_ID,
    )
    user_rule = await get_quota_rule(session, scope_type="user", scope_id=subject_id)
    return _merge_quota_rules(subject_id, global_rule, user_rule)


async def get_quota_usage(
    session: AsyncSession,
    *,
    subject_id: str,
) -> QuotaUsage:
    since = datetime.now(UTC) - timedelta(minutes=1)
    return QuotaUsage(
        active_sandboxes=await count_active_sandboxes(session, owner_subject_id=subject_id),
        created_sandboxes_last_minute=await count_created_sandboxes_since(
            session,
            owner_subject_id=subject_id,
            since=since,
        ),
    )


async def get_quota_status(
    session: AsyncSession,
    *,
    subject_id: str,
) -> dict[str, Any]:
    quota = await get_effective_quota(session, subject_id=subject_id)
    usage = await get_quota_usage(session, subject_id=subject_id)
    return {
        "quota": quota_to_dict(quota),
        "usage": usage_to_dict(usage),
        "remaining": remaining_to_dict(quota, usage),
    }


async def enforce_sandbox_create_quota(
    session: AsyncSession,
    *,
    principal: CloudSandboxPrincipal,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    quota = await get_effective_quota(session, subject_id=principal.subject_id)
    usage = await get_quota_usage(session, subject_id=principal.subject_id)

    if (
        quota.max_running_sandboxes is not None
        and usage.active_sandboxes >= quota.max_running_sandboxes
    ):
        raise QuotaServiceError(
            "QUOTA_EXCEEDED",
            "active sandbox quota exceeded",
            429,
            details={
                "limit": quota.max_running_sandboxes,
                "current": usage.active_sandboxes,
            },
        )

    if (
        quota.max_create_per_minute is not None
        and usage.created_sandboxes_last_minute >= quota.max_create_per_minute
    ):
        raise QuotaServiceError(
            "RATE_LIMITED",
            "sandbox create rate limit exceeded",
            429,
            details={
                "limit": quota.max_create_per_minute,
                "current": usage.created_sandboxes_last_minute,
                "window_seconds": 60,
            },
        )

    return _apply_timeout_policy(request_payload, quota)


async def list_quota_rules(
    session: AsyncSession,
    *,
    scope_type: QuotaScopeType | None,
    scope_id: str | None,
    page: int,
    page_size: int,
) -> tuple[list[QuotaRule], int]:
    return await list_quota_rules_from_db(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
        page=page,
        page_size=page_size,
    )


async def save_quota_rule(
    session: AsyncSession,
    *,
    quota_id: str,
    scope_type: QuotaScopeType,
    scope_id: str,
    max_running_sandboxes: int | None,
    max_timeout_seconds: int | None,
    max_create_per_minute: int | None,
    allowed_runtime_profile_ids: list[str] | None,
    allowed_image_patterns: list[str] | None,
) -> QuotaRule:
    if scope_type == "global" and scope_id != GLOBAL_SCOPE_ID:
        raise QuotaServiceError(
            "INVALID_REQUEST",
            "global quota rule scope_id must be *",
            400,
        )
    if scope_type == "user" and not scope_id:
        raise QuotaServiceError(
            "INVALID_REQUEST",
            "user quota rule scope_id is required",
            400,
        )
    try:
        return await upsert_quota_rule(
            session,
            quota_id=quota_id,
            scope_type=scope_type,
            scope_id=scope_id,
            max_running_sandboxes=max_running_sandboxes,
            max_timeout_seconds=max_timeout_seconds,
            max_create_per_minute=max_create_per_minute,
            allowed_runtime_profile_ids=allowed_runtime_profile_ids,
            allowed_image_patterns=allowed_image_patterns,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise QuotaServiceError(
            "CONFLICT",
            "quota rule id or scope already exists",
            409,
        ) from exc


def quota_rule_to_dict(rule: QuotaRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "scope_type": rule.scope_type,
        "scope_id": rule.scope_id,
        "max_running_sandboxes": rule.max_running_sandboxes,
        "max_timeout_seconds": rule.max_timeout_seconds,
        "max_create_per_minute": rule.max_create_per_minute,
        "allowed_runtime_profile_ids": rule.allowed_runtime_profile_ids,
        "allowed_image_patterns": rule.allowed_image_patterns,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def quota_to_dict(quota: EffectiveQuota) -> dict[str, Any]:
    return {
        "scope_type": quota.scope_type,
        "scope_id": quota.scope_id,
        "max_running_sandboxes": quota.max_running_sandboxes,
        "max_timeout_seconds": quota.max_timeout_seconds,
        "max_create_per_minute": quota.max_create_per_minute,
        "allowed_runtime_profile_ids": quota.allowed_runtime_profile_ids,
        "allowed_image_patterns": quota.allowed_image_patterns,
        "global_rule_id": quota.global_rule_id,
        "user_rule_id": quota.user_rule_id,
    }


def usage_to_dict(usage: QuotaUsage) -> dict[str, int]:
    return {
        "active_sandboxes": usage.active_sandboxes,
        "created_sandboxes_last_minute": usage.created_sandboxes_last_minute,
    }


def remaining_to_dict(quota: EffectiveQuota, usage: QuotaUsage) -> dict[str, int | None]:
    return {
        "active_sandboxes": _remaining(quota.max_running_sandboxes, usage.active_sandboxes),
        "create_per_minute": _remaining(
            quota.max_create_per_minute,
            usage.created_sandboxes_last_minute,
        ),
    }


def _merge_quota_rules(
    subject_id: str,
    global_rule: QuotaRule | None,
    user_rule: QuotaRule | None,
) -> EffectiveQuota:
    return EffectiveQuota(
        scope_type="user",
        scope_id=subject_id,
        max_running_sandboxes=_merged_limit(
            user_rule,
            global_rule,
            "max_running_sandboxes",
            DEFAULT_MAX_RUNNING_SANDBOXES,
        ),
        max_timeout_seconds=_merged_limit(
            user_rule,
            global_rule,
            "max_timeout_seconds",
            DEFAULT_MAX_TIMEOUT_SECONDS,
        ),
        max_create_per_minute=_merged_limit(
            user_rule,
            global_rule,
            "max_create_per_minute",
            DEFAULT_MAX_CREATE_PER_MINUTE,
        ),
        allowed_runtime_profile_ids=_merged_list(
            user_rule,
            global_rule,
            "allowed_runtime_profile_ids",
        ),
        allowed_image_patterns=_merged_list(user_rule, global_rule, "allowed_image_patterns"),
        global_rule_id=global_rule.id if global_rule else None,
        user_rule_id=user_rule.id if user_rule else None,
    )


def _merged_limit(
    user_rule: QuotaRule | None,
    global_rule: QuotaRule | None,
    field: str,
    default: int,
) -> int | None:
    if user_rule is not None and getattr(user_rule, field) is not None:
        return getattr(user_rule, field)
    if global_rule is not None:
        return getattr(global_rule, field)
    return default


def _merged_list(
    user_rule: QuotaRule | None,
    global_rule: QuotaRule | None,
    field: str,
) -> list[str] | None:
    if user_rule is not None and getattr(user_rule, field) is not None:
        return list(getattr(user_rule, field) or [])
    if global_rule is not None:
        value = getattr(global_rule, field)
        return list(value or []) if value is not None else None
    return None


def _apply_timeout_policy(
    payload: dict[str, Any],
    quota: EffectiveQuota,
) -> dict[str, Any]:
    timeout = _extract_timeout(payload)
    if timeout is None:
        if quota.max_timeout_seconds is None:
            return dict(payload)
        adjusted = dict(payload)
        adjusted["timeout"] = quota.max_timeout_seconds
        return adjusted

    if quota.max_timeout_seconds is not None and timeout > quota.max_timeout_seconds:
        raise QuotaServiceError(
            "QUOTA_EXCEEDED",
            "sandbox timeout exceeds quota",
            429,
            details={
                "limit": quota.max_timeout_seconds,
                "requested": timeout,
            },
        )
    return dict(payload)


def _extract_timeout(payload: dict[str, Any]) -> int | None:
    value = payload.get("timeout")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QuotaServiceError(
            "INVALID_REQUEST",
            "timeout must be a positive integer when provided",
            400,
        )
    return value


def _remaining(limit: int | None, used: int) -> int | None:
    if limit is None:
        return None
    return max(limit - used, 0)
