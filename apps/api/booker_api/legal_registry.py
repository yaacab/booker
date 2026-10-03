"""Frozen identifiers for the unapproved 2026-10-01 legal draft.

These hashes describe repository bytes, not a published legal package. Changing
the text requires a new version; an existing registry row is never rewritten.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from booker_api.models import LegalDocumentVersion

DRAFT_VERSION = "2026-10-01-draft"
DOCUMENTS = {
    "offer": ("OFFER_DRAFT.md", "17201d86023d35ac9bff4bc5e3e20718ba9fdc36eabf893a88749acdd3179654", True, "/legal/offer"),
    "privacy": ("PRIVACY_DRAFT.md", "4f9316eabced514702d41bd19c21b0deef6c74833f6f39a7e178045cfc7a6077", True, "/legal/privacy"),
    "consent_texts": ("CONSENT_TEXTS.md", "015800faa3e0bca87807fd7bd9d7e31702e7cdf08594292a33eeab2f0f4d8c82", True, "/legal/consent-texts"),
    "cookies": ("COOKIES_DRAFT.md", "dd4301b905dcd65674b8f8b3cd850f136e1c40410cf19a28dca221ab42608b9f", False, "/legal/cookies"),
    "disputes": ("DISPUTES_REFUNDS_DRAFT.md", "c9fbddfd146ba42a3dc15f3fa1b7092a050d08c2fa8794c9e0f86e5e9a121626", False, "/legal/disputes"),
    "suppliers": ("SUPPLIER_TERMS_DRAFT.md", "c3f0c25e5b08dbb243d8de4e26d4167e98aa74ed546262f67bb204a0195e4628", False, "/legal/suppliers"),
    "cancellation": ("CANCELLATION_TARIFF.md", "be52eacb22ac58c961eddfe915fe1c25dc8c34e4fa6ecd78beb09e937c2ae6dd", False, "/legal/cancellation"),
}
REQUIRED_KEYS = ("offer", "privacy", "consent_texts")


def seed_draft_versions(db: Session) -> None:
    for key, (filename, digest, _required, _href) in DOCUMENTS.items():
        row = db.query(LegalDocumentVersion).filter_by(key=key, version=DRAFT_VERSION).one_or_none()
        if row is None:
            db.add(LegalDocumentVersion(
                key=key, version=DRAFT_VERSION, content_hash=digest,
                status="draft", source_path=f"docs/legal/{filename}",
            ))
        elif row.content_hash != digest or row.source_path != f"docs/legal/{filename}":
            raise RuntimeError(f"legal draft registry drift: {key}")
    db.flush()


def draft_sources_match() -> bool:
    import hashlib

    root = Path(__file__).resolve().parents[3] / "docs" / "legal"
    for filename, digest, _required, _href in DOCUMENTS.values():
        path = root / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return False
    return True


def published_sources_match(rows: dict[str, LegalDocumentVersion]) -> bool:
    import hashlib

    root = Path(__file__).resolve().parents[3]
    for key, (filename, _digest, _required, _href) in DOCUMENTS.items():
        row = rows.get(key)
        expected_path = f"docs/legal/{filename}"
        if row is None or row.source_path != expected_path:
            return False
        path = root / expected_path
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.content_hash:
            return False
    return True
