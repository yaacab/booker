"""Founding catalog artists without TeamMember stay hidden until steward link."""

from booker_api.models import Artist, Organization, TeamMember, User
from booker_api.routers.catalog import _has_account
from booker_api.seed import CATALOG_STEWARD_EMAIL, link_orphan_verified_artists


def test_link_orphan_verified_artists_attaches_steward(SessionLocal):
    db = SessionLocal()
    try:
        org = Organization(name="Orphan Founding", kind="artist")
        db.add(org)
        db.flush()
        db.add(
            Artist(
                organization_id=org.id,
                name="Founding DJ",
                city="Москва",
                category="dj",
                verified=True,
                verified_status="approved",
            )
        )
        db.commit()
        org_id = org.id
        assert _has_account(db, org_id) is False

        linked = link_orphan_verified_artists(db)
        db.commit()
        assert linked >= 1
        assert _has_account(db, org_id) is True
        steward = db.query(User).filter(User.email == CATALOG_STEWARD_EMAIL).one()
        assert (
            db.query(TeamMember)
            .filter(
                TeamMember.organization_id == org_id,
                TeamMember.user_id == steward.id,
                TeamMember.role == "owner",
            )
            .count()
            == 1
        )
        # Idempotent on a second pass
        assert link_orphan_verified_artists(db) == 0
        db.commit()
    finally:
        db.close()
