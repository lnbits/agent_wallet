from http import HTTPStatus

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from lnbits.core.crud import get_user_access_control_lists, get_user_extension
from lnbits.core.models import AccessTokenPayload, SimpleStatus, User
from lnbits.core.models.users import AccountId
from lnbits.core.services.extensions import get_valid_extensions
from lnbits.db import Filters, Page
from lnbits.decorators import (
    access_token_payload,
    check_account_id_exists,
    check_user_exists,
    parse_filters,
)
from lnbits.helpers import generate_filter_params_openapi

from .crud import (
    create_agent_profile,
    delete_agent_profile,
    get_activity_events_paginated,
    get_agent_policy,
    get_agent_profile,
    get_agent_profiles_paginated,
    update_agent_profile,
    upsert_agent_policy,
)
from .models import (
    ActivityEvent,
    ActivityEventFilters,
    AgentPolicy,
    AgentProfile,
    AgentProfileFilters,
    CreateAgentPolicy,
    CreateAgentProfile,
    LnurlpStatus,
    RuntimeBalanceResponse,
    RuntimeInvoiceRequest,
    RuntimeInvoiceResponse,
    RuntimePaymentRequest,
    RuntimePaymentResponse,
    RuntimePaymentStatusResponse,
    RuntimePolicyDecision,
    RuntimeStatus,
    TokenReference,
    UpdateAgentProfile,
)
from .services import (
    check_runtime_payment,
    create_runtime_invoice,
    dry_run_payment,
    execute_payment,
    get_runtime_balance,
    get_runtime_status,
)

agent_profile_filters = parse_filters(AgentProfileFilters)
activity_event_filters = parse_filters(ActivityEventFilters)

agent_wallet_api_router = APIRouter()


