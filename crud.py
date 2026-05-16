from datetime import datetime, timezone

from lnbits.db import Database, Filters, Page
from lnbits.helpers import urlsafe_short_hash

from .models import (
    ActivityEvent,
    ActivityEventFilters,
    AgentPolicy,
    AgentProfile,
    AgentProfileFilters,
    CreateActivityEvent,
    CreateAgentPolicy,
    CreateAgentProfile,
)

db = Database("ext_agent_wallet")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_agent_profile(user_id: str, data: CreateAgentProfile) -> AgentProfile:
    payload = data.dict(exclude={"policy"})
    profile = AgentProfile(**payload, id=urlsafe_short_hash(), user_id=user_id)
    await db.insert("agent_wallet.profiles", profile)
    await create_agent_policy(profile.id, data.policy or CreateAgentPolicy())
    return profile


async def get_agent_profile(user_id: str, profile_id: str) -> AgentProfile | None:
    return await db.fetchone(
        """
            SELECT * FROM agent_wallet.profiles
            WHERE id = :id AND user_id = :user_id
        """,
        {"id": profile_id, "user_id": user_id},
        AgentProfile,
    )


async def get_agent_profile_by_id(profile_id: str) -> AgentProfile | None:
    return await db.fetchone(
        "SELECT * FROM agent_wallet.profiles WHERE id = :id",
        {"id": profile_id},
        AgentProfile,
    )


async def get_agent_profiles_paginated(
    user_id: str | None = None,
    filters: Filters[AgentProfileFilters] | None = None,
) -> Page[AgentProfile]:
    where = []
    values = {}
    if user_id:
        where.append("user_id = :user_id")
        values["user_id"] = user_id

    return await db.fetch_page(
        "SELECT * FROM agent_wallet.profiles",
        where=where,
        values=values,
        filters=filters,
        model=AgentProfile,
    )


async def update_agent_profile(profile: AgentProfile) -> AgentProfile:
    profile.updated_at = _now()
    await db.update("agent_wallet.profiles", profile)
    return profile


async def delete_agent_profile(user_id: str, profile_id: str) -> None:
    await db.execute(
        "DELETE FROM agent_wallet.activity_events WHERE profile_id = :profile_id",
        {"profile_id": profile_id},
    )
    await db.execute(
        "DELETE FROM agent_wallet.policies WHERE profile_id = :profile_id",
        {"profile_id": profile_id},
    )
    await db.execute(
        """
            DELETE FROM agent_wallet.profiles
            WHERE id = :id AND user_id = :user_id
        """,
        {"id": profile_id, "user_id": user_id},
    )


async def create_agent_policy(profile_id: str, data: CreateAgentPolicy) -> AgentPolicy:
    policy = AgentPolicy(**data.dict(), id=urlsafe_short_hash(), profile_id=profile_id)
    await db.insert("agent_wallet.policies", policy)
    return policy


async def get_agent_policy(profile_id: str) -> AgentPolicy | None:
    return await db.fetchone(
        "SELECT * FROM agent_wallet.policies WHERE profile_id = :profile_id",
        {"profile_id": profile_id},
        AgentPolicy,
    )


async def upsert_agent_policy(profile_id: str, data: CreateAgentPolicy) -> AgentPolicy:
    policy = await get_agent_policy(profile_id)
    if not policy:
        return await create_agent_policy(profile_id, data)
    policy = AgentPolicy(**{**policy.dict(), **data.dict(), "updated_at": _now()})
    await db.update("agent_wallet.policies", policy)
    return policy


async def create_activity_event(profile: AgentProfile, data: CreateActivityEvent) -> ActivityEvent:
    event = ActivityEvent(
        **data.dict(),
        id=urlsafe_short_hash(),
        wallet=profile.wallet,
        profile_id=profile.id,
        token_id=profile.token_id,
    )
    await db.insert("agent_wallet.activity_events", event)
    return event


async def get_activity_events_paginated(
    profile_id: str,
    filters: Filters[ActivityEventFilters] | None = None,
) -> Page[ActivityEvent]:
    return await db.fetch_page(
        "SELECT * FROM agent_wallet.activity_events",
        where=["profile_id = :profile_id"],
        values={"profile_id": profile_id},
        filters=filters,
        model=ActivityEvent,
    )
