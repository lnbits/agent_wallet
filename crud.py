from datetime import datetime, timezone

from lnbits.db import Database, Filters, Page
from lnbits.helpers import urlsafe_short_hash
from sqlalchemy.exc import IntegrityError

from .models import (
    ActivityEvent,
    ActivityEventFilters,
    AgentPolicy,
    AgentProfile,
    AgentProfileFilters,
    CreateActivityEvent,
    CreateAgentPolicy,
    CreateAgentProfile,
    DailySpendBucket,
)

db = Database("ext_agent_wallet")


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
    await db.execute(
        "DELETE FROM agent_wallet.policies WHERE profile_id = :profile_id",
        {"profile_id": profile_id},
    )
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


async def mark_activity_by_payment_hash_success(payment_hash: str) -> None:
    await db.execute(
        """
        UPDATE agent_wallet.activity_events
        SET status = 'success'
        WHERE payment_hash = :payment_hash
          AND status IN ('pending', 'created')
        """,
        {"payment_hash": payment_hash},
    )


async def get_allowed_dry_run(profile_id: str, dry_run_id: str | None) -> ActivityEvent | None:
    if not dry_run_id:
        return None
    return await db.fetchone(
        """
        SELECT * FROM agent_wallet.activity_events
        WHERE id = :id
          AND profile_id = :profile_id
          AND event_type = 'dry_run'
          AND status IN ('allowed', 'consumed')
        """,
        {"id": dry_run_id, "profile_id": profile_id},
        ActivityEvent,
    )


async def consume_allowed_dry_run(profile_id: str, dry_run_id: str) -> bool:
    result = await db.execute(
        """
        UPDATE agent_wallet.activity_events
        SET status = 'consumed'
        WHERE id = :id
          AND profile_id = :profile_id
          AND event_type = 'dry_run'
          AND status = 'allowed'
        """,
        {"id": dry_run_id, "profile_id": profile_id},
    )
    return result.rowcount == 1


async def get_daily_spend_bucket(profile_id: str, day: int) -> DailySpendBucket | None:
    return await db.fetchone(
        """
        SELECT * FROM agent_wallet.daily_spend
        WHERE profile_id = :profile_id AND day = :day
        """,
        {"profile_id": profile_id, "day": day},
        DailySpendBucket,
    )


async def get_daily_reserved_sats(profile_id: str, day: int) -> int:
    bucket = await get_daily_spend_bucket(profile_id, day)
    if not bucket:
        return 0
    return int(bucket.spent_sats + bucket.pending_sats)


async def reserve_daily_spend(profile_id: str, day: int, amount_sats: int, daily_limit_sats: int) -> bool:
    if amount_sats <= 0:
        return True
    await _ensure_daily_spend_bucket(profile_id, day)
    result = await db.execute(
        """
        UPDATE agent_wallet.daily_spend
        SET pending_sats = pending_sats + :amount_sats,
            updated_at = :updated_at
        WHERE profile_id = :profile_id
          AND day = :day
          AND spent_sats + pending_sats + :amount_sats <= :daily_limit_sats
        """,
        {
            "profile_id": profile_id,
            "day": day,
            "amount_sats": amount_sats,
            "daily_limit_sats": daily_limit_sats,
            "updated_at": _now(),
        },
    )
    return result.rowcount == 1


async def settle_daily_spend(profile_id: str, day: int, amount_sats: int) -> None:
    if amount_sats <= 0:
        return
    await db.execute(
        """
        UPDATE agent_wallet.daily_spend
        SET pending_sats = CASE
                WHEN pending_sats >= :amount_sats THEN pending_sats - :amount_sats
                ELSE 0
            END,
            spent_sats = spent_sats + CASE
                WHEN pending_sats >= :amount_sats THEN :amount_sats
                ELSE pending_sats
            END,
            updated_at = :updated_at
        WHERE profile_id = :profile_id
          AND day = :day
        """,
        {
            "profile_id": profile_id,
            "day": day,
            "amount_sats": amount_sats,
            "updated_at": _now(),
        },
    )


async def release_daily_spend(profile_id: str, day: int, amount_sats: int) -> None:
    if amount_sats <= 0:
        return
    await db.execute(
        """
        UPDATE agent_wallet.daily_spend
        SET pending_sats = CASE
                WHEN pending_sats >= :amount_sats THEN pending_sats - :amount_sats
                ELSE 0
            END,
            updated_at = :updated_at
        WHERE profile_id = :profile_id
          AND day = :day
        """,
        {
            "profile_id": profile_id,
            "day": day,
            "amount_sats": amount_sats,
            "updated_at": _now(),
        },
    )


async def _ensure_daily_spend_bucket(profile_id: str, day: int) -> None:
    if await get_daily_spend_bucket(profile_id, day):
        return
    try:
        await db.execute(
            """
            INSERT INTO agent_wallet.daily_spend (
                profile_id, day, spent_sats, pending_sats, updated_at
            )
            VALUES (:profile_id, :day, 0, 0, :updated_at)
            """,
            {"profile_id": profile_id, "day": day, "updated_at": _now()},
        )
    except IntegrityError:
        # The row can be created concurrently by another request.
        return


def _now() -> datetime:
    return datetime.now(timezone.utc)
