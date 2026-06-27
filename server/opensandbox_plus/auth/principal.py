from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PLATFORM_ADMIN_ROLE = "osb_platform_admin"
AGENT_USER_ROLE = "osb_agent_user"


@dataclass(frozen=True)
class Principal:
    subject_id: str
    casdoor_owner: str
    casdoor_user: str
    username: str | None
    email: str | None
    display_name: str | None
    roles: list[str]
    status: str

    @property
    def is_platform_admin(self) -> bool:
        return PLATFORM_ADMIN_ROLE in self.roles

    @property
    def is_agent_user(self) -> bool:
        return AGENT_USER_ROLE in self.roles

    @property
    def features(self) -> dict[str, bool]:
        return {
            "credential_issue": self.is_agent_user or self.is_platform_admin,
            "sandbox_create": self.is_agent_user or self.is_platform_admin,
            "admin_console": self.is_platform_admin,
        }


@dataclass(frozen=True)
class CloudSandboxPrincipal:
    principal: Principal
    credential_id: str
    public_prefix: str

    @property
    def subject_id(self) -> str:
        return self.principal.subject_id


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    subject = _first_str(claims, "sub", "id", "user_id")
    if not subject:
        raise ValueError("missing subject claim")

    owner = _first_str(claims, "owner", "organization", "org", default="default")
    username = _first_str(claims, "preferred_username", "name", "username")
    casdoor_user = _first_str(claims, "user", "name", "username", default=subject)
    display_name = _first_str(claims, "display_name", "displayName", "name")
    email = _first_str(claims, "email")
    roles = _extract_roles(claims)
    status = _extract_status(claims)

    return Principal(
        subject_id=f"casdoor:{owner}:{subject}",
        casdoor_owner=owner,
        casdoor_user=casdoor_user,
        username=username,
        email=email,
        display_name=display_name,
        roles=roles,
        status=status,
    )


def _first_str(claims: dict[str, Any], *keys: str, default: str | None = None) -> str | None:
    for key in keys:
        value = claims.get(key)
        if isinstance(value, str) and value:
            return value
    return default


def _extract_status(claims: dict[str, Any]) -> str:
    if claims.get("isForbidden") is True or claims.get("is_forbidden") is True:
        return "disabled"
    status = _first_str(claims, "status", "state")
    if status in {"active", "disabled", "deleted"}:
        return status
    return "active"


def _extract_roles(claims: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("roles", "role", "groups", "permissions"):
        value = claims.get(key)
        values.extend(_extract_role_value(value))

    properties = claims.get("properties")
    if isinstance(properties, dict):
        for key in ("osb_roles", "roles", "role", "groups", "permissions"):
            values.extend(_extract_role_value(properties.get(key)))

    values.extend(_extract_role_value(claims.get("tag")))

    seen: set[str] = set()
    roles: list[str] = []
    for role in values:
        if role and role not in seen:
            seen.add(role)
            roles.append(role)
    return roles


def _extract_role_value(value: Any) -> list[str]:
    if isinstance(value, str):
        return _split_role_string(value)
    if isinstance(value, list):
        return _extract_role_list(value)
    return []


def _split_role_string(value: str) -> list[str]:
    return [part.strip() for part in value.replace(",", " ").split() if part.strip()]


def _extract_role_list(values: list[Any]) -> list[str]:
    roles: list[str] = []
    for value in values:
        if isinstance(value, str):
            roles.extend(_split_role_string(value))
        elif isinstance(value, dict):
            name = value.get("name") or value.get("displayName") or value.get("id")
            if isinstance(name, str):
                roles.append(name)
    return roles
