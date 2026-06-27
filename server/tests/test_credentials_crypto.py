import pytest

from opensandbox_plus.credentials.crypto import (
    generate_credential,
    hash_credential_key,
    parse_credential_key,
)


def test_hash_credential_key_is_deterministic_and_peppered() -> None:
    key = "osb_u_prefix.secret"

    first = hash_credential_key(key, "pepper-a")
    second = hash_credential_key(key, "pepper-a")
    different_pepper = hash_credential_key(key, "pepper-b")

    assert first == second
    assert first != different_pepper
    assert first.startswith("hmac-sha256:")


def test_generate_credential_shape() -> None:
    generated = generate_credential("pepper")

    assert generated.public_prefix
    assert generated.key.startswith(f"osb_u_{generated.public_prefix}.")
    assert generated.key_hash == hash_credential_key(generated.key, "pepper")
    assert generated.key not in generated.key_hash


def test_parse_credential_key_extracts_public_prefix() -> None:
    parsed = parse_credential_key("osb_u_abc123_x.a-very-long-secret-value-1234567890")

    assert parsed.public_prefix == "abc123_x"
    assert parsed.raw_key == "osb_u_abc123_x.a-very-long-secret-value-1234567890"


def test_parse_credential_key_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError):
        parse_credential_key("not-a-cloud-sandbox-key")
