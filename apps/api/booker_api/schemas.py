from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)


class ReconciliationEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider_operation_id: str = Field(min_length=1, max_length=128)
    provider_reference: str = Field(min_length=1, max_length=128)
    operation_kind: Literal["capture", "refund"]
    amount_rub: StrictInt = Field(gt=0, le=2_147_483_647)
    currency: str = Field(min_length=3, max_length=8)
    provider_status: str = Field(min_length=1, max_length=32)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Часовой пояс обязателен")
        return value


class ReconciliationImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: str = Field(min_length=1, max_length=32)
    merchant: str = Field(min_length=1, max_length=128)
    report_id: str = Field(min_length=1, max_length=128)
    period_start: datetime
    period_end: datetime
    complete: StrictBool = True
    entries: list[ReconciliationEntryIn] = Field(max_length=500)
    totp: str = Field(min_length=6, max_length=8)

    @field_validator("period_start", "period_end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Часовой пояс обязателен")
        return value


class ReconciliationResolutionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    resolution: str = Field(min_length=10, max_length=2000)
    totp: str = Field(min_length=6, max_length=8)


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str
    phone: str | None = None
    accept_offer: StrictBool = False
    accept_privacy: StrictBool = False
    accept_processing: StrictBool = False
    marketing_opt_in: StrictBool = False
    accepted_documents: list["AcceptedDocumentIn"] = Field(default_factory=list, max_length=8)
    draft_test_acknowledgement: StrictBool = False

    @model_validator(mode="after")
    def must_accept_legal(self):
        if not self.accept_offer or not self.accept_privacy or not self.accept_processing:
            raise ValueError("Нужно подтвердить оферту, политику и отдельное согласие на обработку")
        return self


class AcceptedDocumentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Literal["offer", "privacy", "consent_texts"]
    version: str = Field(min_length=1, max_length=64)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class LoginIn(BaseModel):
    email: str
    password: str
    totp: str | None = None


class ExternalPaymentReportIn(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=64)
    reference: str = Field(min_length=3, max_length=128)
    details: str = Field(default="", max_length=1000)


class ExternalPaymentReviewIn(BaseModel):
    report_id: str = Field(min_length=1, max_length=36)
    review_note: str = Field(min_length=3, max_length=1000)
    recipient_confirmed: bool = False


class ExternalPaymentAckIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    idempotency_key: str = Field(min_length=8, max_length=64)


class ExternalPaymentCorrectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    report_id: str = Field(min_length=1, max_length=36)
    target_event_id: str = Field(min_length=1, max_length=36)
    reason_code: Literal["wrong_report", "recipient_denied", "duplicate", "partial", "disputed", "other"]
    note: str = Field(min_length=3, max_length=500)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=64)


class ExternalPaymentCorrectionApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_event_id: str = Field(min_length=1, max_length=36)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=64)


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


class OrganizationInvitationIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = "manager"
    can_confirm_offer: bool = False
    idempotency_key: str = Field(min_length=1, max_length=64)


class OrganizationInvitationAcceptIn(BaseModel):
    token: str = Field(min_length=20, max_length=256)


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


class ArtistPublicationEvidenceIn(BaseModel):
    media_url: str = Field(min_length=1, max_length=512)
    media_source_url: str = Field(min_length=1, max_length=512)
    media_rights_status: Literal["owned", "licensed", "official_permission"]
    rights_attested: bool
    calendar_confirmed_through: datetime

    @field_validator("media_url", "media_source_url")
    @classmethod
    def media_url_is_public(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("https://", "/")):
            raise ValueError("media_url должен быть HTTPS URL или локальным публичным путём")
        return value


class VenuePublicationEvidenceIn(BaseModel):
    calendar_confirmed_through: datetime


class VenuePhotoIn(BaseModel):
    photo_url: str = Field(min_length=1, max_length=1024)
    photo_source_url: str = Field(min_length=1, max_length=1024)
    photo_rights_status: Literal["owned", "licensed", "official_permission"]
    rights_attested: bool
    sort_order: int = Field(default=0, ge=0)

    @field_validator("photo_url", "photo_source_url")
    @classmethod
    def photo_url_is_public(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("https://", "/")):
            raise ValueError("URL должен быть HTTPS или локальным публичным путём")
        return value


class PublicationStateIn(BaseModel):
    enabled: bool
    state_version: int = Field(ge=0)


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
    advance_rub: int | None = Field(default=None, ge=1)
    security_deposit_rub: int = Field(default=0, ge=0)


class AckIn(BaseModel):
    side: str
    quote_id: str | None = None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=64)


SupportRelatedType = Literal["event", "booking", "payment", "message"]


