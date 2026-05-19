import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from bolt11 import decode as bolt11_decode
from lnbits.core.crud import get_wallet
from lnbits.core.models import Payment
from lnbits.core.models.payments import CreateInvoice
from lnbits.core.services.payments import create_payment_request, pay_invoice
from loguru import logger

from .crud import create_activity_event, db, get_agent_policy
from .models import (
    ActivityEvent,
    AgentPolicy,
    AgentProfile,
    CreateActivityEvent,
    RuntimeInvoiceRequest,
    RuntimeInvoiceResponse,
    RuntimePaymentRequest,
    RuntimePaymentResponse,
    RuntimePolicyDecision,
    RuntimeStatus,
)


async def payment_received_for_agent_wallet(payment: Payment) -> bool:
    logger.info(f"Agent Wallet invoice paid: {payment.payment_hash}")
    return True


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _domain_from_destination(destination: str) -> str | None:
    destination = destination.strip().lower()
    if "@" in destination and not destination.startswith("lnurl"):
        return destination.rsplit("@", 1)[1]
    parsed = urlparse(destination)
    return parsed.hostname.lower() if parsed.hostname else None


def _payment_hash_from_bolt11(payment_request: str | None) -> str | None:
    if not payment_request:
        return None
    try:
        invoice = bolt11_decode(payment_request)
        return invoice.payment_hash
    except Exception:
        return None


async def get_daily_spent_sats(profile_id: str) -> int:
    now = datetime.now(timezone.utc)
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    row: dict[str, Any] | None = await db.fetchone(
        f"""
        SELECT COALESCE(SUM(amount_sats), 0) AS amount
        FROM agent_wallet.activity_events
        WHERE profile_id = :profile_id
          AND event_type = 'payment'
          AND status = 'success'
          AND created_at >= {db.timestamp_placeholder('day_start')}
        """,
        {"profile_id": profile_id, "day_start": int(day_start.timestamp())},
    )
    if not row:
        return 0
    return int(row["amount"] or 0)


async def get_runtime_status(profile: AgentProfile) -> RuntimeStatus:
    policy = await get_agent_policy(profile.id)
    wallet = await get_wallet(profile.wallet)
    daily_spent = await get_daily_spent_sats(profile.id)
    reasons: list[str] = []
    if profile.status != "active":
        reasons.append("profile is not active")
    if not policy:
        reasons.append("policy is missing")
    if not wallet:
        reasons.append("wallet is missing")

    default_policy = policy or AgentPolicy(id="", profile_id=profile.id)
    daily_remaining = max(default_policy.daily_limit_sats - daily_spent, 0)
    spending_available = bool(
        profile.status == "active" and wallet and policy and default_policy.allow_spending and daily_remaining > 0
    )
    receiving_available = bool(profile.status == "active" and wallet)
    return RuntimeStatus(
        profile_id=profile.id,
        profile_ready=profile.status == "active",
        policy_ready=policy is not None,
        wallet_present=wallet is not None,
        profile_status=profile.status,
        wallet=profile.wallet,
        spending_available=spending_available,
        receiving_available=receiving_available,
        dry_run_required=default_policy.dry_run_required,
        allow_spending=default_policy.allow_spending,
        allow_lnurl_pay=default_policy.allow_lnurl_pay,
        allow_lightning_address_pay=default_policy.allow_lightning_address_pay,
        allow_lnurl_withdraw=default_policy.allow_lnurl_withdraw,
        single_payment_limit_sats=default_policy.single_payment_limit_sats,
        daily_limit_sats=default_policy.daily_limit_sats,
        daily_spent_sats=daily_spent,
        daily_remaining_sats=daily_remaining,
        approval_required_above_sats=default_policy.approval_required_above_sats,
        reasons=reasons,
    )


async def create_runtime_invoice(profile: AgentProfile, data: RuntimeInvoiceRequest) -> RuntimeInvoiceResponse:
    status = await get_runtime_status(profile)
    if not status.receiving_available:
        reason = "; ".join(status.reasons) or "receiving is not available"
        await create_activity_event(
            profile,
            CreateActivityEvent(
                event_type="invoice",
                amount_sats=data.amount_sats,
                status="denied",
                reason=reason,
                task_id=data.task_id,
                request_json=data.json(),
            ),
        )
        return RuntimeInvoiceResponse(
            amount_sats=data.amount_sats,
            memo=data.memo,
            status="denied",
        )

    payment = await create_payment_request(
        profile.wallet,
        CreateInvoice(
            out=False,
            amount=data.amount_sats,
            unit="sat",
            memo=data.memo or f"Agent Wallet {profile.name}",
            expiry=data.expiry,
            extra={"tag": "agent_wallet", "profile_id": profile.id, "task_id": data.task_id},
        ),
    )
    await create_activity_event(
        profile,
        CreateActivityEvent(
            event_type="invoice",
            amount_sats=data.amount_sats,
            payment_hash=payment.payment_hash,
            checking_id=payment.checking_id,
            status=payment.status,
            task_id=data.task_id,
            request_json=data.json(),
            response_json=payment.json(),
        ),
    )
    return RuntimeInvoiceResponse(
        payment_hash=payment.payment_hash,
        checking_id=payment.checking_id,
        payment_request=payment.payment_request or payment.bolt11,
        bolt11=payment.bolt11,
        amount_sats=data.amount_sats,
        memo=payment.memo,
        status=payment.status,
    )


