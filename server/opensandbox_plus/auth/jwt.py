from __future__ import annotations

import json
from urllib.request import urlopen

import jwt
from jwt import PyJWKClient

from opensandbox_plus.auth.principal import Principal, principal_from_claims
from opensandbox_plus.config import Settings


class TokenValidationError(ValueError):
    pass


class CasdoorTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client = PyJWKClient(self._resolve_jwks_url(settings))

    def verify(self, token: str) -> Principal:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                audience=self._settings.casdoor_audience,
                issuer=self._settings.casdoor_issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
            return principal_from_claims(claims)
        except Exception as exc:
            raise TokenValidationError(str(exc)) from exc

    @staticmethod
    def _resolve_jwks_url(settings: Settings) -> str:
        if settings.casdoor_jwks_url:
            return settings.casdoor_jwks_url

        discovery_url = settings.casdoor_discovery_url or (
            settings.casdoor_issuer.rstrip("/") + "/.well-known/openid-configuration"
        )
        try:
            with urlopen(discovery_url, timeout=5) as response:
                discovery = json.loads(response.read().decode("utf-8"))
            jwks_uri = discovery.get("jwks_uri")
            if isinstance(jwks_uri, str) and jwks_uri:
                return jwks_uri
        except Exception:
            pass

        return settings.casdoor_issuer.rstrip("/") + "/.well-known/jwks"
