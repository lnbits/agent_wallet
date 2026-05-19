from uuid import uuid4

import pytest

from agent_wallet.crud import (  # type: ignore[import]
    create_activity_event,
    create_agent_profile,
    delete_agent_profile,
    get_activity_events_paginated,
    get_agent_policy,
    get_agent_profile,
    get_agent_profile_by_id,
    get_agent_profiles_paginated,
    update_agent_profile,
    upsert_agent_policy,
)
from agent_wallet.models import (  # type: ignore[import]
    ActivityEvent,
    CreateActivityEvent,
    CreateAgentPolicy,
    CreateAgentProfile,
    RuntimePaymentRequest,
    RuntimePolicyDecision,
)
from agent_wallet.services import _dry_run_matches_payment  # type: ignore[import]


def profile_data() -> CreateAgentProfile:
    return CreateAgentProfile(
        wallet="wallet-id",
        name="research-agent",
        description="agent for paid API calls",
        acl_id="acl-id",
        token_id="token-id",
        token_name="agent-token",
        token_hint="abc123",
        lightning_address="research@example.com",
        policy=CreateAgentPolicy(single_payment_limit_sats=21),
    )


@pytest.mark.asyncio
async def test_create_get_update_delete_agent_profile():
    user_id = uuid4().hex
    profile = await create_agent_profile(user_id, profile_data())

    assert profile.id
    assert profile.user_id == user_id
    assert profile.template == "agent_wallet"
    assert profile.status == "active"

    fetched = await get_agent_profile(user_id, profile.id)
    assert fetched
    assert fetched.name == "research-agent"

    policy = await get_agent_policy(profile.id)
    assert policy
    assert policy.single_payment_limit_sats == 21

    profile.name = "ops-agent"
    await update_agent_profile(profile)
    updated = await get_agent_profile_by_id(profile.id)
    assert updated
    assert updated.name == "ops-agent"

    page = await get_agent_profiles_paginated(user_id=user_id)
    assert page.total == 1

    await delete_agent_profile(user_id, profile.id)
    page = await get_agent_profiles_paginated(user_id=user_id)
    assert page.total == 0


@pytest.mark.asyncio
async def test_upsert_policy_and_activity_event():
    user_id = uuid4().hex
    profile = await create_agent_profile(user_id, profile_data())

    policy = await upsert_agent_policy(
        profile.id,
        CreateAgentPolicy(
            single_payment_limit_sats=100,
            daily_limit_sats=1000,
            allow_spending=True,
        ),
    )
    assert policy.allow_spending is True
    assert policy.single_payment_limit_sats == 100

    event = await create_activity_event(
        profile,
        CreateActivityEvent(
            event_type="payment_dry_run",
            amount_sats=10,
            destination="lnbc...",
            status="dry_run",
            reason="test",
        ),
    )
    assert event.profile_id == profile.id
    assert event.token_id == profile.token_id

    events = await get_activity_events_paginated(profile.id)
    assert events.total == 1
    assert events.data[0].event_type == "payment_dry_run"


@pytest.mark.asyncio
async def test_dry_run_payment_match_requires_same_amount_destination_and_action():
    dry_run = ActivityEvent(
        id="dry-run-id",
        wallet="wallet-id",
        profile_id="profile-id",
        token_id="token-id",
        event_type="dry_run",
        amount_sats=21,
        destination="lnbc1example",
        status="allowed",
        response_json=RuntimePolicyDecision(
            allowed=True,
            amount_sats=21,
            destination="lnbc1example",
            action="bolt11",
        ).json(),
    )

    matching_payment = RuntimePaymentRequest(
        action="bolt11",
        amount_sats=21,
        destination="lnbc1example",
        payment_request="lnbc1example",
    )
    mismatched_payment = RuntimePaymentRequest(
        action="bolt11",
        amount_sats=22,
        destination="lnbc1example",
        payment_request="lnbc1example",
    )

    assert await _dry_run_matches_payment(dry_run, matching_payment) is True
    assert await _dry_run_matches_payment(dry_run, mismatched_payment) is False
