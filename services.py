import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from bolt11 import decode as bolt11_decode
from lnbits.core.crud import get_wallet
from lnbits.core.models import Payment
from lnbits.core.models.payments import CreateInvoice
from lnbits.core.services.lnurl import get_pr_from_lnurl
from lnbits.core.services.payments import create_payment_request, pay_invoice
from lnbits.helpers import check_callback_url
from lnbits.settings import settings
from lnurl import (
    LnurlErrorResponse,
    LnurlResponseException,
    LnurlSuccessResponse,
    LnurlWithdrawResponse,
    execute_withdraw,
    handle,
)
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

DRY_RUN_FRESHNESS_SECONDS = 15 * 60


async def payment_received_for_agent_wallet(payment: Payment) -> bool:
    logger.info(f"Agent Wallet invoice paid: {payment.payment_hash}")
    return True


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
        await _log_invoice_event(profile, data, status="denied", reason=reason)
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
    await _log_invoice_event(profile, data, status=payment.status, payment=payment)
    return RuntimeInvoiceResponse(
        payment_hash=payment.payment_hash,
        checking_id=payment.checking_id,
        payment_request=payment.payment_request or payment.bolt11,
        bolt11=payment.bolt11,
        amount_sats=data.amount_sats,
        memo=payment.memo,
        status=payment.status,
    )


async def evaluate_policy(profile: AgentProfile, data: RuntimePaymentRequest) -> RuntimePolicyDecision:
    policy, reasons = await _policy_or_default(profile.id)
    daily_spent = await get_daily_spent_sats(profile.id)
    reasons += await _readiness_reasons(profile)
    requires_approval = False
    if data.action == "lnurl_withdraw":
        reasons += _receiving_reasons(policy, data)
    else:
        spending_reasons, requires_approval = _spending_reasons(policy, data, daily_spent)
        reasons += spending_reasons
    reasons += _destination_reasons(policy, data)

    return RuntimePolicyDecision(
        allowed=not reasons,
        requires_approval=requires_approval,
        dry_run_required=policy.dry_run_required and data.action != "lnurl_withdraw",
        amount_sats=data.amount_sats or 0,
        destination=data.destination,
        action=data.action,
        reasons=reasons,
        daily_spent_sats=daily_spent,
        daily_remaining_sats=max(policy.daily_limit_sats - daily_spent, 0),
    )


async def dry_run_payment(profile: AgentProfile, data: RuntimePaymentRequest) -> RuntimePolicyDecision:
    data, _ = await _prepare_lnurl_withdraw(data)
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
            metadata=_metadata_json(data.metadata),
        ),
    )
    decision.dry_run_id = event.id
    return decision


