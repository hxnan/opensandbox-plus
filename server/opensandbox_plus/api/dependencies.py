from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.auth.jwt import CasdoorTokenVerifier, TokenValidationError
from opensandbox_plus.auth.principal import CloudSandboxPrincipal, Principal
from opensandbox_plus.credentials.service import CredentialServiceError
from opensandbox_plus.credentials.service import verify_cloud_sandbox_credential
from opensandbox_plus.db.session import get_session
from opensandbox_plus.users.repository import upsert_user_identity


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "missing Authorization header"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "expected Bearer token"},
        )
    return token


def _get_token_verifier(request: Request) -> CasdoorTokenVerifier:
    verifier = getattr(request.app.state, "casdoor_token_verifier", None)
    if verifier is None:
        verifier = CasdoorTokenVerifier(request.app.state.settings)
        request.app.state.casdoor_token_verifier = verifier
    return verifier


async def get_current_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Principal:
    token = _extract_bearer_token(authorization)
    verifier = _get_token_verifier(request)
    try:
        principal = verifier.verify(token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "invalid access token"},
        ) from exc

    if principal.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "user is not active"},
        )
    if not (principal.is_agent_user or principal.is_platform_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "user does not have OpenSandbox Plus role"},
        )

    await upsert_user_identity(session, principal)
    return principal


async def require_platform_admin(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    if not principal.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "platform admin role required"},
        )
    return principal


async def get_cloud_sandbox_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str | None, Header(alias="OPEN-SANDBOX-API-KEY")] = None,
) -> CloudSandboxPrincipal:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "MISSING_API_KEY",
                "message": "missing OPEN-SANDBOX-API-KEY header",
            },
        )

    try:
        principal = await verify_cloud_sandbox_credential(
            session,
            settings=request.app.state.settings,
            raw_key=api_key,
            client_ip=request.client.host if request.client else None,
        )
    except CredentialServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    request.state.cloud_sandbox_principal = principal
    return principal
