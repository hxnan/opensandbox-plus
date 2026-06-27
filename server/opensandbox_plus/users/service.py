from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.db.models import UserIdentity
from opensandbox_plus.users.repository import (
    active_credential_counts_by_user,
    active_sandbox_counts_by_user,
    list_user_identities,
)


@dataclass(frozen=True)
class AdminUserSummary:
    user: UserIdentity
    active_credentials: int
    active_sandboxes: int


async def list_admin_users(
    session: AsyncSession,
    *,
    keyword: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AdminUserSummary], int]:
    users, total = await list_user_identities(
        session,
        keyword=keyword,
        status=status,
        page=page,
        page_size=page_size,
    )
    subject_ids = [user.subject_id for user in users]
    credential_counts = await active_credential_counts_by_user(session, subject_ids=subject_ids)
    sandbox_counts = await active_sandbox_counts_by_user(session, subject_ids=subject_ids)
    return [
        AdminUserSummary(
            user=user,
            active_credentials=credential_counts.get(user.subject_id, 0),
            active_sandboxes=sandbox_counts.get(user.subject_id, 0),
        )
        for user in users
    ], total
