from uuid import uuid4

import pytest

from agent_wallet.crud import (  # type: ignore[import]
    create_profiles,
    delete_profiles,
    get_profiles,
    get_profiles_by_id,
    get_profiles_ids_by_user,
    get_profiles_paginated,
    update_profiles,
)
from agent_wallet.models import (  # type: ignore[import]
    CreateProfiles,
    Profiles,
)


@pytest.mark.asyncio
async def test_create_and_get_profiles():
    user_id = uuid4().hex

    data = CreateProfiles(
        wallet = "0de83d45-fbed-49a6-8751-4202bf3e5f33",
        name = "name_WkqqhJswXp9Au8HmG9qdPu",
        description = "description_YgDcDMVixfJFMuLkGpq6HX",
        acl_id = "acl_id_fmYPH6FhKqvzDmnapb8hZi",
        token_id = "token_id_b3iFwC26WezWZHDtAJTno8",
        token_name = "token_name_JXo2kUTp65R9w9CmnUJSEb",
        status = "status_nxbst25gT8bRFXS7om9WT2",
        lnurlp_id = "lnurlp_id_mkrnuKxHA7pBLadUj4Ny9p",
        expires_at = datetime.fromisoformat("2026-05-25T13:31:35.510696+00:00"),
    )
    profiles_one = await create_profiles(user_id, data)
    assert profiles_one.id is not None
    assert profiles_one.user_id == user_id

    profiles_one = await get_profiles(user_id, profiles_one.id)
    assert profiles_one.id is not None
    assert profiles_one.user_id == user_id
    assert profiles_one.wallet == data.wallet
    assert profiles_one.name == data.name
    assert profiles_one.description == data.description
    assert profiles_one.acl_id == data.acl_id
    assert profiles_one.token_id == data.token_id
    assert profiles_one.token_name == data.token_name
    assert profiles_one.status == data.status
    assert profiles_one.lnurlp_id == data.lnurlp_id
    assert profiles_one.expires_at == data.expires_at

    data = CreateProfiles(
        wallet = "0de83d45-fbed-49a6-8751-4202bf3e5f33",
        name = "name_WkqqhJswXp9Au8HmG9qdPu",
        description = "description_YgDcDMVixfJFMuLkGpq6HX",
        acl_id = "acl_id_fmYPH6FhKqvzDmnapb8hZi",
        token_id = "token_id_b3iFwC26WezWZHDtAJTno8",
        token_name = "token_name_JXo2kUTp65R9w9CmnUJSEb",
        status = "status_nxbst25gT8bRFXS7om9WT2",
        lnurlp_id = "lnurlp_id_mkrnuKxHA7pBLadUj4Ny9p",
        expires_at = datetime.fromisoformat("2026-05-25T13:31:35.510696+00:00"),
    )
    profiles_two = await create_profiles(user_id, data)
    assert profiles_two.id is not None
    assert profiles_two.user_id == user_id

    profiles_list = await get_profiles_ids_by_user(user_id=user_id)
    assert len(profiles_list) == 2

    profiles_page = await get_profiles_paginated(user_id=user_id)
    assert profiles_page.total == 2
    assert len(profiles_page.data) == 2

    await delete_profiles(user_id, profiles_one.id)
    profiles_list = await get_profiles_ids_by_user(user_id=user_id)
    assert len(profiles_list) == 1

    profiles_page = await get_profiles_paginated(user_id=user_id)
    assert profiles_page.total == 1
    assert len(profiles_page.data) == 1


@pytest.mark.asyncio
async def test_update_profiles():
    user_id = uuid4().hex

    data = CreateProfiles(
        wallet = "0de83d45-fbed-49a6-8751-4202bf3e5f33",
        name = "name_WkqqhJswXp9Au8HmG9qdPu",
        description = "description_YgDcDMVixfJFMuLkGpq6HX",
        acl_id = "acl_id_fmYPH6FhKqvzDmnapb8hZi",
        token_id = "token_id_b3iFwC26WezWZHDtAJTno8",
        token_name = "token_name_JXo2kUTp65R9w9CmnUJSEb",
        status = "status_nxbst25gT8bRFXS7om9WT2",
        lnurlp_id = "lnurlp_id_mkrnuKxHA7pBLadUj4Ny9p",
        expires_at = datetime.fromisoformat("2026-05-25T13:31:35.510696+00:00"),
    )
    profiles_one = await create_profiles(user_id, data)
    assert profiles_one.id is not None
    assert profiles_one.user_id == user_id

    profiles_one = await get_profiles(user_id, profiles_one.id)
    assert profiles_one.id is not None
    assert profiles_one.user_id == user_id
    assert profiles_one.wallet == data.wallet
    assert profiles_one.name == data.name
    assert profiles_one.description == data.description
    assert profiles_one.acl_id == data.acl_id
    assert profiles_one.token_id == data.token_id
    assert profiles_one.token_name == data.token_name
    assert profiles_one.status == data.status
    assert profiles_one.lnurlp_id == data.lnurlp_id
    assert profiles_one.expires_at == data.expires_at

    data_updated = CreateProfiles(
        wallet = "0de83d45-fbed-49a6-8751-4202bf3e5f33",
        name = "name_WkqqhJswXp9Au8HmG9qdPu",
        description = "description_YgDcDMVixfJFMuLkGpq6HX",
        acl_id = "acl_id_fmYPH6FhKqvzDmnapb8hZi",
        token_id = "token_id_b3iFwC26WezWZHDtAJTno8",
        token_name = "token_name_JXo2kUTp65R9w9CmnUJSEb",
        status = "status_nxbst25gT8bRFXS7om9WT2",
        lnurlp_id = "lnurlp_id_mkrnuKxHA7pBLadUj4Ny9p",
        expires_at = datetime.fromisoformat("2026-05-25T13:31:35.510696+00:00"),
    )
    profiles_updated = Profiles(**{**profiles_one.dict(), **data_updated.dict()})

    await update_profiles(profiles_updated)
    profiles_one = await get_profiles_by_id(profiles_one.id)
    assert profiles_one.wallet == profiles_updated.wallet
    assert profiles_one.name == profiles_updated.name
    assert profiles_one.description == profiles_updated.description
    assert profiles_one.acl_id == profiles_updated.acl_id
    assert profiles_one.token_id == profiles_updated.token_id
    assert profiles_one.token_name == profiles_updated.token_name
    assert profiles_one.status == profiles_updated.status
    assert profiles_one.lnurlp_id == profiles_updated.lnurlp_id
    assert profiles_one.expires_at == profiles_updated.expires_at
