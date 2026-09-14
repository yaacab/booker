from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from booker_api.datetime_type import UTCDateTime as DateTime
from booker_api.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["TeamMember"]] = relationship(back_populates="user")
    sessions: Mapped[list["SessionToken"]] = relationship(back_populates="user")


class SessionToken(Base):
    __tablename__ = "session_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    admin_2fa_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))  # customer | artist | venue
    city: Mapped[str] = mapped_column(String(128), default="Москва")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list["TeamMember"]] = relationship(back_populates="organization")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    role: Mapped[str] = mapped_column(String(32), default="owner")
    can_confirm_offer: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="members")


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128), default="Москва")
    category: Mapped[str] = mapped_column(String(64), default="dj")
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rider_json: Mapped[str] = mapped_column(Text, default="{}")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_status: Mapped[str] = mapped_column(String(32), default="pending")


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128), default="Москва")
    capacity: Mapped[int] = mapped_column(Integer, default=100)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_status: Mapped[str] = mapped_column(String(32), default="pending")
    address: Mapped[str] = mapped_column(String(512), default="")
    district: Mapped[str] = mapped_column(String(128), default="")
    metro: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    source_attribution: Mapped[str] = mapped_column(String(128), default="")
    listing_origin: Mapped[str] = mapped_column(String(32), default="owner")  # open_data|owner|seed
    availability_mode: Mapped[str] = mapped_column(String(32), default="owner")  # synthetic|owner
    venue_type: Mapped[str] = mapped_column(String(64), default="")
    administrative_district: Mapped[str] = mapped_column(String(32), default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    official_website: Mapped[str] = mapped_column(String(512), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="owner_submission")
    partnership_status: Mapped[str] = mapped_column(String(32), default="claimed")
    is_partner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_claimed: Mapped[bool] = mapped_column(Boolean, default=True)
    moderation_status: Mapped[str] = mapped_column(String(32), default="published")
    completeness_score: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    partnership_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_freshness_status: Mapped[str] = mapped_column(String(32), default="needs_review")


class VenueHall(Base):
    __tablename__ = "venue_halls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    capacity: Mapped[int] = mapped_column(Integer, default=50)


class VenueSource(Base):
    __tablename__ = "venue_sources"
    __table_args__ = (UniqueConstraint("venue_id", "field_name", "source_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(String(1024))
    source_kind: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VenuePhoto(Base):
    __tablename__ = "venue_photos"
    __table_args__ = (UniqueConstraint("venue_id", "photo_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    photo_url: Mapped[str] = mapped_column(String(1024))
    photo_source_url: Mapped[str] = mapped_column(String(1024))
    photo_rights_status: Mapped[str] = mapped_column(String(32), default="unknown")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class VenueStatusHistory(Base):
    __tablename__ = "venue_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32))
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    comment: Mapped[str] = mapped_column(Text, default="")


class VenueImportBatch(Base):
    __tablename__ = "venue_import_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(128), default="Москва")
    category: Mapped[str] = mapped_column(String(64), default="mixed")
    administrative_district: Mapped[str] = mapped_column(String(32), default="all")
    status: Mapped[str] = mapped_column(String(32), default="running")
    found_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    published_count: Mapped[int] = mapped_column(Integer, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0)
    with_contacts_count: Mapped[int] = mapped_column(Integer, default=0)
    with_prices_count: Mapped[int] = mapped_column(Integer, default=0)
    with_photos_count: Mapped[int] = mapped_column(Integer, default=0)
    with_official_website_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class VenueDuplicateCandidate(Base):
    __tablename__ = "venue_duplicate_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("venue_import_batches.id"), index=True)
    incoming_key: Mapped[str] = mapped_column(String(255))
    existing_venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    resolution: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtistTariff(Base):
    __tablename__ = "artist_tariffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    artist_id: Mapped[str] = mapped_column(ForeignKey("artists.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    honorarium_rub: Mapped[int] = mapped_column(Integer)
    hours: Mapped[int] = mapped_column(Integer, default=2)


class VenueTariff(Base):
    __tablename__ = "venue_tariffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    honorarium_rub: Mapped[int] = mapped_column(Integer)


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resource_type: Mapped[str] = mapped_column(String(16))  # artist | hall
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|held|confirmed|busy
    buffer_before_min: Mapped[int] = mapped_column(Integer, default=0)
    buffer_after_min: Mapped[int] = mapped_column(Integer, default=0)
    external_uid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128), default="Москва")
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), default="")
    guest_count: Mapped[int] = mapped_column(Integer, default=50)
    budget_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="Draft")

    requirements: Mapped[list["EventTeamRequirement"]] = relationship(back_populates="event")