async def _policy_or_default(profile_id: str) -> tuple[AgentPolicy, list[str]]:
    policy = await get_agent_policy(profile_id)
    if policy:
        return policy, []
    return AgentPolicy(id="", profile_id=profile_id), ["policy is missing"]


async def _readiness_reasons(profile: AgentProfile) -> list[str]:
    reasons = []
    if profile.status != "active":
        reasons.append("profile is not active")
    if not await get_wallet(profile.wallet):
        reasons.append("wallet is missing")
    return reasons


def _spending_reasons(policy: AgentPolicy, data: RuntimePaymentRequest, daily_spent: int) -> tuple[list[str], bool]:
    reasons = []
    requires_approval = False
    action_permissions = {
        "lnurl_pay": (policy.allow_lnurl_pay, "LNURL-pay is disabled"),
        "lightning_address": (
            policy.allow_lightning_address_pay,
            "Lightning Address payments are disabled",
        ),
        "lnurl_withdraw": (policy.allow_lnurl_withdraw, "LNURL-withdraw is disabled"),
    }
    if not policy.allow_spending:
        reasons.append("spending is disabled")
    allowed, message = action_permissions.get(data.action, (True, ""))
    if not allowed:
        reasons.append(message)
    if data.amount_sats > policy.single_payment_limit_sats:
        reasons.append("amount exceeds single payment limit")
    if daily_spent + data.amount_sats > policy.daily_limit_sats:
        reasons.append("amount exceeds daily limit")
    if policy.approval_required_above_sats is not None and data.amount_sats > policy.approval_required_above_sats:
        requires_approval = True
        reasons.append("amount requires approval")
    return reasons, requires_approval


def _destination_reasons(policy: AgentPolicy, data: RuntimePaymentRequest) -> list[str]:
    reasons = []
    destination = data.destination.lower().strip()
    domain = _domain_from_destination(destination)
    if destination in _csv(policy.denied_lightning_addresses):
        reasons.append("destination lightning address is denied")
    allowed_addresses = _csv(policy.allowed_lightning_addresses)
    if data.action == "lightning_address" and allowed_addresses:
        if destination not in allowed_addresses:
            reasons.append("destination lightning address is not allowed")
    if domain in _csv(policy.denied_domains):
        reasons.append("destination domain is denied")
    allowed_domains = _csv(policy.allowed_domains)
    if allowed_domains and domain not in allowed_domains:
        reasons.append("destination domain is not allowed")
    allowed_lnurl_domains = _csv(policy.allowed_lnurl_domains)
    if data.action == "lnurl_pay" and allowed_lnurl_domains:
        if domain not in allowed_lnurl_domains:
            reasons.append("LNURL domain is not allowed")
    return reasons


async def evaluate_policy(profile: AgentProfile, data: RuntimePaymentRequest) -> RuntimePolicyDecision:
    policy, reasons = await _policy_or_default(profile.id)
    daily_spent = await get_daily_spent_sats(profile.id)
    reasons += await _readiness_reasons(profile)
    spending_reasons, requires_approval = _spending_reasons(policy, data, daily_spent)
    reasons += spending_reasons
    reasons += _destination_reasons(policy, data)

    return RuntimePolicyDecision(
        allowed=not reasons,
        requires_approval=requires_approval,
        dry_run_required=policy.dry_run_required,
        amount_sats=data.amount_sats,
        destination=data.destination,
        action=data.action,
        reasons=reasons,
        daily_spent_sats=daily_spent,
        daily_remaining_sats=max(policy.daily_limit_sats - daily_spent, 0),
    )


