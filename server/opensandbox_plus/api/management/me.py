from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import get_current_principal
from opensandbox_plus.api.management.schemas import CurrentUserResponse
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.db.session import get_session
from opensandbox_plus.quotas.service import get_quota_status

router = APIRouter()


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> CurrentUserResponse:
    return CurrentUserResponse(
        subject_id=principal.subject_id,
        username=principal.username,
        email=principal.email,
        display_name=principal.display_name,
        roles=principal.roles,
        features=principal.features,
    )


@router.get("/me/usage")
async def get_my_usage(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    return await get_quota_status(session, subject_id=principal.subject_id)