@agent_wallet_api_router.get("/api/v1/tokens", response_model=list[TokenReference])
async def api_list_token_references(
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> list[TokenReference]:
    """List safe ACL token references for binding to agent profiles.

    This endpoint never returns raw API token secrets. It only exposes ACL/token ids,
    names, and a short token hint for UI selection.
    """

    _reject_api_token(token)
    user_acls = await get_user_access_control_lists(account_id.id)
    refs: list[TokenReference] = []
    for acl in user_acls.access_control_list:
        for acl_token in acl.token_id_list:
            refs.append(
                TokenReference(
                    acl_id=acl.id,
                    acl_name=acl.name,
                    token_id=acl_token.id,
                    token_name=acl_token.name,
                    token_hint=acl_token.id[-6:] if acl_token.id else None,
                )
            )
    return refs


@agent_wallet_api_router.get("/api/v1/lnurlp/status", response_model=LnurlpStatus)
async def api_lnurlp_status(
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> LnurlpStatus:
    _reject_api_token(token)
    valid_extension_ids = [ext.code for ext in await get_valid_extensions()]
    installed = "lnurlp" in valid_extension_ids
    user_ext = await get_user_extension(account_id.id, "lnurlp") if installed else None
    enabled = bool(user_ext and user_ext.active)
    message = None
    if not installed:
        message = "LNURLp extension is not installed on this LNbits instance."
    elif not enabled:
        message = "Enable LNURLp to use Lightning Address / LNURL-pay features."
    return LnurlpStatus(installed=installed, enabled=enabled, message=message)


@agent_wallet_api_router.post("/api/v1/profiles", status_code=HTTPStatus.CREATED, response_model=AgentProfile)
async def api_create_agent_profile(
    data: CreateAgentProfile,
    user: User = Depends(check_user_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> AgentProfile:
    _reject_api_token(token)
    _check_user_wallet_access(user, data.wallet)
    await _check_acl_token(user.id, data.acl_id, data.token_id)
    profile = await create_agent_profile(user.id, data)
    return profile


@agent_wallet_api_router.get(
    "/api/v1/profiles/paginated",
    name="Agent Wallet Profiles List",
    response_model=Page[AgentProfile],
    openapi_extra=generate_filter_params_openapi(AgentProfileFilters),
)
async def api_get_agent_profiles_paginated(
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
    filters: Filters = Depends(agent_profile_filters),
) -> Page[AgentProfile]:
    _reject_api_token(token)
    return await get_agent_profiles_paginated(user_id=account_id.id, filters=filters)


@agent_wallet_api_router.get("/api/v1/profiles/{profile_id}", response_model=AgentProfile)
async def api_get_agent_profile(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> AgentProfile:
    _reject_api_token(token)
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    return profile


@agent_wallet_api_router.put("/api/v1/profiles/{profile_id}", response_model=AgentProfile)
async def api_update_agent_profile(
    profile_id: str,
    data: UpdateAgentProfile,
    user: User = Depends(check_user_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> AgentProfile:
    _reject_api_token(token)
    profile = await get_agent_profile(user.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    _check_user_wallet_access(user, data.wallet)
    await _check_acl_token(user.id, data.acl_id, data.token_id)
    updated = AgentProfile(**{**profile.dict(), **data.dict(exclude={"policy"})})
    return await update_agent_profile(updated)


@agent_wallet_api_router.delete("/api/v1/profiles/{profile_id}", response_model=SimpleStatus)
async def api_delete_agent_profile(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> SimpleStatus:
    _reject_api_token(token)
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    await delete_agent_profile(account_id.id, profile_id)
    return SimpleStatus(success=True, message="Agent profile deleted.")


@agent_wallet_api_router.get("/api/v1/profiles/{profile_id}/policy", response_model=AgentPolicy)
async def api_get_agent_policy(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> AgentPolicy:
    _reject_api_token(token)
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    policy = await get_agent_policy(profile_id)
    if not policy:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent policy not found.")
    return policy


@agent_wallet_api_router.put("/api/v1/profiles/{profile_id}/policy", response_model=AgentPolicy)
async def api_upsert_agent_policy(
    profile_id: str,
    data: CreateAgentPolicy,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> AgentPolicy:
    _reject_api_token(token)
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    return await upsert_agent_policy(profile_id, data)


@agent_wallet_api_router.get("/api/v1/profiles/{profile_id}/runtime/status", response_model=RuntimeStatus)
async def api_get_runtime_status(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> RuntimeStatus:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    _require_profile_token(token, profile)
    return await get_runtime_status(profile)


@agent_wallet_api_router.get("/api/v1/profiles/{profile_id}/runtime/balance", response_model=RuntimeBalanceResponse)
async def api_get_runtime_balance(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> RuntimeBalanceResponse:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    _require_profile_token(token, profile)
    return await get_runtime_balance(profile)


@agent_wallet_api_router.get(
    "/api/v1/profiles/{profile_id}/runtime/payments/{checking_id}",
    response_model=RuntimePaymentStatusResponse,
)
async def api_check_runtime_payment(
    profile_id: str,
    checking_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> RuntimePaymentStatusResponse:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    _require_profile_token(token, profile)
    return await check_runtime_payment(profile, checking_id)


@agent_wallet_api_router.post(
    "/api/v1/profiles/{profile_id}/runtime/invoice",
    status_code=HTTPStatus.CREATED,
    response_model=RuntimeInvoiceResponse,
)
async def api_create_runtime_invoice(
    profile_id: str,
    data: RuntimeInvoiceRequest,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> RuntimeInvoiceResponse:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    _require_profile_token(token, profile)
    return await create_runtime_invoice(profile, data)


@agent_wallet_api_router.post(
    "/api/v1/profiles/{profile_id}/runtime/dry-run",
    response_model=RuntimePolicyDecision,
)
async def api_runtime_dry_run(
    profile_id: str,
    data: RuntimePaymentRequest,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> RuntimePolicyDecision:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    _require_profile_token(token, profile)
    return await dry_run_payment(profile, data)


@agent_wallet_api_router.post(
    "/api/v1/profiles/{profile_id}/runtime/pay",
    response_model=RuntimePaymentResponse,
)
async def api_runtime_pay(
    profile_id: str,
    data: RuntimePaymentRequest,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
) -> RuntimePaymentResponse:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    _require_profile_token(token, profile)
    return await execute_payment(profile, data)


@agent_wallet_api_router.get(
    "/api/v1/profiles/{profile_id}/activity",
    response_model=Page[ActivityEvent],
    openapi_extra=generate_filter_params_openapi(ActivityEventFilters),
)
async def api_get_activity_events(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
    token: AccessTokenPayload = Depends(access_token_payload),
    filters: Filters = Depends(activity_event_filters),
) -> Page[ActivityEvent]:
    _reject_api_token(token)
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    return await get_activity_events_paginated(profile_id, filters=filters)


def _reject_api_token(token: AccessTokenPayload) -> None:
    if token.api_token_id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "API token is only allowed on runtime endpoints.")


def _check_user_wallet_access(user: User, wallet_id: str) -> None:
    if wallet_id not in [wallet.id for wallet in user.wallets]:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not your wallet.")


async def _check_acl_token(user_id: str, acl_id: str, token_id: str) -> None:
    acls = await get_user_access_control_lists(user_id)
    acl = acls.get_acl_by_id(acl_id)
    if not acl or not acl.get_token_by_id(token_id):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Invalid ACL token.")


def _require_profile_token(token: AccessTokenPayload, profile: AgentProfile) -> None:
    if not token.api_token_id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "API token required.")
    if token.api_token_id != profile.token_id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Profile token mismatch.")
