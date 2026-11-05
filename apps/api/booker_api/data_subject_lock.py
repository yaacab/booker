"""Serialize privacy state mutations through the subject's user row."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.models import User


def lock_subject(db: Session, user_id: str) -> User | None:
    if db.get_bind().dialect.name == "sqlite":
        # SQLite has no row-level FOR UPDATE. An unchanged UPDATE takes the
        # database write lock until this transaction commits or rolls back.
        changed = db.execute(update(User).where(User.id == user_id).values(
            optional_processing_restricted=User.optional_processing_restricted
        ).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            return None
        user = db.get(User, user_id)
    else:
        user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if user is not None:
        db.refresh(user)
    return user
