from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str
    phone: str | None = None
    accept_offer: bool = False
    accept_privacy: bool = False
    marketing_opt_in: bool = False

    @model_validator(mode="after")
    def must_accept_legal(self):
        if not self.accept_offer or not self.accept_privacy:
            raise ValueError("Нужно принять оферту и политику персональных данных")
        return self


class LoginIn(BaseModel):
    email: str
    password: str
    totp: str | None = None


class TokenOut(BaseModel):
    token: str
    user_id: str


class OrgIn(BaseModel):
    name: str
    kind: str
    city: str = "Москва"
    confirm_another_workspace: bool = False


class MemberIn(BaseModel):
    user_id: str
    role: str = "manager"
    can_confirm_offer: bool = False


class ArtistIn(BaseModel):
    organization_id: str
    name: str
    city: str = "Москва"
    category: str = "dj"
    media_url: str | None = None
    rider_json: str = "{}"


class VenueIn(BaseModel):
    organization_id: str
    name: str
    city: str = "Москва"
    capacity: int = 100


class TariffIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    honorarium_rub: int = Field(strict=True, ge=0, le=1_000_000_000)
    hours: int = Field(default=2, strict=True, ge=1, le=24)


class SlotIn(BaseModel):
    resource_type: str
    resource_id: str
    starts_at: datetime
    ends_at: datetime
    buffer_before_min: int | None = Field(default=0, ge=0)
    buffer_after_min: int | None = Field(default=0, ge=0)


class EventRequirementIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category_code: str = Field(min_length=1, max_length=32)
    role_label: str = Field(default="", max_length=128)
    qty: int = Field(default=1, strict=True, ge=1, le=20)
    required: bool = True
    sort_order: int | None = Field(default=None, strict=True, ge=0, le=1000)
    notes: str = Field(default="", max_length=4000)


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    organization_id: UUID
    title: str = Field(min_length=1, max_length=255)
    city: str = Field(default="Москва", min_length=1, max_length=128)
    event_date: datetime
    ends_at: datetime | None = None
    event_type: str = Field(default="", max_length=128)
    guest_count: int = Field(default=50, strict=True, ge=1, le=100000)
    budget_rub: int | None = Field(default=None, strict=True, ge=0, le=1_000_000_000)
    notes: str = Field(default="", max_length=16000)
    requirements: list[EventRequirementIn] | None = Field(default=None, max_length=30)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("event_date", "ends_at")
    @classmethod
    def utc_dates(cls, value):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)) if value else None

    @model_validator(mode="after")
    def valid_interval(self):
        if self.ends_at and self.ends_at <= self.event_date:
            raise ValueError("Окончание должно быть позже начала события")
        return self


class RequestCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: Literal["artist", "hall", "venue"]
    resource_id: UUID
    requirement_id: UUID | None = None
    promotion_touch_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=64)


class RequestIn(BaseModel):
    resource_type: str
    resource_id: str
    slot_id: str | None = None


class OfferIn(BaseModel):
    honorarium_rub: int
    terms: str = ""
    slot_id: str


class AckIn(BaseModel):
    side: str
    quote_id: str | None = None


class MessageIn(BaseModel):
    body: str


class SignIn(BaseModel):
    side: str
    otp: str


class PaymentIn(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=64)


class WebhookIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    payment_id: str = Field(min_length=1, max_length=36)
    status: str = Field(min_length=1, max_length=32)
    signature: str = Field(min_length=1, max_length=256)


DISPUTE_CATEGORIES = (
    "no_show",
    "delay",
    "quality",
    "payment",
    "cancel",
)


class DisputeIn(BaseModel):
    category: str
    notes: str = ""

    @field_validator("category")
    @classmethod
    def category_from_list(cls, value: str) -> str:
        if value not in DISPUTE_CATEGORIES:
            raise ValueError("Категория спора должна быть из списка")
        return value


class VerifyIn(BaseModel):
    target_type: str
    target_id: str
    approve: bool
    notes: str = ""


class VenueStatusIn(BaseModel):
    partnership_status: str
    comment: str = Field(default="", max_length=2000)


class VenueModerationIn(BaseModel):
    moderation_status: str
    comment: str = Field(default="", max_length=2000)


PILOT_SERVICE_CATEGORIES = (
    "dj",
    "host",
    "cover",
    "photo",
    "makeup",
    "decor",
    "catering",
    "venue",
)


class ServiceIn(BaseModel):
    organization_id: str
    category_code: str
    title: str
    description: str = ""
    city: str = "Москва"
    published: bool = True
    honorarium_rub: int | None = None

    @field_validator("category_code")
    @classmethod
    def category_from_pilot(cls, value: str) -> str:
        code = (value or "").strip().lower()
        if code not in PILOT_SERVICE_CATEGORIES:
            raise ValueError("category_code: dj|host|cover|photo|makeup|decor|catering|venue")
        return code


class ServiceOut(BaseModel):
    id: str
    organization_id: str
    category_code: str
    title: str
    description: str
    city: str
    published: bool
    honorarium_rub: int | None = None

    model_config = {"from_attributes": True}


class ServiceFromTemplateIn(BaseModel):
    organization_id: str
    template_id: str
    city: str = "Москва"
    honorarium_rub: int | None = None


class TotpEnableIn(BaseModel):
    secret: str = Field(min_length=6, max_length=64)


class ClientEventIn(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_.-]*$")
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=20)


class IcalImportIn(BaseModel):
    organization_id: str
    resource_type: str
    resource_id: str
    ical_url: str | None = None
    ical_body: str | None = None

    @model_validator(mode="after")
    def source_required(self):
        if not self.ical_url and not self.ical_body:
            raise ValueError("Нужен ical_url или ical_body")
        if self.resource_type not in {"artist", "hall"}:
            raise ValueError("resource_type: artist|hall")
        return self


class VacationIn(BaseModel):
    organization_id: str
    resource_type: str
    resource_id: str
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def resource_kind(self):
        if self.resource_type not in {"artist", "hall"}:
            raise ValueError("resource_type: artist|hall")
        return self


class VacationClearIn(BaseModel):
    organization_id: str
    resource_type: str
    resource_id: str

    @model_validator(mode="after")
    def resource_kind(self):
        if self.resource_type not in {"artist", "hall"}:
            raise ValueError("resource_type: artist|hall")
        return self
