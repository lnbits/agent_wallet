# Description: This file contains the extensions API endpoints.
from http import HTTPStatus

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from lnbits.core.models import SimpleStatus, User
from lnbits.core.models.users import AccountId
from lnbits.db import Filters, Page
from lnbits.decorators import (
    check_account_exists,
    check_account_id_exists,
    parse_filters,
)
from lnbits.helpers import generate_filter_params_openapi

from .crud import (
    create_client_data,
    create_profiles,
    delete_client_data,
    delete_profiles,
    get_client_data_by_id,
    get_client_data_paginated,
    get_profiles,
    get_profiles_by_id,
    get_profiles_ids_by_user,
    get_profiles_paginated,
    update_client_data,
    update_profiles,
)
from .models import (
    ClientData,
    ClientDataFilters,
    CreateClientData,
    CreateProfiles,
    Profiles,
    ProfilesFilters,
)


profiles_filters = parse_filters(ProfilesFilters)
client_data_filters = parse_filters(ClientDataFilters)

agent_wallet_api_router = APIRouter()


############################# Profiles #############################
@agent_wallet_api_router.post("/api/v1/profiles", status_code=HTTPStatus.CREATED)
async def api_create_profiles(
    data: CreateProfiles,
    account_id: AccountId = Depends(check_account_id_exists),
) -> Profiles:
    profiles = await create_profiles(account_id.id, data)
    return profiles


@agent_wallet_api_router.put("/api/v1/profiles/{profiles_id}", status_code=HTTPStatus.CREATED)
async def api_update_profiles(
    profiles_id: str,
    data: CreateProfiles,
    account_id: AccountId = Depends(check_account_id_exists),
) -> Profiles:
    profiles = await get_profiles(account_id.id, profiles_id)
    if not profiles:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Profiles not found.")
    if profiles.user_id != account_id.id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "You do not own this profiles.")
    profiles = await update_profiles(Profiles(**{**profiles.dict(), **data.dict()}))
    return profiles


@agent_wallet_api_router.get(
    "/api/v1/profiles/paginated",
    name="Profiles List",
    summary="get paginated list of profiles",
    response_description="list of profiles",
    openapi_extra=generate_filter_params_openapi(ProfilesFilters),
    response_model=Page[Profiles],
)
async def api_get_profiles_paginated(
    account_id: AccountId = Depends(check_account_id_exists),
    filters: Filters = Depends(profiles_filters),
) -> Page[Profiles]:

    return await get_profiles_paginated(
        user_id=account_id.id,
        filters=filters,
    )


@agent_wallet_api_router.get(
    "/api/v1/profiles/{profiles_id}",
    name="Get Profiles",
    summary="Get the profiles with this id.",
    response_description="An profiles or 404 if not found",
    response_model=Profiles,
)
async def api_get_profiles(
    profiles_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
) -> Profiles:

    profiles = await get_profiles(account_id.id, profiles_id)
    if not profiles:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Profiles not found.")

    return profiles




@agent_wallet_api_router.delete(
    "/api/v1/profiles/{profiles_id}",
    name="Delete Profiles",
    summary="Delete the profiles " "and optionally all its associated client_data.",
    response_description="The status of the deletion.",
    response_model=SimpleStatus,
)
async def api_delete_profiles(
    profiles_id: str,
    clear_client_data: bool | None = False,
    account_id: AccountId = Depends(check_account_id_exists),
) -> SimpleStatus:

    await delete_profiles(account_id.id, profiles_id)
    if clear_client_data is True:
        # await delete all client data associated with this profiles
        pass
    return SimpleStatus(success=True, message="Profiles Deleted")


############################# Client Data #############################
@agent_wallet_api_router.post(
    "/api/v1/client_data/{profiles_id}",
    name="Create Client Data",
    summary="Create new client data for the specified profiles.",
    response_description="The created client data.",
    response_model=ClientData,
    status_code=HTTPStatus.CREATED,
)
async def api_create_client_data(
    profiles_id: str,
    data: CreateClientData,
    account_id: AccountId = Depends(check_account_id_exists),
) -> ClientData:
    profiles = await get_profiles(account_id.id, profiles_id)
    if not profiles:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Profiles not found.")

    client_data = await create_client_data(profiles_id, data)
    return client_data




@agent_wallet_api_router.put(
    "/api/v1/client_data/{client_data_id}",
    name="Update Client Data",
    summary="Update the client_data with this id.",
    response_description="The updated client data.",
    response_model=ClientData,
)
async def api_update_client_data(
    client_data_id: str,
    data: CreateClientData,
    account_id: AccountId = Depends(check_account_id_exists),
) -> ClientData:
    client_data = await get_client_data_by_id(client_data_id)
    if not client_data:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Client Data not found.")

    profiles = await get_profiles(account_id.id, client_data.profiles_id)
    if not profiles:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Profiles not found.")

    client_data = await update_client_data(ClientData(**{**client_data.dict(), **data.dict()}))
    return client_data


@agent_wallet_api_router.get(
    "/api/v1/client_data/paginated",
    name="Client Data List",
    summary="get paginated list of client_data",
    response_description="list of client_data",
    openapi_extra=generate_filter_params_openapi(ClientDataFilters),
    response_model=Page[ClientData],
)
async def api_get_client_data_paginated(
    account_id: AccountId = Depends(check_account_id_exists),
    profiles_id: str | None = None,
    filters: Filters = Depends(client_data_filters),
) -> Page[ClientData]:

    profiles_ids = await get_profiles_ids_by_user(account_id.id)

    if profiles_id:
        if profiles_id not in profiles_ids:
            raise HTTPException(HTTPStatus.FORBIDDEN, "Not your profiles.")
        profiles_ids = [profiles_id]

    return await get_client_data_paginated(
        profiles_ids=profiles_ids,
        filters=filters,
    )


@agent_wallet_api_router.get(
    "/api/v1/client_data/{client_data_id}",
    name="Get Client Data",
    summary="Get the client data with this id.",
    response_description="An client data or 404 if not found",
    response_model=ClientData,
)
async def api_get_client_data(
    client_data_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
) -> ClientData:

    client_data = await get_client_data_by_id(client_data_id)
    if not client_data:
        raise HTTPException(HTTPStatus.NOT_FOUND, "ClientData not found.")
    profiles = await get_profiles(account_id.id, client_data.profiles_id)
    if not profiles:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Profiles deleted for this Client Data.")

    return client_data


@agent_wallet_api_router.delete(
    "/api/v1/client_data/{client_data_id}",
    name="Delete Client Data",
    summary="Delete the client_data",
    response_description="The status of the deletion.",
    response_model=SimpleStatus,
)
async def api_delete_client_data(
    client_data_id: str,
    account_id: AccountId = Depends(check_account_id_exists),
) -> SimpleStatus:

    client_data = await get_client_data_by_id(client_data_id)
    if not client_data:
        raise HTTPException(HTTPStatus.NOT_FOUND, "ClientData not found.")
    profiles = await get_profiles(account_id.id, client_data.profiles_id)
    if not profiles:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Profiles deleted for this Client Data.")

    await delete_client_data(profiles.id, client_data_id)
    return SimpleStatus(success=True, message="Client Data Deleted")


