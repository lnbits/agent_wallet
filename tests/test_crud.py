from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from agent_wallet.crud import (  # type: ignore[import]
    create_activity_event,
    create_agent_profile,
    db,
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
    AgentProfile,
    CreateActivityEvent,
    CreateAgentPolicy,
    CreateAgentProfile,
    RuntimePaymentRequest,
    RuntimePolicyDecision,
)
from agent_wallet.services import (  # type: ignore[import]
    _dry_run_matches_payment,
    _pay_bolt11,
    dry_run_payment,
    execute_payment,
)

BOLT11_REGRESSION_INVOICE = (
    "lnbc2500u1p0psj6zpp5qqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfq9qyysgqcqpcxqyz5vqsp5"
    "zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zygq9qyyssq2v0j9w7v7n0v0v0n6z6w3h8t6l6m3t7y8f8"
    "x9x2v3g4h5j6k7l8m9n0q"
)


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
async def test_dry_run_payment_match_requires_same_amount_destination_action_and_payment_request():
    dry_run = ActivityEvent(
        id="dry-run-id",
        wallet="wallet-id",
        profile_id="profile-id",
        token_id="token-id",
        event_type="dry_run",
        amount_sats=21,
        destination="lnbc1example",
        status="allowed",
        request_json=RuntimePaymentRequest(
            action="bolt11",
            amount_sats=21,
            destination="lnbc1example",
            payment_request="lnbc1example",
        ).json(),
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
        amount_sats=21,
        destination="lnbc1example",
        payment_request="lnbc1different",
    )

    assert await _dry_run_matches_payment(dry_run, matching_payment) is True
    assert await _dry_run_matches_payment(dry_run, mismatched_payment) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "supplied_payment_request",
    [
        BOLT11_REGRESSION_INVOICE,
        f"  \n{BOLT11_REGRESSION_INVOICE}\t  ",
        f"lightning:{BOLT11_REGRESSION_INVOICE}",
        f"LIGHTNING:{BOLT11_REGRESSION_INVOICE}?amount=2500",
        f"{BOLT11_REGRESSION_INVOICE[:80]}\n{BOLT11_REGRESSION_INVOICE[80:]}",
    ],
)
async def test_pay_bolt11_forwards_payment_request_unchanged(monkeypatch, supplied_payment_request):
    captured: dict[str, str] = {}

    async def mock_pay_invoice(**kwargs):
        captured["payment_request"] = kwargs["payment_request"]
        return type("PaymentStub", (), {"status": "pending", "payment_hash": None, "checking_id": None})()

    monkeypatch.setattr("agent_wallet.services.pay_invoice", mock_pay_invoice)

    request = RuntimePaymentRequest(
        action="bolt11",
        amount_sats=2500,
        destination=supplied_payment_request,
        payment_request=supplied_payment_request,
    )
    profile = AgentProfile(id="p", user_id="u", wallet="w", name="n", acl_id="a", token_id="t")
    await _pay_bolt11(profile, request)

    assert captured["payment_request"] == supplied_payment_request


@pytest.mark.asyncio
async def test_execute_payment_requires_allowed_dry_run(monkeypatch):
    async def mock_get_wallet(_wallet_id):
        return object()

    monkeypatch.setattr("agent_wallet.services.get_wallet", mock_get_wallet)

    user_id = uuid4().hex
    profile = await create_agent_profile(
        user_id,
        CreateAgentProfile(
            wallet="wallet-id",
            name="agent",
            acl_id="acl-id",
            token_id="token-id",
            policy=CreateAgentPolicy(allow_spending=True, dry_run_required=True, single_payment_limit_sats=1000),
        ),
    )

    response = await execute_payment(
        profile,
        RuntimePaymentRequest(
            action="bolt11",
            amount_sats=10,
            destination="lnbc1example",
            payment_request="lnbc1example",
        ),
    )

    assert response.status == "denied"
    assert response.allowed is False
    assert "allowed dry-run is required before payment" in (response.reason or "")


