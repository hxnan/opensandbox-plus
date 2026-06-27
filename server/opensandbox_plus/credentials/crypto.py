from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

CREDENTIAL_KEY_PREFIX = "osb_u_"
PUBLIC_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,32}$")


@dataclass(frozen=True)
class GeneratedCredential:
    public_prefix: str
    key: str
    key_hash: str


@dataclass(frozen=True)
class ParsedCredentialKey:
    public_prefix: str
    raw_key: str


def generate_credential(pepper: str) -> GeneratedCredential:
    public_prefix = secrets.token_urlsafe(9).rstrip("=")
    secret = secrets.token_urlsafe(32).rstrip("=")
    key = f"{CREDENTIAL_KEY_PREFIX}{public_prefix}.{secret}"
    return GeneratedCredential(
        public_prefix=public_prefix,
        key=key,
        key_hash=hash_credential_key(key, pepper),
    )


def hash_credential_key(key: str, pepper: str) -> str:
    digest = hmac.new(
        pepper.encode("utf-8"),
        key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:{digest}"


def parse_credential_key(key: str) -> ParsedCredentialKey:
    raw_key = key.strip()
    if not raw_key.startswith(CREDENTIAL_KEY_PREFIX):
        raise ValueError("invalid credential key prefix")

    body = raw_key[len(CREDENTIAL_KEY_PREFIX) :]
    public_prefix, separator, secret = body.partition(".")
    if not separator or not public_prefix or not secret:
        raise ValueError("invalid credential key format")
    if not PUBLIC_PREFIX_PATTERN.fullmatch(public_prefix):
        raise ValueError("invalid credential public prefix")
    if len(secret) < 32:
        raise ValueError("credential secret is too short")

    return ParsedCredentialKey(public_prefix=public_prefix, raw_key=raw_key)
