from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


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
    title: str
    honorarium_rub: int
    hours: int = 2


class SlotIn(BaseModel):
    resource_type: str
    resource_id: str
    starts_at: datetime
    ends_at: datetime
    buffer_before_min: int | None = Field(default=0, ge=0)
    buffer_after_min: int | None = Field(default=0, ge=0)


class EventIn(BaseModel):
    organization_id: str
    title: str
    city: str = "Москва"
    event_date: datetime
    guest_count: int = 50
    budget_rub: int | None = None
    notes: str = ""


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
    idempotency_key: str


class WebhookIn(BaseModel):
    event_id: str
    payment_id: str
    status: str
    signature: str


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


class RefundIn(BaseModel):
    payment_id: str
    approver_user_id: str
    totp: str | None = None
    reason: str = ""


class VerifyIn(BaseModel):
    target_type: str
    target_id: str
    approve: bool
    notes: str = ""


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