@pytest.mark.asyncio
async def test_execute_payment_rejects_mismatched_amount(monkeypatch):
    async def mock_get_wallet(_wallet_id):
        return object()

    monkeypatch.setattr("agent_wallet.services.get_wallet", mock_get_wallet)

    user_id = uuid4().hex
    profile = await create_agent_profile(
        user_id,
        CreateAgentProfile(
            wallet="wallet-id",
            name="agent",
            acl_id="acl-id",
            token_id="token-id",
            policy=CreateAgentPolicy(allow_spending=True, dry_run_required=True, single_payment_limit_sats=1000),
        ),
    )

    dry_run = await dry_run_payment(
        profile,
        RuntimePaymentRequest(
            action="bolt11",
            amount_sats=10,
            destination="lnbc1example",
            payment_request="lnbc1example",
        ),
    )

    response = await execute_payment(
        profile,
        RuntimePaymentRequest(
            action="bolt11",
            amount_sats=11,
            destination="lnbc1example",
            payment_request="lnbc1example",
            dry_run_id=dry_run.dry_run_id,
        ),
    )

    assert response.status == "denied"
    assert "dry-run does not match payment request" in (response.reason or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,expected_value",
    [
        ("destination", "lnbc1other"),
        ("payment_request", "lnbc1other"),
        ("action", "lnurl_pay"),
    ],
)
async def test_execute_payment_rejects_mismatched_dry_run_binding(monkeypatch, field, expected_value):
    async def mock_get_wallet(_wallet_id):
        return object()

    monkeypatch.setattr("agent_wallet.services.get_wallet", mock_get_wallet)

    user_id = uuid4().hex
    profile = await create_agent_profile(
        user_id,
        CreateAgentProfile(
            wallet="wallet-id",
            name="agent",
            acl_id="acl-id",
            token_id="token-id",
            policy=CreateAgentPolicy(allow_spending=True, dry_run_required=True, single_payment_limit_sats=1000),
        ),
    )

    dry_run = await dry_run_payment(
        profile,
        RuntimePaymentRequest(
            action="bolt11",
            amount_sats=10,
            destination="lnbc1example",
            payment_request="lnbc1example",
        ),
    )

    payload = {
        "action": "bolt11",
        "amount_sats": 10,
        "destination": "lnbc1example",
        "payment_request": "lnbc1example",
        "dry_run_id": dry_run.dry_run_id,
    }
    payload[field] = expected_value

    response = await execute_payment(profile, RuntimePaymentRequest(**payload))

    assert response.status == "denied"
    assert "dry-run does not match payment request" in (response.reason or "")


@pytest.mark.asyncio
async def test_execute_payment_success_logs_activity(monkeypatch):
    async def mock_get_wallet(_wallet_id):
        return object()

    class PaymentStub:
        status = "success"
        payment_hash = "ph"
        checking_id = "cid"

        def json(self) -> str:
            return "{}"

    async def mock_pay_invoice(**_kwargs):
        return PaymentStub()

    monkeypatch.setattr("agent_wallet.services.get_wallet", mock_get_wallet)
    monkeypatch.setattr("agent_wallet.services.pay_invoice", mock_pay_invoice)

    user_id = uuid4().hex
    profile = await create_agent_profile(
        user_id,
        CreateAgentProfile(
            wallet="wallet-id",
            name="agent",
            acl_id="acl-id",
            token_id="token-id",
            policy=CreateAgentPolicy(allow_spending=True, dry_run_required=False, single_payment_limit_sats=1000),
        ),
    )

    response = await execute_payment(
        profile,
        RuntimePaymentRequest(
            action="bolt11",
            amount_sats=10,
            destination="lnbc1example",
            payment_request="lnbc1example",
        ),
    )
    events = await get_activity_events_paginated(profile.id)

    assert response.status == "success"
    assert events.total == 1
    assert events.data[0].event_type == "payment"
    assert events.data[0].status == "success"


