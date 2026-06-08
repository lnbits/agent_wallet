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

from .crud import (
    consume_allowed_dry_run,
    create_activity_event,
    get_agent_policy,
    get_allowed_dry_run,
    get_daily_reserved_sats,
    mark_activity_by_payment_hash_success,
    release_daily_spend,
    reserve_daily_spend,
    settle_daily_spend,
)
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
    await mark_activity_by_payment_hash_success(payment.payment_hash)
    logger.info(f"Agent Wallet invoice/payment updated as success: {payment.payment_hash}")
    return True


async def get_daily_spent_sats(profile_id: str) -> int:
    return await get_daily_reserved_sats(profile_id, _current_day_start())


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
            extra={
                "tag": "agent_wallet",
                "profile_id": profile.id,
                "task_id": data.task_id,
            },
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
        destination=_normalize_destination(data.destination),
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
    day_start = _current_day_start()
    try:
        data, lnurl_withdraw = await _prepare_lnurl_withdraw(data)
    except Exception as exc:
        return await _fail_payment(profile, data, _public_reason(exc))

    decision = await evaluate_policy(profile, data)
    _validate_executable_payment(data, decision)
    if decision.requires_approval:
        decision.allowed = False
        decision.reasons.append("amount requires approval")
    if data.action != "lnurl_withdraw":
        await _validate_dry_run_requirement(profile, data, decision)

    if not decision.allowed:
        return await _deny_payment(profile, data, decision)
    reserved_daily_spend = await _reserve_daily_spend_for_payment(profile, data, day_start)
    if not reserved_daily_spend and data.action != "lnurl_withdraw":
        decision.allowed = False
        decision.reasons.append("amount exceeds daily limit")
        return await _deny_payment(profile, data, decision)

    try:
        payment = await _pay_payment_request(profile, data, lnurl_withdraw=lnurl_withdraw)
    except Exception as exc:
        await _release_daily_spend_for_payment(profile, data, day_start)
        return await _fail_payment(profile, data, _public_reason(exc))
    await _finalize_daily_spend_for_payment(profile, data, day_start, payment)

    await _log_payment_event(profile, data, status=payment.status, payment=payment)
    return RuntimePaymentResponse(
        payment_hash=payment.payment_hash,
        checking_id=payment.checking_id,
        amount_sats=data.amount_sats or 0,
        destination=_normalize_destination(data.destination),
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
    return reasons, requires_approval


def _receiving_reasons(policy: AgentPolicy, data: RuntimePaymentRequest) -> list[str]:
    reasons = []
    if data.action == "lnurl_withdraw" and not policy.allow_lnurl_withdraw:
        reasons.append("LNURL-withdraw is disabled")
    return reasons


def _destination_reasons(policy: AgentPolicy, data: RuntimePaymentRequest) -> list[str]:
    if data.action not in ("lnurl_pay", "lightning_address", "lnurl_withdraw"):
        return []
    reasons: list[str] = []
    destination = _normalize_destination(data.destination)
    if not destination:
        return reasons
    domain = _domain_from_destination(destination)
    denied_addresses = _csv(policy.denied_lightning_addresses)
    allowed_addresses = _csv(policy.allowed_lightning_addresses)
    denied_domains = _csv(policy.denied_domains)
    allowed_domains = _csv(policy.allowed_domains)
    allowed_lnurl_domains = _csv(policy.allowed_lnurl_domains)

    if destination in denied_addresses:
        reasons.append("destination lightning address is denied")
    if data.action == "lightning_address" and allowed_addresses:
        if destination not in allowed_addresses:
            reasons.append("destination lightning address is not allowed")
    reasons += _domain_policy_reasons(domain, denied_domains, allowed_domains)
    reasons += _lnurl_domain_policy_reasons(data.action, domain, allowed_lnurl_domains)
    return reasons


async def _validate_dry_run_requirement(
    profile: AgentProfile,
    data: RuntimePaymentRequest,
    decision: RuntimePolicyDecision,
) -> None:
    policy = await get_agent_policy(profile.id)
    if not policy or not policy.dry_run_required:
        return

    dry_run = await get_allowed_dry_run(profile.id, data.dry_run_id)
    if not dry_run:
        decision.allowed = False
        decision.reasons.append("allowed dry-run is required before payment")
        return
    if dry_run.status == "consumed":
        decision.allowed = False
        decision.reasons.append("dry-run was already used by a prior payment attempt")
        return
    if _is_dry_run_stale(dry_run):
        decision.allowed = False
        decision.reasons.append("dry-run is stale; create a new dry-run before payment")
        return
    if not await _dry_run_matches_payment(dry_run, data):
        decision.allowed = False
        decision.reasons.append("dry-run does not match payment request")
        return
    if not await consume_allowed_dry_run(profile.id, dry_run.id):
        decision.allowed = False
        decision.reasons.append("dry-run was already used by a prior payment attempt")


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
            _normalize_destination(data.destination) or "",
            (data.amount_sats or 0) * 1000,
            comment=data.comment,
        )
        return await pay_invoice(
            wallet_id=profile.wallet,
            payment_request=payment_request,
            max_sat=data.amount_sats,
            description=data.comment or "Agent Wallet LNURL payment",
            tag="agent_wallet",
            extra={
                "profile_id": profile.id,
                "task_id": data.task_id,
                "action": data.action,
            },
        )

    if data.action == "lnurl_withdraw":
        withdraw = lnurl_withdraw or await _resolve_lnurl_withdraw(data.destination or "")
        amount_sats = _lnurl_withdraw_amount_sats(withdraw, data.amount_sats)
        memo = data.comment or str(withdraw.defaultDescription)
        payment = await create_payment_request(
            profile.wallet,
            CreateInvoice(
                out=False,
                amount=amount_sats,
                unit="sat",
                memo=memo or "Agent Wallet LNURL-withdraw",
                extra={
                    "tag": "agent_wallet",
                    "profile_id": profile.id,
                    "task_id": data.task_id,
                    "action": data.action,
                },
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
    min_withdrawable = int(withdraw.minWithdrawable)
    max_withdrawable = int(withdraw.maxWithdrawable)
    min_sats = _ceil_msat_to_sat(min_withdrawable)
    max_sats = max_withdrawable // 1000
    if max_sats <= 0:
        raise LnurlResponseException("LNURL-withdraw maxWithdrawable must be at least 1 sat.")
    amount_sats = requested_sats or max_sats
    if amount_sats < min_sats:
        raise LnurlResponseException("requested amount is below LNURL-withdraw minimum")
    if amount_sats > max_sats:
        raise LnurlResponseException("requested amount exceeds LNURL-withdraw maximum")
    return amount_sats


def _ceil_msat_to_sat(amount_msat: int) -> int:
    return (amount_msat + 999) // 1000


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
        amount_sats=data.amount_sats or 0,
        destination=_normalize_destination(data.destination),
        status="denied",
        allowed=False,
        reason=reason,
    )


async def _fail_payment(profile: AgentProfile, data: RuntimePaymentRequest, reason: str) -> RuntimePaymentResponse:
    await _log_payment_event(profile, data, status="failed", reason=reason)
    return RuntimePaymentResponse(
        amount_sats=data.amount_sats or 0,
        destination=_normalize_destination(data.destination),
        status="failed",
        allowed=False,
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
            destination=_normalize_destination(data.destination),
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


def _domain_policy_reasons(
    domain: str | None,
    denied_domains: list[str],
    allowed_domains: list[str],
) -> list[str]:
    reasons: list[str] = []
    if domain and domain in denied_domains:
        reasons.append("destination domain is denied")
    if allowed_domains and domain and domain not in allowed_domains:
        reasons.append("destination domain is not allowed")
    if allowed_domains and not domain:
        reasons.append("destination domain could not be determined")
    return reasons


def _lnurl_domain_policy_reasons(
    action: str,
    domain: str | None,
    allowed_lnurl_domains: list[str],
) -> list[str]:
    if action not in ("lnurl_pay", "lnurl_withdraw") or not allowed_lnurl_domains:
        return []
    if not domain or domain not in allowed_lnurl_domains:
        return ["LNURL domain is not allowed"]
    return []


def _normalize_destination(destination: str | None) -> str | None:
    if destination is None:
        return None
    value = destination.strip()
    return value or None


def _public_reason(exc: Exception) -> str:
    if isinstance(exc, (LnurlResponseException, ValueError)):
        return str(exc)
    return "payment execution failed"


async def _reserve_daily_spend_for_payment(profile: AgentProfile, data: RuntimePaymentRequest, day_start: int) -> bool:
    if data.action == "lnurl_withdraw" or data.amount_sats is None:
        return True
    policy = await get_agent_policy(profile.id)
    if not policy:
        return False
    return await reserve_daily_spend(profile.id, day_start, data.amount_sats, policy.daily_limit_sats)


async def _release_daily_spend_for_payment(profile: AgentProfile, data: RuntimePaymentRequest, day_start: int) -> None:
    if data.action == "lnurl_withdraw" or data.amount_sats is None:
        return
    await release_daily_spend(profile.id, day_start, data.amount_sats)


async def _finalize_daily_spend_for_payment(
    profile: AgentProfile, data: RuntimePaymentRequest, day_start: int, payment: Payment
) -> None:
    if data.action == "lnurl_withdraw" or data.amount_sats is None:
        return
    if payment.status == "success":
        await settle_daily_spend(profile.id, day_start, data.amount_sats)
        return
    if payment.status == "failed":
        await release_daily_spend(profile.id, day_start, data.amount_sats)


def _payment_hash_from_bolt11(payment_request: str | None) -> str | None:
    if not payment_request:
        return None
    try:
        invoice = bolt11_decode(payment_request)
        return invoice.payment_hash
    except Exception:
        return None


def _current_day_start() -> int:
    now = datetime.now(timezone.utc)
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return int(day_start.timestamp())
