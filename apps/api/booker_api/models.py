from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from booker_api.db import Base
from booker_api.totp_storage import EncryptedTotpSecret


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
    is_support_operator: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret: Mapped[str | None] = mapped_column(EncryptedTotpSecret(), nullable=True)
    active_organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    optional_processing_restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_consent_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # NULL required_at means a pre-verification legacy account, not proof of ownership.
    email_verification_required_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["TeamMember"]] = relationship(back_populates="user")
    sessions: Mapped[list["SessionToken"]] = relationship(back_populates="user")
    identities: Mapped[list["UserIdentity"]] = relationship(back_populates="user")


class UserIdentity(Base):
    """External login identity; provider claims never imply Booker email proof."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_user_identity_subject"),
        UniqueConstraint("user_id", "provider", name="uq_user_identity_user_provider"),
        CheckConstraint("provider IN ('telegram','yandex','vk')", name="ck_user_identity_provider"),
        CheckConstraint("length(provider_subject) > 0", name="ck_user_identity_subject"),
        CheckConstraint("link_origin IN ('first_login','explicit_link')",
                        name="ck_user_identity_link_origin"),
        Index("ix_user_identities_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_email_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    provider_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    link_origin: Mapped[str] = mapped_column(String(16), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="identities")


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


class StaffRecoveryCode(Base):
    __tablename__ = "staff_recovery_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailVerificationChallenge(Base):
    __tablename__ = "email_verification_challenges"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    target_email: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "invited_by_user_id",
            "idempotency_key",
            name="uq_organization_invitation_actor_idempotency",
        ),
        Index(
            "uq_organization_invitation_pending_email",
            "organization_id",
            "email",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    invited_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(32))
    can_confirm_offer: Mapped[bool] = mapped_column(Boolean, default=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    invited_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128), default="Москва")
    category: Mapped[str] = mapped_column(String(64), default="dj")
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_rights_status: Mapped[str] = mapped_column(String(32), default="unknown")
    media_rights_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    media_rights_attested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    calendar_confirmed_through: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    calendar_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calendar_confirmed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    publication_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    publication_state_version: Mapped[int] = mapped_column(Integer, default=0)
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
    calendar_confirmed_through: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    calendar_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calendar_confirmed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    publication_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    publication_state_version: Mapped[int] = mapped_column(Integer, default=0)
    address: Mapped[str] = mapped_column(String(512), default="")
    district: Mapped[str] = mapped_column(String(128), default="")
    metro: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    source_attribution: Mapped[str] = mapped_column(String(128), default="")
    listing_origin: Mapped[str] = mapped_column(String(32), default="owner")  # open_data|owner|seed
    availability_mode: Mapped[str] = mapped_column(String(32), default="owner")  # research|owner
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
    rights_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rights_attested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
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
    guest_count: Mapped[int] = mapped_column(Integer, default=50)
    budget_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="Draft")

    requirements: Mapped[list["EventTeamRequirement"]] = relationship(back_populates="event")


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
    advance_rub: Mapped[int] = mapped_column(Integer, default=0)
    balance_rub: Mapped[int] = mapped_column(Integer, default=0)
    security_deposit_rub: Mapped[int] = mapped_column(Integer, default=0)
    payment_terms_json: Mapped[str] = mapped_column(Text, default="{}")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    terms: Mapped[str] = mapped_column(Text, default="")
    customer_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    supplier_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OfferAcknowledgement(Base):
    __tablename__ = "offer_acknowledgements"
    __table_args__ = (
        UniqueConstraint("offer_version_id", "side"),
        UniqueConstraint("offer_version_id", "actor_user_id"),
        CheckConstraint("side IN ('customer', 'supplier')", name="ck_offer_ack_side"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    offer_version_id: Mapped[str] = mapped_column(ForeignKey("offer_versions.id"), index=True)
    side: Mapped[str] = mapped_column(String(16))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attribution_status: Mapped[str] = mapped_column(String(32), default="attributed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id"))
    accepted_offer_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("offer_versions.id"), nullable=True
    )
    slot_id: Mapped[str] = mapped_column(ForeignKey("availability_slots.id"))
    status: Mapped[str] = mapped_column(String(32), default="Negotiation")
    payout_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    payout_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    payout_block_reason: Mapped[str] = mapped_column(String(64), default="")
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
    request_id: Mapped[str | None] = mapped_column(
        ForeignKey("requests.id"), unique=True, nullable=True
    )
    booking_id: Mapped[str | None] = mapped_column(
        ForeignKey("bookings.id"), unique=True, nullable=True
    )
    customer_org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    supplier_org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    customer_name_snapshot: Mapped[str] = mapped_column(String(255))
    supplier_name_snapshot: Mapped[str] = mapped_column(String(255))
    next_message_sequence: Mapped[int] = mapped_column(Integer, default=1)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    author_org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    author_side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    author_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attribution_status: Mapped[str] = mapped_column(
        String(32), default="legacy_unattributed"
    )
    kind: Mapped[str] = mapped_column(String(16), default="chat")  # chat | system
    body: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=utcnow
    )

    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence"),
        CheckConstraint(
            "(attribution_status = 'system' AND kind = 'system' "
            "AND author_user_id IS NULL AND author_org_id IS NULL "
            "AND author_side IS NULL AND author_name_snapshot IS NULL "
            "AND actor_role_snapshot IS NULL) OR "
            "(attribution_status = 'legacy_unattributed' AND author_org_id IS NULL "
            "AND author_side IS NULL) OR "
            "(attribution_status = 'attributed' AND kind = 'chat' "
            "AND author_user_id IS NOT NULL AND author_org_id IS NOT NULL "
            "AND author_side IN ('customer', 'supplier') "
            "AND author_name_snapshot IS NOT NULL AND actor_role_snapshot IS NOT NULL)",
            name="ck_message_actor_attribution",
        ),
        Index(
            "uq_message_conversation_idempotency",
            "conversation_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class ConversationReadState(Base):
    __tablename__ = "conversation_read_states"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "user_id",
            "organization_id",
            name="uq_conversation_read_state_party",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    last_read_sequence: Mapped[int] = mapped_column(Integer, default=0)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(Message, "before_insert")
def _assign_message_sequence(_mapper, connection, target: Message) -> None:
    """Allocate one monotonic position inside a conversation in the current transaction."""
    if not target.attribution_status:
        target.attribution_status = (
            "system" if target.kind == "system" else "legacy_unattributed"
        )
    if target.sequence is not None:
        return
    target.sequence = connection.execute(
        text(
            "UPDATE conversations SET next_message_sequence = next_message_sequence + 1 "
            "WHERE id = :conversation_id RETURNING next_message_sequence - 1"
        ),
        {"conversation_id": target.conversation_id},
    ).scalar_one()


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (UniqueConstraint("booking_id", name="uq_contract_booking"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    template_key: Mapped[str] = mapped_column(String(64), default="artist_direct_v1")
    body: Mapped[str] = mapped_column(Text)
    offer_version_id: Mapped[str | None] = mapped_column(ForeignKey("offer_versions.id"), nullable=True)
    body_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effect: Mapped[str] = mapped_column(String(48), default="legacy_unbound", server_default="legacy_unbound")
    legal_pack_version: Mapped[str] = mapped_column(String(48), default="legacy_unknown", server_default="legacy_unknown")
    customer_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    supplier_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    otp_customer: Mapped[str | None] = mapped_column(String(8), nullable=True)
    otp_supplier: Mapped[str | None] = mapped_column(String(8), nullable=True)


class ContractSignature(Base):
    __tablename__ = "contract_signatures"
    __table_args__ = (
        UniqueConstraint("contract_id", "side"),
        UniqueConstraint("contract_id", "actor_user_id"),
        CheckConstraint("side IN ('customer', 'supplier')", name="ck_contract_signature_side"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    side: Mapped[str] = mapped_column(String(16))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    offer_version_id: Mapped[str | None] = mapped_column(ForeignKey("offer_versions.id"), nullable=True)
    body_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effect: Mapped[str] = mapped_column(String(48), default="legacy_unbound", server_default="legacy_unbound")
    auth_method: Mapped[str] = mapped_column(String(16), default="otp")
    attribution_status: Mapped[str] = mapped_column(String(32), default="attributed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContractChallenge(Base):
    __tablename__ = "contract_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    side: Mapped[str] = mapped_column(String(16))
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    otp_hash: Mapped[str] = mapped_column(String(160))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@event.listens_for(OfferAcknowledgement, "before_update")
@event.listens_for(OfferAcknowledgement, "before_delete")
@event.listens_for(ContractSignature, "before_update")
@event.listens_for(ContractSignature, "before_delete")
def _reject_deal_attestation_mutation(*_args) -> None:
    raise ValueError("Подтверждения и подписи сделки неизменяемы")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index(
            "uq_payments_active_obligation",
            "obligation_id",
            unique=True,
            sqlite_where=text(
                "obligation_id IS NOT NULL AND status IN "
                "('pending', 'succeeded', 'external_recorded')"
            ),
            postgresql_where=text(
                "obligation_id IS NOT NULL AND status IN "
                "('pending', 'succeeded', 'external_recorded')"
            ),
        ),
        Index(
            "uq_payments_provider_reference",
            "provider",
            "provider_merchant",
            "provider_reference",
            unique=True,
            sqlite_where=text("provider_reference IS NOT NULL"),
            postgresql_where=text("provider_reference IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    obligation_id: Mapped[str | None] = mapped_column(
        ForeignKey("payment_obligations.id"), nullable=True, index=True
    )
    amount_rub: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    provider: Mapped[str] = mapped_column(String(32), default="stub")
    provider_merchant: Mapped[str] = mapped_column(String(128), default="")
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    external_evidence_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentPlan(Base):
    __tablename__ = "payment_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    offer_version_id: Mapped[str] = mapped_column(
        ForeignKey("offer_versions.id"), unique=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentObligation(Base):
    __tablename__ = "payment_obligations"
    __table_args__ = (UniqueConstraint("plan_id", "kind"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("payment_plans.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    amount_rub: Mapped[int] = mapped_column(Integer)
    recipient: Mapped[str] = mapped_column(String(32), default="supplier")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    required_before_check_in: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    satisfied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(OfferVersion, "before_update")
def _reject_offer_payment_terms_mutation(_mapper, _connection, target: OfferVersion) -> None:
    if inspect(target).attrs.payment_terms_json.history.has_changes():
        raise ValueError("Условия платёжного графика версии оффера неизменяемы")


@event.listens_for(PaymentObligation, "before_update")
def _reject_obligation_deadline_mutation(_mapper, _connection, target: PaymentObligation) -> None:
    state = inspect(target).attrs
    if any(
        field.history.has_changes()
        for field in (state.due_at, state.grace_until, state.required_before_check_in)
    ):
        raise ValueError("Сроки платёжного обязательства неизменяемы")


class MoneyMovement(Base):
    """Immutable record of funds actually controlled by the payment provider."""

    __tablename__ = "money_movements"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "kind", name="uq_money_movement_source"),
        Index(
            "uq_money_movement_capture_payment",
            "payment_id",
            unique=True,
            sqlite_where=text("kind = 'capture'"),
            postgresql_where=text("kind = 'capture'"),
        ),
        CheckConstraint("amount_rub > 0", name="ck_money_movement_positive_amount"),
        CheckConstraint("direction IN ('credit', 'debit')", name="ck_money_movement_direction"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    obligation_id: Mapped[str | None] = mapped_column(
        ForeignKey("payment_obligations.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(8))
    amount_rub: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    provider: Mapped[str] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(128))
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        UniqueConstraint("provider", "merchant", "report_id"),
        UniqueConstraint("provider", "merchant", "content_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    merchant: Mapped[str] = mapped_column(String(128))
    report_id: Mapped[str] = mapped_column(String(128))
    content_sha256: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="processing")
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReconciliationEntry(Base):
    __tablename__ = "reconciliation_entries"
    __table_args__ = (
        UniqueConstraint("run_id", "line_no"),
        UniqueConstraint(
            "provider",
            "merchant",
            "provider_operation_id",
            name="uq_reconciliation_provider_operation",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    merchant: Mapped[str] = mapped_column(String(128))
    line_no: Mapped[int] = mapped_column(Integer)
    provider_operation_id: Mapped[str] = mapped_column(String(128), index=True)
    provider_reference: Mapped[str] = mapped_column(String(128), index=True)
    operation_kind: Mapped[str] = mapped_column(String(32))
    amount_rub: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    provider_status: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconciliationDiscrepancy(Base):
    __tablename__ = "reconciliation_discrepancies"
    __table_args__ = (UniqueConstraint("run_id", "fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(64), index=True)
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    movement_id: Mapped[str | None] = mapped_column(
        ForeignKey("money_movements.id"), nullable=True
    )
    entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("reconciliation_entries.id"), nullable=True
    )
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="open")
    resolution: Mapped[str] = mapped_column(Text, default="")
    resolved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(ReconciliationRun, "before_update")
def _reject_reconciliation_run_identity_mutation(
    _mapper, _connection, target: ReconciliationRun
) -> None:
    state = inspect(target).attrs
    fields = (
        state.provider,
        state.merchant,
        state.report_id,
        state.content_sha256,
        state.period_start,
        state.period_end,
        state.received_at,
    )
    if any(field.history.has_changes() for field in fields):
        raise ValueError("Идентичность запуска сверки неизменяема")


@event.listens_for(ReconciliationDiscrepancy, "before_update")
def _reject_reconciliation_discrepancy_identity_mutation(
    _mapper, _connection, target: ReconciliationDiscrepancy
) -> None:
    state = inspect(target).attrs
    fields = (
        state.run_id,
        state.fingerprint,
        state.kind,
        state.booking_id,
        state.payment_id,
        state.movement_id,
        state.entry_id,
        state.details_json,
        state.created_at,
    )
    if any(field.history.has_changes() for field in fields):
        raise ValueError("Идентичность расхождения неизменяема")


@event.listens_for(ReconciliationRun, "before_delete")
@event.listens_for(ReconciliationDiscrepancy, "before_delete")
def _reject_reconciliation_audit_deletion(_mapper, _connection, _target) -> None:
    raise ValueError("Записи сверки нельзя удалять")


@event.listens_for(ReconciliationEntry, "before_update")
@event.listens_for(ReconciliationEntry, "before_delete")
def _reject_reconciliation_entry_mutation(*_args) -> None:
    raise ValueError("Строки реестра сверки неизменяемы")


@event.listens_for(MoneyMovement, "before_update")
@event.listens_for(MoneyMovement, "before_delete")
def _reject_money_movement_mutation(*_args) -> None:
    raise ValueError("Денежные движения неизменяемы; добавьте компенсирующую запись")


class RefundRequest(Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        Index(
            "uq_refund_request_pending_payment",
            "payment_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    amount_rub: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    refund_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExternalPaymentReport(Base):
    __tablename__ = "external_payment_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    submitted_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reference: Mapped[str] = mapped_column(String(128))
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    reviewed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExternalPaymentEvent(Base):
    """Append-only external transfer evidence and correction decisions; never a bank capture."""

    __tablename__ = "external_payment_events"
    __table_args__ = (UniqueConstraint("idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("external_payment_reports.id"), index=True)
    parent_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("external_payment_events.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    expected_version: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(ExternalPaymentEvent, "before_update")
@event.listens_for(ExternalPaymentEvent, "before_delete")
def _reject_external_payment_event_mutation(*_args) -> None:
    raise ValueError("Событие внешнего платежа неизменяемо")


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


class UserNotification(Base):
    """Durable, recipient-indexed notice containing no free-form or secret body."""

    __tablename__ = "user_notifications"
    __table_args__ = (
        UniqueConstraint("recipient_user_id", "template", "entity_type", "entity_id",
                         name="uq_user_notification_event"),
        Index("ix_user_notifications_recipient_created", "recipient_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportNotificationTarget(Base):
    """Explicit staff destination; email resolves from the verified User row."""

    __tablename__ = "support_notification_targets"
    __table_args__ = (
        UniqueConstraint(
            "recipient_user_id", "channel", "escalation_level",
            name="uq_support_notification_target",
        ),
        CheckConstraint(
            "channel IN ('cabinet','email','telegram')",
            name="ck_support_notification_target_channel",
        ),
        CheckConstraint(
            "escalation_level IN ('primary','backup','administrator')",
            name="ck_support_notification_target_level",
        ),
        Index(
            "uq_support_notification_target_active_staff_level",
            "channel", "escalation_level", unique=True,
            sqlite_where=text("active = 1 AND escalation_level IN ('primary','backup')"),
            postgresql_where=text("active = true AND escalation_level IN ('primary','backup')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    escalation_level: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Calendar changes require a reviewed policy; the current API writes only this schedule.
    schedule_json: Mapped[str] = mapped_column(
        Text,
        default='{"timezone":"Europe/Moscow","weekdays":[0,1,2,3,4,5,6],"start":"10:00","end":"22:00"}',
    )
    state_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LegalDocumentVersion(Base):
    __tablename__ = "legal_document_versions"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_legal_document_key_version"),
        Index("uq_legal_document_published_key", "key", unique=True,
              sqlite_where=text("status = 'published'"),
              postgresql_where=text("status = 'published'")),
        CheckConstraint("length(trim(key)) > 0", name="ck_legal_document_key"),
        CheckConstraint("length(trim(version)) > 0", name="ck_legal_document_version"),
        CheckConstraint("status IN ('draft','published','retired')", name="ck_legal_document_status"),
        CheckConstraint(
            "(status = 'draft' AND published_at IS NULL AND retired_at IS NULL)"
            " OR (status = 'published' AND published_at IS NOT NULL AND retired_at IS NULL"
            " AND content_hash IS NOT NULL AND length(content_hash) = 64"
            " AND length(trim(source_path)) > 0)"
            " OR (status = 'retired' AND published_at IS NOT NULL AND retired_at IS NOT NULL"
            " AND content_hash IS NOT NULL AND length(content_hash) = 64"
            " AND length(trim(source_path)) > 0)", name="ck_legal_document_lifecycle",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(48), index=True)
    version: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    source_path: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsentEvent(Base):
    __tablename__ = "consent_events"
    __table_args__ = (
        CheckConstraint("action IN ('accepted','withdrawn')", name="ck_consent_action"),
        CheckConstraint("kind IN ('offer','privacy','processing','marketing_email')", name="ck_consent_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    document_version_id: Mapped[str | None] = mapped_column(ForeignKey("legal_document_versions.id"), nullable=True)
    document_version: Mapped[str] = mapped_column(String(64))
    document_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    notes: Mapped[str] = mapped_column(Text, default="")


class Dispute(Base):
    __tablename__ = "disputes"
    __table_args__ = (
        Index(
            "uq_disputes_active_booking",
            "booking_id",
            unique=True,
            sqlite_where=text("status IN ('open', 'in_review')"),
            postgresql_where=text("status IN ('open', 'in_review')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    opened_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    priority: Mapped[str] = mapped_column(String(16), default="high", index=True)
    response_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    decision_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(Text, default="")
    resolved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DisputeEvidence(Base):
    __tablename__ = "dispute_evidence"
    __table_args__ = (UniqueConstraint("dispute_id", "attachment_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dispute_id: Mapped[str] = mapped_column(ForeignKey("disputes.id"), index=True)
    attachment_id: Mapped[str] = mapped_column(ForeignKey("deal_attachments.id"), index=True)
    submitted_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
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
    scan_status: Mapped[str] = mapped_column(String(32), default="quarantined")
    scan_note: Mapped[str] = mapped_column(Text, default="")
    av_verdict_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    av_verdict_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    av_scan_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    av_scan_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scanned_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Service(Base):
    """Каталожная услуга поверх таксономии. Не заменяет Artist/Venue; honorarium_rub — витрина, не quote."""

    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="interested")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    brief: Mapped[PublicBrief] = relationship(back_populates="responses")


class SharedShortlist(Base):
    """Read-only shared shortlist with token; revoke removes access (E22)."""

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
    __table_args__ = (
        UniqueConstraint(
            "author_user_id",
            "idempotency_key_hash",
            name="uq_support_ticket_author_idempotency",
        ),
        CheckConstraint(
            "(accepted_by_user_id IS NULL AND accepted_at IS NULL) OR "
            "(accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL "
            "AND assigned_to_user_id IS NOT NULL "
            "AND accepted_by_user_id = assigned_to_user_id)",
            name="ck_support_ticket_acceptance",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    accepted_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(64), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    related_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal", server_default="normal", index=True)
    urgency_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    response_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    overdue_escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportMessage(Base):
    """Private support conversation, isolated from commercial deal messages."""

    __tablename__ = "support_messages"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "author_user_id",
            "idempotency_key_hash",
            name="uq_support_message_actor_idempotency",
        ),
        CheckConstraint(
            "author_kind IN ('user', 'operator')",
            name="ck_support_message_author_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("support_tickets.id"), index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    author_kind: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportOperatorNote(Base):
    """Operator-only notes, never projected through customer support endpoints."""

    __tablename__ = "support_operator_notes"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "author_user_id",
            "idempotency_key_hash",
            name="uq_support_note_actor_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("support_tickets.id"), index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportAgentSession(Base):
    """User-owned, bounded assistant session; no operator notes or deal mutations."""

    __tablename__ = "support_agent_sessions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key_hash",
            name="uq_support_agent_session_user_idempotency",
        ),
        CheckConstraint(
            "status IN ('active', 'escalated', 'closed')",
            name="ck_support_agent_session_status",
        ),
        CheckConstraint(
            "(status = 'active' AND ticket_id IS NULL AND escalated_at IS NULL) OR "
            "(status = 'escalated' AND ticket_id IS NOT NULL AND escalated_at IS NOT NULL) OR "
            "status = 'closed'",
            name="ck_support_agent_session_escalation_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    related_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    ticket_id: Mapped[str | None] = mapped_column(
        ForeignKey("support_tickets.id"), nullable=True, unique=True
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    escalation_idempotency_key_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    escalation_request_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportAgentExchange(Base):
    """Persisted user/assistant pair with source IDs, never chain-of-thought."""

    __tablename__ = "support_agent_exchanges"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "idempotency_key_hash",
            name="uq_support_agent_exchange_session_idempotency",
        ),
        CheckConstraint(
            "outcome IN ('answered', 'clarify', 'needs_human')",
            name="ck_support_agent_exchange_outcome",
        ),
        CheckConstraint(
            "(outcome = 'needs_human' AND needs_human = true) OR "
            "(outcome != 'needs_human' AND needs_human = false)",
            name="ck_support_agent_exchange_handoff",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("support_agent_sessions.id"), index=True
    )
    user_message: Mapped[str] = mapped_column(Text)
    assistant_message: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    needs_human: Mapped[bool] = mapped_column(Boolean, default=False)
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportAgentFeedback(Base):
    """One user rating per assistant exchange."""

    __tablename__ = "support_agent_feedback"
    __table_args__ = (
        UniqueConstraint(
            "exchange_id", "user_id", name="uq_support_agent_feedback_exchange_user"
        ),
        CheckConstraint(
            "rating IN ('helpful', 'not_helpful')",
            name="ck_support_agent_feedback_rating",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exchange_id: Mapped[str] = mapped_column(
        ForeignKey("support_agent_exchanges.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    rating: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
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


class DataSubjectRequest(Base):
    __tablename__ = "data_subject_requests"
    __table_args__ = (
        UniqueConstraint("subject_user_id", "idempotency_key_hash", name="uq_subject_request_idempotency"),
        CheckConstraint("request_type IN ('access','export','restrict','delete','correct')", name="ck_subject_request_type"),
        CheckConstraint("status IN ('pending','in_review','needs_info','approved','rejected','completed','cancelled')",
                        name="ck_subject_request_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    subject_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(16), index=True)
    correction_field: Mapped[str | None] = mapped_column(String(32), nullable=True)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    decided_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataSubjectRequestEvent(Base):
    __tablename__ = "data_subject_request_events"
    __table_args__ = (
        UniqueConstraint("request_id", "state_version", name="uq_subject_event_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("data_subject_requests.id"), index=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LegalHold(Base):
    __tablename__ = "legal_holds"
    __table_args__ = (
        Index("uq_legal_holds_active_subject", "subject_user_id", unique=True,
              sqlite_where=text("released_at IS NULL"),
              postgresql_where=text("released_at IS NULL")),
        CheckConstraint("scope = 'user'", name="ck_legal_hold_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    subject_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(String(16), default="user")
    reason_code: Mapped[str] = mapped_column(String(32))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    released_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RateLimitCounter(Base):
    """Opaque fixed-window counter shared by API workers."""

    __tablename__ = "rate_limit_counters"

    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[int] = mapped_column(BigInteger, index=True)
    hits: Mapped[int] = mapped_column(Integer)