@pytest.mark.asyncio
async def test_execute_payment_denied_logs_activity(monkeypatch):
    async def mock_get_wallet(_wallet_id):
        return object()

    monkeypatch.setattr("agent_wallet.services.get_wallet", mock_get_wallet)

    user_id = uuid4().hex
    profile = await create_agent_profile(
        user_id,
        CreateAgentProfile(
            wallet="wallet-id",
            name="agent",
            acl_id="acl-id",
            token_id="token-id",
            policy=CreateAgentPolicy(allow_spending=False, dry_run_required=False, single_payment_limit_sats=1000),
        ),
    )

    response = await execute_payment(
        profile,
        RuntimePaymentRequest(
            action="bolt11",
            amount_sats=10,
            destination="lnbc1example",
            payment_request="lnbc1example",
        ),
    )
    events = await get_activity_events_paginated(profile.id)

    assert response.status == "denied"
    assert events.total == 1
    assert events.data[0].event_type == "payment"
    assert events.data[0].status == "denied"


@pytest.mark.asyncio
async def test_execute_payment_rejects_replayed_dry_run(monkeypatch):
    async def mock_get_wallet(_wallet_id):
        return object()

    class PaymentStub:
        status = "success"
        payment_hash = "ph"
        checking_id = "cid"

        def json(self) -> str:
            return "{}"

    async def mock_pay_invoice(**_kwargs):
        return PaymentStub()

    monkeypatch.setattr("agent_wallet.services.get_wallet", mock_get_wallet)
    monkeypatch.setattr("agent_wallet.services.pay_invoice", mock_pay_invoice)

    user_id = uuid4().hex
    profile = await create_agent_profile(
        user_id,
        CreateAgentProfile(
            wallet="wallet-id",
            name="agent",
            acl_id="acl-id",
            token_id="token-id",
            policy=CreateAgentPolicy(allow_spending=True, dry_run_required=True, single_payment_limit_sats=1000),
        ),
    )

    request = RuntimePaymentRequest(
        action="bolt11",
        amount_sats=10,
        destination="lnbc1example",
        payment_request="lnbc1example",
    )
    dry_run = await dry_run_payment(profile, request)

    first = await execute_payment(profile, RuntimePaymentRequest(**{**request.dict(), "dry_run_id": dry_run.dry_run_id}))
    second = await execute_payment(profile, RuntimePaymentRequest(**{**request.dict(), "dry_run_id": dry_run.dry_run_id}))

    assert first.status == "success"
    assert second.status == "denied"
    assert "dry-run was already used by a prior payment attempt" in (second.reason or "")


@pytest.mark.asyncio
async def test_execute_payment_rejects_stale_dry_run(monkeypatch):
    async def mock_get_wallet(_wallet_id):
        return object()

    monkeypatch.setattr("agent_wallet.services.get_wallet", mock_get_wallet)

    user_id = uuid4().hex
    profile = await create_agent_profile(
        user_id,
        CreateAgentProfile(
            wallet="wallet-id",
            name="agent",
            acl_id="acl-id",
            token_id="token-id",
            policy=CreateAgentPolicy(allow_spending=True, dry_run_required=True, single_payment_limit_sats=1000),
        ),
    )

    request = RuntimePaymentRequest(
        action="bolt11",
        amount_sats=10,
        destination="lnbc1example",
        payment_request="lnbc1example",
    )
    dry_run = await dry_run_payment(profile, request)
    stale_timestamp = int((datetime.now(timezone.utc) - timedelta(minutes=16)).timestamp())
    await db.execute(
        """
        UPDATE agent_wallet.activity_events
        SET created_at = :created_at
        WHERE id = :id
        """,
        {"created_at": stale_timestamp, "id": dry_run.dry_run_id},
    )

    response = await execute_payment(profile, RuntimePaymentRequest(**{**request.dict(), "dry_run_id": dry_run.dry_run_id}))

    assert response.status == "denied"
    assert "dry-run is stale; create a new dry-run before payment" in (response.reason or "")


def test_canonical_helpers_removed():
    import agent_wallet.services as services

    assert not hasattr(services, "_canonical_bolt11")
    assert not hasattr(services, "_canonicalize_bolt11_payment")