class EventPlan(Base):
    __tablename__ = "event_plans"

    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    selections_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventRepeatPreference(Base):
    """Preferred participants only; never a request, saved plan, quote or reservation."""
    __tablename__ = "event_repeat_preferences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    requirement_id: Mapped[str | None] = mapped_column(ForeignKey("event_team_requirements.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resource_type: Mapped[str] = mapped_column(String(16))
    resource_id: Mapped[str] = mapped_column(String(36))
    hall_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class EventCommandReceipt(Base):
    __tablename__ = "event_command_receipts"

    scope: Mapped[str] = mapped_column(String(128), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CatalogCategory(Base):
    __tablename__ = "catalog_categories"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    group_code: Mapped[str] = mapped_column(String(32), default="other")
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class EventTeamRequirement(Base):
    __tablename__ = "event_team_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    category_code: Mapped[str] = mapped_column(String(32), index=True)
    role_label: Mapped[str] = mapped_column(String(128), default="")
    qty: Mapped[int] = mapped_column(Integer, default=1)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")

    event: Mapped[Event] = relationship(back_populates="requirements")


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    requirement_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_team_requirements.id"), nullable=True, index=True
    )
    resource_type: Mapped[str] = mapped_column(String(16))
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    supplier_org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    status: Mapped[str] = mapped_column(String(32), default="RequestSent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True)
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OfferVersion(Base):
    __tablename__ = "offer_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id"), index=True)
    honorarium_rub: Mapped[int] = mapped_column(Integer)
    commission_rate: Mapped[float] = mapped_column(Float)
    commission_rub: Mapped[int] = mapped_column(Integer)
    total_rub: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    # Null for historic offers: never infer or rewrite their monetary terms.
    customer_service_fee_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_service_fee_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supplier_service_fee_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    supplier_service_fee_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_total_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supplier_payout_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    platform_revenue_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commercial_policy_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    terms: Mapped[str] = mapped_column(Text, default="")
    customer_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    supplier_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id"))
    slot_id: Mapped[str] = mapped_column(ForeignKey("availability_slots.id"))
    status: Mapped[str] = mapped_column(String(32), default="Negotiation")
    payout_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BookingHold(Base):
    __tablename__ = "booking_holds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    slot_id: Mapped[str] = mapped_column(ForeignKey("availability_slots.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="active")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), unique=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    author_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="chat")  # chat | system
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    template_key: Mapped[str] = mapped_column(String(64), default="artist_direct_v1")
    body: Mapped[str] = mapped_column(Text)
    customer_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    supplier_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    otp_customer: Mapped[str | None] = mapped_column(String(8), nullable=True)
    otp_supplier: Mapped[str | None] = mapped_column(String(8), nullable=True)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    amount_rub: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    provider: Mapped[str] = mapped_column(String(32), default="disabled")
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"))
    status: Mapped[str] = mapped_column(String(32))
    response_json: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    notes: Mapped[str] = mapped_column(Text, default="")


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    category: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    decision: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    """Отзыв по завершённой сделке: один на бронь от автора, org_id — профиль контрагента."""

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("booking_id", "author_user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DealAttachment(Base):
    __tablename__ = "deal_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    uploaded_by_user_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Service(Base):
    """Каталожная услуга поверх таксономии. Не заменяет Artist/Venue; honorarium_rub — витрина, не quote."""

    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    category_code: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(128), default="Москва")
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    honorarium_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Favorite(Base):
    """Избранное заказчика: артист или площадка. Не создаёт заявку/hold/бронь (E04)."""

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organization_id",
            "target_type",
            "target_id",
            name="uq_favorites_user_org_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(16))  # artist | venue
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PublicBrief(Base):
    """Добровольный публичный бриф (E18): ограниченный снимок, не приватное событие."""

    __tablename__ = "public_briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128), default="Москва")
    date_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    role_needed: Mapped[str] = mapped_column(String(64), index=True)
    guest_count_band: Mapped[str] = mapped_column(String(32), default="1-50")
    public_notes: Mapped[str] = mapped_column(Text, default="")
    event_type: Mapped[str] = mapped_column(String(64), default="")
    share_budget: Mapped[bool] = mapped_column(Boolean, default=False)
    budget_min_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_max_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    public_requirements_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    responses: Mapped[list["BriefResponse"]] = relationship(back_populates="brief")


