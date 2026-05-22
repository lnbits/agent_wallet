from datetime import datetime, timezone
from typing import Any, Literal

from lnbits.db import FilterModel
from pydantic import BaseModel, Field


class CreateAgentPolicy(BaseModel):
    single_payment_limit_sats: int = 100
    daily_limit_sats: int = 1000
    allow_spending: bool = False
    allow_lnurl_pay: bool = False
    allow_lightning_address_pay: bool = False
    allow_lnurl_withdraw: bool = False
    dry_run_required: bool = True
    approval_required_above_sats: int | None = None
    allowed_domains: str | None = None
    allowed_lnurl_domains: str | None = None
    allowed_lightning_addresses: str | None = None
    denied_domains: str | None = None
    denied_lightning_addresses: str | None = None


class AgentPolicy(CreateAgentPolicy):
    id: str
    profile_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateAgentProfile(BaseModel):
    wallet: str
    name: str
    description: str | None = None
    template: str = "agent_wallet"
    acl_id: str
    token_id: str
    token_name: str | None = None
    token_hint: str | None = None
    status: str = "active"
    lightning_address: str | None = None
    lnurlp_id: str | None = None
    expires_at: datetime | None = None
    policy: CreateAgentPolicy | None = None


class UpdateAgentProfile(CreateAgentProfile):
    pass


class AgentProfile(BaseModel):
    id: str
    user_id: str
    wallet: str
    name: str
    description: str | None = None
    template: str = "agent_wallet"
    acl_id: str
    token_id: str
    token_name: str | None = None
    token_hint: str | None = None
    status: str = "active"
    lightning_address: str | None = None
    lnurlp_id: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentProfileFilters(FilterModel):
    __search_fields__ = [
        "wallet",
        "name",
        "acl_id",
        "token_id",
        "token_name",
        "token_hint",
        "lightning_address",
    ]

    __sort_fields__ = [
        "wallet",
        "name",
        "template",
        "token_name",
        "status",
        "created_at",
        "updated_at",
    ]

    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateActivityEvent(BaseModel):
    event_type: str
    amount_sats: int | None = None
    destination: str | None = None
    payment_hash: str | None = None
    checking_id: str | None = None
    status: str
    reason: str | None = None
    task_id: str | None = None
    request_json: str | None = None
    response_json: str | None = None
    metadata: str | None = None


class ActivityEvent(CreateActivityEvent):
    id: str
    wallet: str
    profile_id: str
    token_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActivityEventFilters(FilterModel):
    __search_fields__ = ["event_type", "destination", "payment_hash", "status", "reason", "task_id"]
    __sort_fields__ = ["event_type", "amount_sats", "status", "created_at"]

    created_at: datetime | None = None


class TokenReference(BaseModel):
    acl_id: str
    acl_name: str
    token_id: str
    token_name: str | None = None
    token_hint: str | None = None


class LnurlpStatus(BaseModel):
    installed: bool
    enabled: bool
    enable_url: str = "/api/v1/extension/lnurlp/enable"
    message: str | None = None


class RuntimeStatus(BaseModel):
    profile_id: str
    profile_ready: bool
    policy_ready: bool
    wallet_present: bool
    profile_status: str
    wallet: str
    spending_available: bool
    receiving_available: bool
    dry_run_required: bool
    allow_spending: bool
    allow_lnurl_pay: bool
    allow_lightning_address_pay: bool
    allow_lnurl_withdraw: bool
    single_payment_limit_sats: int
    daily_limit_sats: int
    daily_spent_sats: int
    daily_remaining_sats: int
    approval_required_above_sats: int | None = None
    reasons: list[str] = Field(default_factory=list)


class RuntimeInvoiceRequest(BaseModel):
    amount_sats: int = Field(..., gt=0)
    memo: str | None = None
    expiry: int | None = None
    task_id: str | None = None


class RuntimeInvoiceResponse(BaseModel):
    payment_hash: str | None = None
    checking_id: str | None = None
    payment_request: str | None = None
    bolt11: str | None = None
    amount_sats: int
    memo: str | None = None
    status: str


RuntimeActionType = Literal["bolt11", "lnurl_pay", "lightning_address", "lnurl_withdraw"]


class RuntimePaymentRequest(BaseModel):
    action: RuntimeActionType = "bolt11"
    amount_sats: int | None = Field(None, gt=0)
    destination: str
    payment_request: str | None = None
    comment: str | None = None
    task_id: str | None = None
    dry_run_id: str | None = None
    metadata: dict[str, Any] | None = None


class RuntimePolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    dry_run_required: bool = True
    amount_sats: int
    destination: str
    action: RuntimeActionType
    reasons: list[str] = Field(default_factory=list)
    daily_spent_sats: int = 0
    daily_remaining_sats: int = 0
    dry_run_id: str | None = None


class RuntimePaymentResponse(BaseModel):
    payment_hash: str | None = None
    checking_id: str | None = None
    amount_sats: int
    destination: str
    status: str
    allowed: bool
    reason: str | None = None
