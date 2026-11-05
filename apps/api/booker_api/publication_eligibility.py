"""Single server-side gate for public supply profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    TeamMember,
    Venue,
    VenueHall,
    VenuePhoto,
    VenueTariff,
)
from booker_api.security import aware, now

PUBLIC_MEDIA_RIGHTS = frozenset({"owned", "licensed", "official_permission"})
PUBLICATION_HORIZON_DAYS = 30


@dataclass(frozen=True)
class PublicationEligibility:
    eligible: bool
    checks: dict[str, bool]

    @property
    def reason_codes(self) -> list[str]:
        return [code for code, passed in self.checks.items() if not passed]


def _has_representative(db: Session, organization_id: str) -> bool:
    return (
        db.query(TeamMember.id)
        .filter(
            TeamMember.organization_id == organization_id,
            TeamMember.role.in_(("owner", "admin")),
        )
        .first()
        is not None
    )


def _required_horizon(required_through: datetime | None = None) -> datetime:
    baseline = now() + timedelta(days=PUBLICATION_HORIZON_DAYS)
    if required_through and aware(required_through) > baseline:
        return aware(required_through)
    return baseline


def _artist_checks(
    artist: Artist,
    *,
    has_tariff: bool,
    has_representative: bool,
    has_entry: bool,
    required_through: datetime | None,
) -> dict[str, bool]:
    return {
        "publication_enabled": bool(artist.publication_enabled),
        "verified": bool(artist.verified and artist.verified_status == "approved"),
        "tariff": has_tariff,
        "media": bool(
            (artist.media_url or "").strip()
            and (artist.media_source_url or "").strip()
            and artist.media_rights_status in PUBLIC_MEDIA_RIGHTS
            and artist.media_rights_attested_at
            and artist.media_rights_attested_by_user_id
        ),
        "representative": has_representative,
        "calendar_30d": bool(
            artist.calendar_confirmed_through
            and aware(artist.calendar_confirmed_through) >= _required_horizon(required_through)
            and artist.calendar_confirmed_at
            and artist.calendar_confirmed_by_user_id
        ),
        "calendar_entries": has_entry,
    }


def _venue_checks(
    venue: Venue,
    *,
    hall_ids: set[str],
    halls_with_entries: set[str],
    has_tariff: bool,
    has_media: bool,
    has_representative: bool,
    required_through: datetime | None,
) -> dict[str, bool]:
    return {
        "publication_enabled": bool(venue.publication_enabled),
        "verified": bool(venue.verified and venue.verified_status == "approved"),
        "moderation": venue.moderation_status == "published",
        "claimed": bool(venue.is_claimed),
        "tariff": has_tariff,
        "media": has_media,
        "representative": has_representative,
        "halls": bool(hall_ids),
        "calendar_30d": bool(
            venue.calendar_confirmed_through
            and aware(venue.calendar_confirmed_through) >= _required_horizon(required_through)
            and venue.calendar_confirmed_at
            and venue.calendar_confirmed_by_user_id
        ),
        "calendar_entries": bool(hall_ids) and hall_ids <= halls_with_entries,
    }


def artist_publication_eligibility(
    db: Session,
    artist: Artist,
    *,
    required_through: datetime | None = None,
) -> PublicationEligibility:
    org = artist.organization_id
    has_entry = (
        db.query(AvailabilitySlot.id)
        .filter(
            AvailabilitySlot.resource_type == "artist",
            AvailabilitySlot.resource_id == artist.id,
            AvailabilitySlot.status.in_(("open", "held", "confirmed")),
            AvailabilitySlot.ends_at >= now(),
        )
        .first()
        is not None
    )
    checks = _artist_checks(
        artist,
        has_tariff=(
            db.query(ArtistTariff.id)
            .filter(ArtistTariff.artist_id == artist.id, ArtistTariff.honorarium_rub > 0)
            .first()
            is not None
        ),
        has_representative=_has_representative(db, org),
        has_entry=has_entry,
        required_through=required_through,
    )
    return PublicationEligibility(eligible=all(checks.values()), checks=checks)


def venue_publication_eligibility(
    db: Session,
    venue: Venue,
    *,
    required_through: datetime | None = None,
) -> PublicationEligibility:
    hall_ids = [
        row[0] for row in db.query(VenueHall.id).filter(VenueHall.venue_id == venue.id).all()
    ]
    halls_with_entries = {
        row[0]
        for row in db.query(AvailabilitySlot.resource_id)
        .filter(
            AvailabilitySlot.resource_type == "hall",
            AvailabilitySlot.resource_id.in_(hall_ids),
            AvailabilitySlot.status.in_(("open", "held", "confirmed")),
            AvailabilitySlot.ends_at >= now(),
        )
        .distinct()
        .all()
    }
    checks = _venue_checks(
        venue,
        hall_ids=set(hall_ids),
        halls_with_entries=halls_with_entries,
        has_tariff=(
            db.query(VenueTariff.id)
            .filter(VenueTariff.venue_id == venue.id, VenueTariff.honorarium_rub > 0)
            .first()
            is not None
        ),
        has_media=(
            db.query(VenuePhoto.id)
            .filter(
                VenuePhoto.venue_id == venue.id,
                VenuePhoto.photo_rights_status.in_(PUBLIC_MEDIA_RIGHTS),
                VenuePhoto.rights_attested_at.is_not(None),
                VenuePhoto.rights_attested_by_user_id.is_not(None),
            )
            .first()
            is not None
        ),
        has_representative=_has_representative(db, venue.organization_id),
        required_through=required_through,
    )
    return PublicationEligibility(eligible=all(checks.values()), checks=checks)


def batch_publication_eligibility(
    db: Session,
    artists: list[Artist],
    venues: list[Venue],
    *,
    required_through: datetime | None = None,
) -> dict[tuple[str, str], PublicationEligibility]:
    """Use the canonical check builders with grouped evidence for a search page.

    The lookup is limited to a caller-provided candidate batch. It does not replace
    the single-profile gate used by other routes.
    """
    if not artists and not venues:
        return {}
    artist_ids = [artist.id for artist in artists]
    venue_ids = [venue.id for venue in venues]
    org_ids = {row.organization_id for row in [*artists, *venues]}
    representatives = {
        row[0]
        for row in db.query(TeamMember.organization_id)
        .filter(
            TeamMember.organization_id.in_(org_ids),
            TeamMember.role.in_(("owner", "admin")),
        )
        .distinct()
        .all()
    }
    positive_artist_tariffs: set[str] = set()
    artist_entries: set[str] = set()
    if artist_ids:
        positive_artist_tariffs = {
            row[0]
            for row in db.query(ArtistTariff.artist_id)
            .filter(ArtistTariff.artist_id.in_(artist_ids), ArtistTariff.honorarium_rub > 0)
            .distinct()
            .all()
        }
        artist_entries = {
            row[0]
            for row in db.query(AvailabilitySlot.resource_id)
            .filter(
                AvailabilitySlot.resource_type == "artist",
                AvailabilitySlot.resource_id.in_(artist_ids),
                AvailabilitySlot.status.in_(("open", "held", "confirmed")),
                AvailabilitySlot.ends_at >= now(),
            )
            .distinct()
            .all()
        }
    halls_by_venue: dict[str, set[str]] = {venue_id: set() for venue_id in venue_ids}
    positive_venue_tariffs: set[str] = set()
    venue_media: set[str] = set()
    hall_entries: set[str] = set()
    if venue_ids:
        for venue_id, hall_id in (
            db.query(VenueHall.venue_id, VenueHall.id)
            .filter(VenueHall.venue_id.in_(venue_ids))
            .all()
        ):
            halls_by_venue[venue_id].add(hall_id)
        hall_ids = {hall_id for ids in halls_by_venue.values() for hall_id in ids}
        if hall_ids:
            hall_entries = {
                row[0]
                for row in db.query(AvailabilitySlot.resource_id)
                .filter(
                    AvailabilitySlot.resource_type == "hall",
                    AvailabilitySlot.resource_id.in_(hall_ids),
                    AvailabilitySlot.status.in_(("open", "held", "confirmed")),
                    AvailabilitySlot.ends_at >= now(),
                )
                .distinct()
                .all()
            }
        positive_venue_tariffs = {
            row[0]
            for row in db.query(VenueTariff.venue_id)
            .filter(VenueTariff.venue_id.in_(venue_ids), VenueTariff.honorarium_rub > 0)
            .distinct()
            .all()
        }
        venue_media = {
            row[0]
            for row in db.query(VenuePhoto.venue_id)
            .filter(
                VenuePhoto.venue_id.in_(venue_ids),
                VenuePhoto.photo_rights_status.in_(PUBLIC_MEDIA_RIGHTS),
                VenuePhoto.rights_attested_at.is_not(None),
                VenuePhoto.rights_attested_by_user_id.is_not(None),
            )
            .distinct()
            .all()
        }
    result: dict[tuple[str, str], PublicationEligibility] = {}
    for artist in artists:
        checks = _artist_checks(
            artist,
            has_tariff=artist.id in positive_artist_tariffs,
            has_representative=artist.organization_id in representatives,
            has_entry=artist.id in artist_entries,
            required_through=required_through,
        )
        result[("artist", artist.id)] = PublicationEligibility(all(checks.values()), checks)
    for venue in venues:
        checks = _venue_checks(
            venue,
            hall_ids=halls_by_venue[venue.id],
            halls_with_entries=hall_entries,
            has_tariff=venue.id in positive_venue_tariffs,
            has_media=venue.id in venue_media,
            has_representative=venue.organization_id in representatives,
            required_through=required_through,
        )
        result[("venue", venue.id)] = PublicationEligibility(all(checks.values()), checks)
    return result


def organization_publication_eligibility(
    db: Session, organization_id: str
) -> PublicationEligibility | None:
    artists = db.query(Artist).filter(Artist.organization_id == organization_id).all()
    for artist in artists:
        result = artist_publication_eligibility(db, artist)
        if result.eligible:
            return result
    venues = db.query(Venue).filter(Venue.organization_id == organization_id).all()
    for venue in venues:
        result = venue_publication_eligibility(db, venue)
        if result.eligible:
            return result
    if artists:
        return artist_publication_eligibility(db, artists[0])
    if venues:
        return venue_publication_eligibility(db, venues[0])
    return None


def target_is_public(db: Session, target_type: str, target_id: str) -> bool:
    if target_type == "artist":
        row = db.get(Artist, target_id)
        return bool(row and artist_publication_eligibility(db, row).eligible)
    if target_type == "venue":
        row = db.get(Venue, target_id)
        return bool(row and venue_publication_eligibility(db, row).eligible)
    return False