class BriefResponse(Base):
    """Отклик поставщика на публичный бриф (E19): интерес/сообщение, без автоброни."""

    __tablename__ = "brief_responses"
    __table_args__ = (UniqueConstraint("brief_id", "supplier_org_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    brief_id: Mapped[str] = mapped_column(ForeignKey("public_briefs.id"), index=True)
    supplier_org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    target_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="interested")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    brief: Mapped[PublicBrief] = relationship(back_populates="responses")


class SharedShortlist(Base):
    """Scoped shared shortlist; historical links remain read-only."""

    __tablename__ = "shared_shortlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(16))  # artist | venue
    title: Mapped[str] = mapped_column(String(255), default="Подборка")
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True, index=True)
    collaborative: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list["SharedShortlistItem"]] = relationship(back_populates="shortlist")


class SharedShortlistItem(Base):
    """Snapshot for shared view: no phones, private budget, or chat."""

    __tablename__ = "shared_shortlist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shortlist_id: Mapped[str] = mapped_column(ForeignKey("shared_shortlists.id"), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    shortlist: Mapped[SharedShortlist] = relationship(back_populates="items")


class ShortlistGuest(Base):
    __tablename__ = "shortlist_guests"
    __table_args__ = (UniqueConstraint("shortlist_id", "secret_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shortlist_id: Mapped[str] = mapped_column(ForeignKey("shared_shortlists.id"), index=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ShortlistFeedback(Base):
    __tablename__ = "shortlist_feedback"
    __table_args__ = (UniqueConstraint("guest_id", "item_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    guest_id: Mapped[str] = mapped_column(ForeignKey("shortlist_guests.id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("shared_shortlist_items.id"), index=True)
    reaction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    comment: Mapped[str] = mapped_column(String(1000), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VenueOwnershipClaim(Base):
    """Claim for open-data/unowned venue listing — does not grant ownership immediately."""

    __tablename__ = "venue_ownership_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    claimant_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    claimant_org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    evidence_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportTicket(Base):
    """Operational support / complaint ticket with human escalation path."""

    __tablename__ = "support_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(64), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    related_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailOutbox(Base):
    """Persisted email delivery for retry without duplicate semantic send (E21)."""

    __tablename__ = "email_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    recipient_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[str] = mapped_column(String(64), default="")
    entity_type: Mapped[str] = mapped_column(String(32), default="notification")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SavedSearch(Base):
    """Saved catalog search for a logged-in customer (W3-SAVED)."""

    __tablename__ = "saved_searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    query_params_json: Mapped[str] = mapped_column(Text, default="{}")
    notify_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommercialPlan(Base):
    __tablename__ = "commercial_plans"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_commercial_plan_version"),
        CheckConstraint("monthly_price_rub >= 0 AND annual_price_rub >= 0"),
        CheckConstraint("supplier_fee_bps >= 0 AND supplier_fee_bps <= 10000"),
        CheckConstraint("customer_fee_bps >= 0 AND customer_fee_bps <= 10000"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(64), index=True)
    audience: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(64))
    monthly_price_rub: Mapped[int] = mapped_column(Integer)
    annual_price_rub: Mapped[int] = mapped_column(Integer)
    supplier_fee_bps: Mapped[int] = mapped_column(Integer)
    customer_fee_bps: Mapped[int] = mapped_column(Integer, default=600)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    features_json: Mapped[str] = mapped_column(Text, default="{}")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("status IN ('pending','trial','active','past_due','cancelled','expired')"),
        CheckConstraint("billing_period IN ('monthly','annual','manual')"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), unique=True)
    plan_code: Mapped[str] = mapped_column(String(64))
    billing_period: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    next_plan_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="disabled")
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_billing_order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BillingOrder(Base):
    __tablename__ = "billing_orders"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_billing_order_idempotency"),
        CheckConstraint("amount_rub >= 0"),
        CheckConstraint("status IN ('created','pending_payment','paid','failed','cancelled','refunded')"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_kind: Mapped[str] = mapped_column(String(32))
    product_code: Mapped[str] = mapped_column(String(64))
    amount_rub: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    status: Mapped[str] = mapped_column(String(32), default="created")
    provider: Mapped[str] = mapped_column(String(32), default="disabled")
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PromotionProduct(Base):
    __tablename__ = "promotion_products"
    __table_args__ = (
        UniqueConstraint("audience", "code", "version", name="uq_promotion_product_version"),
        CheckConstraint("price_rub >= 0 AND duration_hours > 0"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    audience: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    price_rub: Mapped[int] = mapped_column(Integer)
    duration_hours: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PromotionCampaign(Base):
    __tablename__ = "promotion_campaigns"
    __table_args__ = (
        CheckConstraint("target_type IN ('artist','venue')"),
        CheckConstraint("status IN ('draft','pending_payment','scheduled','active','expired','cancelled','rejected')"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    product_code: Mapped[str] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    billing_order_id: Mapped[str | None] = mapped_column(
        ForeignKey("billing_orders.id"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommerceWebhookEvent(Base):
    __tablename__ = "commerce_webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_commerce_webhook_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[str] = mapped_column(String(128))
    order_id: Mapped[str] = mapped_column(ForeignKey("billing_orders.id"))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PromotionCreditUse(Base):
    __tablename__ = "promotion_credit_uses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("promotion_campaigns.id"), unique=True)
    period_key: Mapped[str] = mapped_column(String(7), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_promo_credit_key"),)


class PromotionTouch(Base):
    __tablename__ = "promotion_touches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("promotion_campaigns.id"), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    impressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    request_id: Mapped[str | None] = mapped_column(ForeignKey("requests.id"), nullable=True, unique=True)
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id"), nullable=True, unique=True)


class DiscoverySignal(Base):
    """Deduplicated browser observations; no money or trust is derived from these."""
    __tablename__ = "discovery_signals"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "kind", "visitor_key", "day_key", name="uq_discovery_daily"),
        CheckConstraint("kind IN ('impression', 'profile_view', 'favorite')", name="ck_discovery_kind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    visitor_key: Mapped[str] = mapped_column(String(64))
    day_key: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class OpportunityFilter(Base):
    __tablename__ = "opportunity_filters"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_opportunity_filter_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    query_json: Mapped[str] = mapped_column(Text, default="{}")
    idempotency_key: Mapped[str] = mapped_column(String(64))
    instant_alerts: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OpportunityDelivery(Base):
    __tablename__ = "opportunity_deliveries"
    __table_args__ = (UniqueConstraint("brief_id", "user_id", name="uq_opportunity_delivery"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    brief_id: Mapped[str] = mapped_column(ForeignKey("public_briefs.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    filter_id: Mapped[str] = mapped_column(ForeignKey("opportunity_filters.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtistPresentation(Base):
    __tablename__ = "artist_presentations"

    artist_id: Mapped[str] = mapped_column(ForeignKey("artists.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HallTechnicalProfile(Base):
    __tablename__ = "hall_technical_profiles"

    hall_id: Mapped[str] = mapped_column(ForeignKey("venue_halls.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