async def dry_run_payment(profile: AgentProfile, data: RuntimePaymentRequest) -> RuntimePolicyDecision:
    decision = await evaluate_policy(profile, data)
    event = await create_activity_event(
        profile,
        CreateActivityEvent(
            event_type="dry_run",
            amount_sats=data.amount_sats,
            destination=data.destination,
            payment_hash=_payment_hash_from_bolt11(data.payment_request),
            status="allowed" if decision.allowed else "denied",
            reason="; ".join(decision.reasons) or None,
            task_id=data.task_id,
            request_json=data.json(),
            response_json=decision.json(),
            metadata=json.dumps(data.metadata) if data.metadata else None,
        ),
    )
    decision.dry_run_id = event.id
    return decision


async def _get_allowed_dry_run(profile: AgentProfile, dry_run_id: str | None) -> ActivityEvent | None:
    if not dry_run_id:
        return None
    return await db.fetchone(
        """
        SELECT * FROM agent_wallet.activity_events
        WHERE id = :id
          AND profile_id = :profile_id
          AND event_type = 'dry_run'
          AND status = 'allowed'
        """,
        {"id": dry_run_id, "profile_id": profile.id},
        ActivityEvent,
    )


async def _dry_run_matches_payment(dry_run: ActivityEvent, data: RuntimePaymentRequest) -> bool:
    if dry_run.amount_sats != data.amount_sats:
        return False
    if (dry_run.destination or "").strip().lower() != data.destination.strip().lower():
        return False
    if not dry_run.response_json:
        return False
    try:
        decision = RuntimePolicyDecision.parse_raw(dry_run.response_json)
    except ValueError:
        return False
    return decision.action == data.action


async def execute_payment(profile: AgentProfile, data: RuntimePaymentRequest) -> RuntimePaymentResponse:
    decision = await evaluate_policy(profile, data)
    policy = await get_agent_policy(profile.id)
    dry_run = await _get_allowed_dry_run(profile, data.dry_run_id)
    if policy and policy.dry_run_required:
        if not dry_run:
            decision.allowed = False
            decision.reasons.append("allowed dry-run is required before payment")
        elif not await _dry_run_matches_payment(dry_run, data):
            decision.allowed = False
            decision.reasons.append("dry-run does not match payment request")
    if data.action != "bolt11":
        decision.allowed = False
        decision.reasons.append("only bolt11 payments are executable by this endpoint")
    if not data.payment_request:
        decision.allowed = False
        decision.reasons.append("payment_request is required")
    if not decision.allowed:
        reason = "; ".join(decision.reasons)
        await create_activity_event(
            profile,
            CreateActivityEvent(
                event_type="payment",
                amount_sats=data.amount_sats,
                destination=data.destination,
                payment_hash=_payment_hash_from_bolt11(data.payment_request),
                status="denied",
                reason=reason,
                task_id=data.task_id,
                request_json=data.json(),
                response_json=decision.json(),
                metadata=json.dumps(data.metadata) if data.metadata else None,
            ),
        )
        return RuntimePaymentResponse(
            amount_sats=data.amount_sats,
            destination=data.destination,
            status="denied",
            allowed=False,
            reason=reason,
        )

    try:
        payment = await pay_invoice(
            wallet_id=profile.wallet,
            payment_request=data.payment_request or "",
            max_sat=data.amount_sats,
            description=data.comment or "Agent Wallet payment",
            tag="agent_wallet",
            extra={"profile_id": profile.id, "task_id": data.task_id},
        )
        await create_activity_event(
            profile,
            CreateActivityEvent(
                event_type="payment",
                amount_sats=data.amount_sats,
                destination=data.destination,
                payment_hash=payment.payment_hash,
                checking_id=payment.checking_id,
                status=payment.status,
                task_id=data.task_id,
                request_json=data.json(),
                response_json=payment.json(),
                metadata=json.dumps(data.metadata) if data.metadata else None,
            ),
        )
        return RuntimePaymentResponse(
            payment_hash=payment.payment_hash,
            checking_id=payment.checking_id,
            amount_sats=data.amount_sats,
            destination=data.destination,
            status=payment.status,
            allowed=True,
        )
    except Exception as exc:
        reason = str(exc)
        await create_activity_event(
            profile,
            CreateActivityEvent(
                event_type="payment",
                amount_sats=data.amount_sats,
                destination=data.destination,
                payment_hash=_payment_hash_from_bolt11(data.payment_request),
                status="failed",
                reason=reason,
                task_id=data.task_id,
                request_json=data.json(),
                metadata=json.dumps(data.metadata) if data.metadata else None,
            ),
        )
        return RuntimePaymentResponse(
            amount_sats=data.amount_sats,
            destination=data.destination,
            status="failed",
            allowed=True,
            reason=reason,
        )
