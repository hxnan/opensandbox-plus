from opensandbox_plus.auth.principal import (
    AGENT_USER_ROLE,
    PLATFORM_ADMIN_ROLE,
    principal_from_claims,
)


def test_principal_from_casdoor_like_claims() -> None:
    principal = principal_from_claims(
        {
            "sub": "user_123",
            "owner": "built-in",
            "name": "alice",
            "email": "alice@example.com",
            "displayName": "Alice",
            "roles": [{"name": AGENT_USER_ROLE}, {"name": PLATFORM_ADMIN_ROLE}],
        }
    )

    assert principal.subject_id == "casdoor:built-in:user_123"
    assert principal.casdoor_owner == "built-in"
    assert principal.casdoor_user == "alice"
    assert principal.username == "alice"
    assert principal.email == "alice@example.com"
    assert principal.display_name == "Alice"
    assert principal.is_agent_user is True
    assert principal.is_platform_admin is True
    assert principal.features == {
        "credential_issue": True,
        "sandbox_create": True,
        "admin_console": True,
    }


def test_principal_marks_forbidden_user_disabled() -> None:
    principal = principal_from_claims(
        {
            "sub": "user_456",
            "owner": "built-in",
            "name": "bob",
            "roles": AGENT_USER_ROLE,
            "isForbidden": True,
        }
    )

    assert principal.status == "disabled"
    assert principal.roles == [AGENT_USER_ROLE]


def test_principal_extracts_roles_from_properties_and_tag() -> None:
    principal = principal_from_claims(
        {
            "sub": "user_789",
            "owner": "built-in",
            "name": "carol",
            "properties": {"osb_roles": AGENT_USER_ROLE},
            "tag": PLATFORM_ADMIN_ROLE,
        }
    )

    assert principal.roles == [AGENT_USER_ROLE, PLATFORM_ADMIN_ROLE]
