from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from lnbits.core.crud import get_user, get_user_access_control_lists, get_user_extension
from lnbits.core.models import SimpleStatus
from lnbits.core.models.users import AccountId
from lnbits.core.services.extensions import get_valid_extensions
from lnbits.db import Database, Filters, Page
from lnbits.decorators import check_account_id_exists, parse_filters
from lnbits.helpers import generate_filter_params_openapi

from .crud import (
    create_activity_event,
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
    CreateActivityEvent,
    CreateAgentPolicy,
    CreateAgentProfile,
    LnurlpLinkReference,
    LnurlpStatus,
    TokenReference,
    UpdateAgentProfile,
)

agent_profile_filters = parse_filters(AgentProfileFilters)
activity_event_filters = parse_filters(ActivityEventFilters)

agent_wallet_api_router = APIRouter()
lnurlp_db = Database("ext_lnurlp")


@agent_wallet_api_router.get("/api/v1/tokens", response_model=list[TokenReference])
async def api_list_token_references(
    account_id: AccountId = Depends(check_account_id_exists),
) -> list[TokenReference]:
    """List safe ACL token references for binding to agent profiles.

    This endpoint never returns raw API token secrets. It only exposes ACL/token ids,
    names, and a short token hint for UI selection.
    """

    user_acls = await get_user_access_control_lists(account_id.id)
    refs: list[TokenReference] = []
    for acl in user_acls.access_control_list:
        for token in acl.token_id_list:
            refs.append(
                TokenReference(
                    acl_id=acl.id,
                    acl_name=acl.name,
                    token_id=token.id,
                    token_name=token.name,
                    token_hint=token.id[-6:] if token.id else None,
                )
            )
    return refs


@agent_wallet_api_router.get("/api/v1/lnurlp/status", response_model=LnurlpStatus)
async def api_lnurlp_status(
    account_id: AccountId = Depends(check_account_id_exists),
) -> LnurlpStatus:
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


@agent_wallet_api_router.get("/api/v1/lnurlp/links", response_model=list[LnurlpLinkReference])
async def api_list_lnurlp_links(
    req: Request,
    account_id: AccountId = Depends(check_account_id_exists),
) -> list[LnurlpLinkReference]:
    status = await api_lnurlp_status(account_id)
    if not status.installed or not status.enabled:
        return []

    user = await get_user(account_id.id)
    wallet_ids = [wallet.id for wallet in user.wallets] if user else []
    if not wallet_ids:
        return []

    wallet_params = {f"wallet_{i}": wallet_id for i, wallet_id in enumerate(wallet_ids)}
    wallet_placeholders = ", ".join(f":wallet_{i}" for i in range(len(wallet_ids)))
    rows = await lnurlp_db.fetchall(
        f"""
        SELECT id, description, username, min, max, currency, domain
        FROM lnurlp.pay_links
        WHERE wallet IN ({wallet_placeholders})
        ORDER BY id
        """,
        wallet_params,
    )

    fallback_domain = req.base_url.hostname or str(req.base_url).split("://", 1)[-1].rstrip("/")
    links: list[LnurlpLinkReference] = []
    for row in rows:
        data = dict(row)
        domain = data.get("domain") or fallback_domain
        link_id = data["id"]
        username = data.get("username")
        links.append(
            LnurlpLinkReference(
                id=link_id,
                description=data["description"],
                username=username,
                lnurl=f"lnurlp://{domain}/lnurlp/{link_id}",
                lnaddress=f"{username}@{domain}" if username else None,
                min=data.get("min"),
                max=data.get("max"),
                currency=data.get("currency"),
            )
        )
    return links


@agent_wallet_api_router.post("/api/v1/profiles", status_code=HTTPStatus.CREATED, response_model=AgentProfile)
async def api_create_agent_profile(
    data: CreateAgentProfile,
    account_id: AccountId = Depends(check_account_id_exists),
) -> AgentProfile:
    profile = await create_agent_profile(account_id.id, data)
    return profile


@agent_wallet_api_router.get(
    "/api/v1/profiles/paginated",
    name="Agent Wallet Profiles List",
    response_model=Page[AgentProfile],
    openapi_extra=generate_filter_params_openapi(AgentProfileFilters),
)
async def api_get_agent_profiles_paginated(
    account_id: AccountId = Depends(check_account_id_exists),
    filters: Filters = Depends(agent_profile_filters),
) -> Page[AgentProfile]:
    return await get_agent_profiles_paginated(user_id=account_id.id, filters=filters)


@agent_wallet_api_router.get("/api/v1/profiles/{profile_id}", response_model=AgentProfile)
async def api_get_agent_profile(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
) -> AgentProfile:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    return profile


@agent_wallet_api_router.put("/api/v1/profiles/{profile_id}", response_model=AgentProfile)
async def api_update_agent_profile(
    profile_id: str,
    data: UpdateAgentProfile,
    account_id: AccountId = Depends(check_account_id_exists),
) -> AgentProfile:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    updated = AgentProfile(**{**profile.dict(), **data.dict(exclude={"policy"})})
    return await update_agent_profile(updated)


@agent_wallet_api_router.delete("/api/v1/profiles/{profile_id}", response_model=SimpleStatus)
async def api_delete_agent_profile(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
) -> SimpleStatus:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    await delete_agent_profile(account_id.id, profile_id)
    return SimpleStatus(success=True, message="Agent profile deleted.")


@agent_wallet_api_router.get("/api/v1/profiles/{profile_id}/policy", response_model=AgentPolicy)
async def api_get_agent_policy(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
) -> AgentPolicy:
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
) -> AgentPolicy:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    return await upsert_agent_policy(profile_id, data)


@agent_wallet_api_router.get(
    "/api/v1/profiles/{profile_id}/activity",
    response_model=Page[ActivityEvent],
    openapi_extra=generate_filter_params_openapi(ActivityEventFilters),
)
async def api_get_activity_events(
    profile_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
    filters: Filters = Depends(activity_event_filters),
) -> Page[ActivityEvent]:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    return await get_activity_events_paginated(profile_id, filters=filters)


@agent_wallet_api_router.post(
    "/api/v1/profiles/{profile_id}/activity",
    status_code=HTTPStatus.CREATED,
    response_model=ActivityEvent,
)
async def api_create_activity_event(
    profile_id: str,
    data: CreateActivityEvent,
    account_id: AccountId = Depends(check_account_id_exists),
) -> ActivityEvent:
    profile = await get_agent_profile(account_id.id, profile_id)
    if not profile:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Agent profile not found.")
    return await create_activity_event(profile, data)