class SupportTicketIn(BaseModel):
    organization_id: str | None = None
    category: Literal[
        "profile",
        "brief",
        "message",
        "review",
        "media",
        "payment",
        "incident",
        "technical",
        "other",
    ]
    subject: str = Field(min_length=3, max_length=255)
    body: str = Field(min_length=3, max_length=8000)
    related_type: SupportRelatedType | None = None
    related_id: str | None = Field(default=None, min_length=1, max_length=36)

    @field_validator("subject", "body")
    @classmethod
    def strip_support_text(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Введите не менее трёх символов")
        return normalized

    @model_validator(mode="after")
    def related_reference_is_complete(self):
        if (self.related_type is None) != (self.related_id is None):
            raise ValueError("related_type и related_id передаются вместе")
        if self.related_id is not None:
            self.related_id = self.related_id.strip()
            if not self.related_id:
                raise ValueError("related_id не может быть пустым")
        return self


class SupportMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)

    @field_validator("body")
    @classmethod
    def strip_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Введите текст сообщения")
        return normalized


class SupportOperatorNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)

    @field_validator("body")
    @classmethod
    def strip_note(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Введите текст заметки")
        return normalized


class SupportAgentSessionIn(BaseModel):
    organization_id: str | None = None
    related_type: SupportRelatedType | None = None
    related_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def related_reference_is_complete(self):
        if (self.related_type is None) != (self.related_id is None):
            raise ValueError("related_type и related_id передаются вместе")
        if self.related_id is not None:
            self.related_id = self.related_id.strip()
            if not self.related_id:
                raise ValueError("related_id не может быть пустым")
        return self


class SupportAgentMessageIn(BaseModel):
    message: str = Field(min_length=3, max_length=4000)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Введите не менее трёх символов")
        return normalized


class SupportAgentEscalationIn(BaseModel):
    reason_code: Literal[
        "user_requested_human",
        "not_solved",
        "money_or_legal",
        "account_security",
        "event_day_no_show",
        "paid_not_confirmed",
        "other",
    ] = "user_requested_human"


class SupportAgentFeedbackIn(BaseModel):
    rating: Literal["helpful", "not_helpful"]
    reason_code: Literal["incorrect", "unsafe", "unclear", "not_solved", "other"] | None = None
    comment: str = Field(default="", max_length=1000)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, value: str) -> str:
        return value.strip()


class SignIn(BaseModel):
    side: str | None = None
    otp: str
    body_hash: str


class PaymentIn(BaseModel):
    idempotency_key: str
    obligation_id: str | None = None


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
    notes: str = Field(default="", max_length=8000)

    @field_validator("category")
    @classmethod
    def category_from_list(cls, value: str) -> str:
        if value not in DISPUTE_CATEGORIES:
            raise ValueError("Категория спора должна быть из списка")
        return value


class DisputeEvidenceIn(BaseModel):
    attachment_id: str = Field(min_length=1, max_length=36)
    note: str = Field(default="", max_length=2000)


class DisputeAssignmentIn(BaseModel):
    assignee_user_id: str = Field(min_length=1, max_length=36)
    state_version: int = Field(ge=0)
    totp: str | None = None


class DisputeResolutionIn(BaseModel):
    decision_kind: Literal[
        "information_only",
        "service_adjustment_recommended",
        "refund_review_required",
        "rejected",
    ]
    decision_note: str = Field(min_length=3, max_length=8000)
    state_version: int = Field(ge=0)
    totp: str | None = None


class RefundRequestIn(BaseModel):
    payment_id: str
    totp: str | None = None
    reason: str = ""


class RefundApproveIn(BaseModel):
    totp: str | None = None


class AttachmentScanDecisionIn(BaseModel):
    scan_status: str
    note: str = Field(default="", max_length=1000)
    totp: str | None = None

    @field_validator("scan_status")
    @classmethod
    def status_from_list(cls, value: str) -> str:
        if value not in {"clean", "blocked"}:
            raise ValueError("scan_status должен быть clean или blocked")
        return value


class AttachmentScanRunIn(BaseModel):
    totp: str | None = None


class VerifyIn(BaseModel):
    target_type: Literal["artist", "venue"]
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
    resource_type: Literal["artist", "venue"] | None = None
    resource_id: str | None = None
    category_code: str
    title: str
    description: str = ""
    city: str = "Москва"
    published: bool = True
    honorarium_rub: int | None = None

    @model_validator(mode="after")
    def profile_binding_is_complete(self):
        if (self.resource_type is None) != (self.resource_id is None):
            raise ValueError("resource_type и resource_id нужны вместе")
        return self

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
    resource_type: str | None = None
    resource_id: str | None = None
    category_code: str
    title: str
    description: str
    city: str
    published: bool
    honorarium_rub: int | None = None

    model_config = {"from_attributes": True}


class ServiceProfileBindingIn(BaseModel):
    resource_type: Literal["artist", "venue"]
    resource_id: str = Field(min_length=1, max_length=36)


class ServiceFromTemplateIn(BaseModel):
    organization_id: str
    resource_type: Literal["artist", "venue"] | None = None
    resource_id: str | None = None
    template_id: str
    city: str = "Москва"
    honorarium_rub: int | None = None

    @model_validator(mode="after")
    def profile_binding_is_complete(self):
        if (self.resource_type is None) != (self.resource_id is None):
            raise ValueError("resource_type и resource_id нужны вместе")
        return self


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
