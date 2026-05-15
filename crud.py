# Description: This file contains the CRUD operations for talking to the database.


from lnbits.db import Database, Filters, Page
from lnbits.helpers import urlsafe_short_hash

from .models import (
    ClientData,
    ClientDataFilters,
    CreateClientData,
    CreateProfiles,
    Profiles,
    ProfilesFilters,
)

db = Database("ext_agent_wallet")


########################### Profiles ############################
async def create_profiles(user_id: str, data: CreateProfiles) -> Profiles:
    profiles = Profiles(**data.dict(), id=urlsafe_short_hash(), user_id=user_id)
    await db.insert("agent_wallet.profiles", profiles)
    return profiles


async def get_profiles(
    user_id: str,
    profiles_id: str,
) -> Profiles | None:
    return await db.fetchone(
        """
            SELECT * FROM agent_wallet.profiles
            WHERE id = :id AND user_id = :user_id
        """,
        {"id": profiles_id, "user_id": user_id},
        Profiles,
    )


async def get_profiles_by_id(
    profiles_id: str,
) -> Profiles | None:
    return await db.fetchone(
        """
            SELECT * FROM agent_wallet.profiles
            WHERE id = :id
        """,
        {"id": profiles_id},
        Profiles,
    )


async def get_profiles_ids_by_user(
    user_id: str,
) -> list[str]:
    rows: list[dict] = await db.fetchall(
        """
            SELECT DISTINCT id FROM agent_wallet.profiles
            WHERE user_id = :user_id
        """,
        {"user_id": user_id},
    )

    return [row["id"] for row in rows]


async def get_profiles_paginated(
    user_id: str | None = None,
    filters: Filters[ProfilesFilters] | None = None,
) -> Page[Profiles]:
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
        model=Profiles,
    )


async def update_profiles(data: Profiles) -> Profiles:
    await db.update("agent_wallet.profiles", data)
    return data


async def delete_profiles(user_id: str, profiles_id: str) -> None:
    await db.execute(
        """
            DELETE FROM agent_wallet.profiles
            WHERE id = :id AND user_id = :user_id
        """,
        {"id": profiles_id, "user_id": user_id},
    )


################################# Client Data ###########################


async def create_client_data(profiles_id: str, data: CreateClientData) -> ClientData:
    client_data = ClientData(**data.dict(), id=urlsafe_short_hash(), profiles_id=profiles_id)
    await db.insert("agent_wallet.client_data", client_data)
    return client_data


async def get_client_data(
    profiles_id: str,
    client_data_id: str,
) -> ClientData | None:
    return await db.fetchone(
        """
            SELECT * FROM agent_wallet.client_data
            WHERE id = :id AND profiles_id = :profiles_id
        """,
        {"id": client_data_id, "profiles_id": profiles_id},
        ClientData,
    )


async def get_client_data_by_id(
    client_data_id: str,
) -> ClientData | None:
    return await db.fetchone(
        """
            SELECT * FROM agent_wallet.client_data
            WHERE id = :id
        """,
        {"id": client_data_id},
        ClientData,
    )


async def get_client_data_paginated(
    profiles_ids: list[str] | None = None,
    filters: Filters[ClientDataFilters] | None = None,
) -> Page[ClientData]:

    if not profiles_ids:
        return Page(data=[], total=0)

    where = []
    values = {}
    id_clause = []
    for i, item_id in enumerate(profiles_ids):
        # profiles_ids are not user input, but DB entries, so this is safe
        profiles_id = f"profiles_id__{i}"
        id_clause.append(f"profiles_id = :{profiles_id}")
        values[profiles_id] = item_id
    or_clause = " OR ".join(id_clause)
    where.append(f"({or_clause})")

    return await db.fetch_page(
        "SELECT * FROM agent_wallet.client_data",
        where=where,
        values=values,
        filters=filters,
        model=ClientData,
    )


async def update_client_data(data: ClientData) -> ClientData:
    await db.update("agent_wallet.client_data", data)
    return data


async def delete_client_data(profiles_id: str, client_data_id: str) -> None:
    await db.execute(
        """
            DELETE FROM agent_wallet.client_data
            WHERE id = :id AND profiles_id = :profiles_id
        """,
        {"id": client_data_id, "profiles_id": profiles_id},
    )