async def execute_payment(profile: AgentProfile, data: RuntimePaymentRequest) -> RuntimePaymentResponse:
    try:
        data, lnurl_withdraw = await _prepare_lnurl_withdraw(data)
    except Exception as exc:
        return await _fail_payment(profile, data, str(exc))

    decision = await evaluate_policy(profile, data)
    if data.action != "lnurl_withdraw":
        await _validate_dry_run_requirement(profile, data, decision)
    _validate_executable_payment(data, decision)

    if not decision.allowed:
        return await _deny_payment(profile, data, decision)

    try:
        payment = await _pay_payment_request(profile, data, lnurl_withdraw=lnurl_withdraw)
    except Exception as exc:
        return await _fail_payment(profile, data, str(exc))

    await _log_payment_event(profile, data, status=payment.status, payment=payment)
    return RuntimePaymentResponse(
        payment_hash=payment.payment_hash,
        checking_id=payment.checking_id,
        amount_sats=data.amount_sats or 0,
        destination=data.destination,
        status=payment.status,
        allowed=True,
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
    if data.amount_sats is None:
        reasons.append("amount_sats is required")
        return reasons, requires_approval
    if data.amount_sats > policy.single_payment_limit_sats:
        reasons.append("amount exceeds single payment limit")
    if daily_spent + data.amount_sats > policy.daily_limit_sats:
        reasons.append("amount exceeds daily limit")
    if policy.approval_required_above_sats is not None and data.amount_sats > policy.approval_required_above_sats:
        requires_approval = True
        reasons.append("amount requires approval")
    return reasons, requires_approval


def _receiving_reasons(policy: AgentPolicy, data: RuntimePaymentRequest) -> list[str]:
    reasons = []
    if data.action == "lnurl_withdraw" and not policy.allow_lnurl_withdraw:
        reasons.append("LNURL-withdraw is disabled")
    return reasons


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
    if data.action in ("lnurl_pay", "lnurl_withdraw") and allowed_lnurl_domains:
        if domain not in allowed_lnurl_domains:
            reasons.append("LNURL domain is not allowed")
    return reasons


async def _validate_dry_run_requirement(
    profile: AgentProfile,
    data: RuntimePaymentRequest,
    decision: RuntimePolicyDecision,
) -> None:
    policy = await get_agent_policy(profile.id)
    if not policy or not policy.dry_run_required:
        return

    dry_run = await _get_allowed_dry_run(profile, data.dry_run_id)
    if not dry_run:
        decision.allowed = False
        decision.reasons.append("allowed dry-run is required before payment")
        return
    if _is_dry_run_stale(dry_run):
        decision.allowed = False
        decision.reasons.append("dry-run is stale; create a new dry-run before payment")
        return
    if await _dry_run_already_used(profile.id, dry_run.id):
        decision.allowed = False
        decision.reasons.append("dry-run was already used by a prior payment attempt")
        return
    if not await _dry_run_matches_payment(dry_run, data):
        decision.allowed = False
        decision.reasons.append("dry-run does not match payment request")


def _validate_executable_payment(data: RuntimePaymentRequest, decision: RuntimePolicyDecision) -> None:
    if data.action == "bolt11" and not data.payment_request:
        decision.allowed = False
        decision.reasons.append("payment_request is required")
    if data.action in ("lnurl_pay", "lightning_address") and not data.destination:
        decision.allowed = False
        decision.reasons.append("destination is required")
    if data.action == "lnurl_withdraw" and not data.destination:
        decision.allowed = False
        decision.reasons.append("destination is required")


async def _pay_payment_request(
    profile: AgentProfile,
    data: RuntimePaymentRequest,
    *,
    lnurl_withdraw: LnurlWithdrawResponse | None = None,
) -> Payment:
    if data.action == "bolt11":
        return await _pay_bolt11(profile, data)

    if data.action in ("lnurl_pay", "lightning_address"):
        payment_request = await get_pr_from_lnurl(
            data.destination,
            data.amount_sats * 1000,
            comment=data.comment,
        )
        return await pay_invoice(
            wallet_id=profile.wallet,
            payment_request=payment_request,
            max_sat=data.amount_sats,
            description=data.comment or "Agent Wallet LNURL payment",
            tag="agent_wallet",
            extra={"profile_id": profile.id, "task_id": data.task_id, "action": data.action},
        )

    if data.action == "lnurl_withdraw":
        withdraw = lnurl_withdraw or await _resolve_lnurl_withdraw(data.destination)
        amount_sats = _lnurl_withdraw_amount_sats(withdraw, data.amount_sats)
        payment = await create_payment_request(
            profile.wallet,
            CreateInvoice(
                out=False,
                amount=amount_sats,
                unit="sat",
                memo=data.comment or _lnurl_withdraw_description(withdraw) or "Agent Wallet LNURL-withdraw",
                extra={"tag": "agent_wallet", "profile_id": profile.id, "task_id": data.task_id, "action": data.action},
            ),
        )
        res = await execute_withdraw(
            withdraw,
            payment.bolt11,
            user_agent=settings.user_agent,
            timeout=10,
        )
        if isinstance(res, LnurlErrorResponse):
            raise LnurlResponseException(res.reason)
        if not isinstance(res, LnurlSuccessResponse):
            raise LnurlResponseException("Invalid LNURL-withdraw success response.")
        return payment

    raise ValueError(f"Unsupported payment action: {data.action}")


async def _prepare_lnurl_withdraw(
    data: RuntimePaymentRequest,
) -> tuple[RuntimePaymentRequest, LnurlWithdrawResponse | None]:
    if data.action != "lnurl_withdraw" or not data.destination:
        return data, None
    withdraw = await _resolve_lnurl_withdraw(data.destination)
    amount_sats = _lnurl_withdraw_amount_sats(withdraw, data.amount_sats)
    if amount_sats == data.amount_sats:
        return data, withdraw
    return data.copy(update={"amount_sats": amount_sats}), withdraw


async def _resolve_lnurl_withdraw(lnurl: str) -> LnurlWithdrawResponse:
    res = await handle(lnurl, user_agent=settings.user_agent, timeout=10)
    if isinstance(res, LnurlErrorResponse):
        raise LnurlResponseException(res.reason)
    if not isinstance(res, LnurlWithdrawResponse):
        raise LnurlResponseException("Invalid LNURL response. Expected LNURL-withdraw.")
    try:
        check_callback_url(res.callback)
    except ValueError as exc:
        raise LnurlResponseException(f"Invalid callback URL: {exc!s}") from exc
    return res


def _lnurl_withdraw_amount_sats(withdraw: LnurlWithdrawResponse, requested_sats: int | None) -> int:
    min_withdrawable = _lnurl_withdraw_field(withdraw, "min_withdrawable", "minWithdrawable") or 0
    max_withdrawable = _lnurl_withdraw_field(withdraw, "max_withdrawable", "maxWithdrawable") or 0
    min_sats = _msat_to_sat_ceil(min_withdrawable)
    max_sats = max_withdrawable // 1000
    if max_sats <= 0:
        raise LnurlResponseException("LNURL-withdraw maxWithdrawable must be at least 1 sat.")
    amount_sats = requested_sats or max_sats
    if amount_sats < min_sats:
        raise LnurlResponseException("requested amount is below LNURL-withdraw minimum")
    if amount_sats > max_sats:
        raise LnurlResponseException("requested amount exceeds LNURL-withdraw maximum")
    return amount_sats


def _msat_to_sat_ceil(amount_msat: int) -> int:
    return (amount_msat + 999) // 1000


def _lnurl_withdraw_description(withdraw: LnurlWithdrawResponse) -> str | None:
    return _lnurl_withdraw_field(withdraw, "default_description", "defaultDescription")


def _lnurl_withdraw_field(withdraw: LnurlWithdrawResponse, snake_name: str, alias_name: str):
    if hasattr(withdraw, snake_name):
        return getattr(withdraw, snake_name)
    if hasattr(withdraw, alias_name):
        return getattr(withdraw, alias_name)
    if hasattr(withdraw, "dict"):
        data = withdraw.dict()
        return data.get(snake_name) or data.get(alias_name)
    return None


async def _pay_bolt11(profile: AgentProfile, data: RuntimePaymentRequest) -> Payment:
    return await pay_invoice(
        wallet_id=profile.wallet,
        payment_request=data.payment_request or "",
        max_sat=data.amount_sats,
        description=data.comment or "Agent Wallet payment",
        tag="agent_wallet",
        extra={"profile_id": profile.id, "task_id": data.task_id},
    )


async def _deny_payment(
    profile: AgentProfile,
    data: RuntimePaymentRequest,
    decision: RuntimePolicyDecision,
) -> RuntimePaymentResponse:
    reason = "; ".join(decision.reasons)
    await _log_payment_event(
        profile,
        data,
        status="denied",
        reason=reason,
        response_json=decision.json(),
    )
    return RuntimePaymentResponse(
        amount_sats=data.amount_sats,
        destination=data.destination,
        status="denied",
        allowed=False,
        reason=reason,
    )


async def _fail_payment(profile: AgentProfile, data: RuntimePaymentRequest, reason: str) -> RuntimePaymentResponse:
    await _log_payment_event(profile, data, status="failed", reason=reason)
    return RuntimePaymentResponse(
        amount_sats=data.amount_sats,
        destination=data.destination,
        status="failed",
        allowed=True,
        reason=reason,
    )


async def _log_invoice_event(
    profile: AgentProfile,
    data: RuntimeInvoiceRequest,
    *,
    status: str,
    payment: Payment | None = None,
    reason: str | None = None,
) -> ActivityEvent:
    return await create_activity_event(
        profile,
        CreateActivityEvent(
            event_type="invoice",
            amount_sats=data.amount_sats,
            payment_hash=payment.payment_hash if payment else None,
            checking_id=payment.checking_id if payment else None,
            status=status,
            reason=reason,
            task_id=data.task_id,
            request_json=data.json(),
            response_json=payment.json() if payment else None,
        ),
    )


async def _log_payment_event(
    profile: AgentProfile,
    data: RuntimePaymentRequest,
    *,
    status: str,
    payment: Payment | None = None,
    reason: str | None = None,
    response_json: str | None = None,
) -> ActivityEvent:
    return await create_activity_event(
        profile,
        CreateActivityEvent(
            event_type="payment",
            amount_sats=data.amount_sats,
            destination=data.destination,
            payment_hash=payment.payment_hash if payment else _payment_hash_from_bolt11(data.payment_request),
            checking_id=payment.checking_id if payment else None,
            status=status,
            reason=reason,
            task_id=data.task_id,
            request_json=data.json(),
            response_json=payment.json() if payment else response_json,
            metadata=_metadata_json(data.metadata),
        ),
    )


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
    if (dry_run.destination or "") != data.destination:
        return False
    if not dry_run.request_json or not dry_run.response_json:
        return False
    try:
        request = RuntimePaymentRequest.parse_raw(dry_run.request_json)
        decision = RuntimePolicyDecision.parse_raw(dry_run.response_json)
    except ValueError:
        return False
    return (
        request.action == data.action
        and request.amount_sats == data.amount_sats
        and request.destination == data.destination
        and request.payment_request == data.payment_request
        and decision.action == data.action
    )


async def _dry_run_already_used(profile_id: str, dry_run_id: str) -> bool:
    used = await db.fetchone(
        """
        SELECT id FROM agent_wallet.activity_events
        WHERE profile_id = :profile_id
          AND event_type = 'payment'
          AND (
            request_json LIKE :dry_run_pattern
            OR request_json LIKE :dry_run_pattern_spaced
          )
        LIMIT 1
        """,
        {
            "profile_id": profile_id,
            "dry_run_pattern": f'%"dry_run_id":"{dry_run_id}"%',
            "dry_run_pattern_spaced": f'%"dry_run_id": "{dry_run_id}"%',
        },
    )
    return bool(used)


def _is_dry_run_stale(dry_run: ActivityEvent) -> bool:
    created_at = dry_run.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
    return age_seconds > DRY_RUN_FRESHNESS_SECONDS


def _metadata_json(metadata: dict[str, Any] | None) -> str | None:
    return json.dumps(metadata) if metadata else None


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
