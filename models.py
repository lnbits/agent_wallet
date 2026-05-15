from datetime import datetime, timezone

from lnbits.db import FilterModel
from pydantic import BaseModel, Field


########################### Profiles ############################
class CreateProfiles(BaseModel):
    wallet: str
    name: str
    description: str | None
    acl_id: str
    token_id: str
    token_name: str | None
    status: str
    lnurlp_id: str | None
    expires_at: datetime
    


class Profiles(BaseModel):
    id: str
    user_id: str
    wallet: str
    name: str
    description: str | None
    acl_id: str
    token_id: str
    token_name: str | None
    status: str
    lnurlp_id: str | None
    expires_at: datetime
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))




class ProfilesFilters(FilterModel):
    __search_fields__ = [
        "wallet","name","acl_id","token_id","token_name",
    ]

    __sort_fields__ = [
        "wallet",
        "name",
        "acl_id",
        "token_id",
        "token_name",
        
        "created_at",
        "updated_at",
    ]

    created_at: datetime | None
    updated_at: datetime | None


################################# Client Data ###########################


class CreateClientData(BaseModel):
    name: str | None
    


class ClientData(BaseModel):
    id: str
    profiles_id: str
    name: str | None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))




class ClientDataFilters(FilterModel):
    __search_fields__ = [
        "name",
    ]

    __sort_fields__ = [
        "name",
        
        "created_at",
        "updated_at",
    ]

    created_at: datetime | None
    updated_at: datetime | None


