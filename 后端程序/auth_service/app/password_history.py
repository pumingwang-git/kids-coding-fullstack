"""Password-history enforcement.

A new password may not equal the current one or any of the user's most recent
passwords.  Replaced passwords are archived as Argon2id hashes (the same
algorithm as the live hash) and the table is pruned to the newest ``keep`` rows
per user.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import PasswordHistory
from .security import password_hash


def password_was_used_before(
    db: Session,
    user_id: int,
    candidate: str,
    current_hash: str | None = None,
) -> bool:
    """True when `candidate` equals the current hash or any archived hash."""
    if current_hash and password_hash.verify(candidate, current_hash):
        return True
    stored = db.scalars(
        select(PasswordHistory.password_hash).where(PasswordHistory.user_id == user_id)
    ).all()
    return any(password_hash.verify(candidate, item) for item in stored)


def archive_password(db: Session, user_id: int, previous_hash: str, keep: int = 5) -> None:
    """Archive a replaced password hash and prune to the newest `keep` rows."""
    if not previous_hash:
        return
    db.add(PasswordHistory(user_id=user_id, password_hash=previous_hash))
    db.flush()
    overflow = list(
        db.scalars(
            select(PasswordHistory.id)
            .where(PasswordHistory.user_id == user_id)
            .order_by(PasswordHistory.id.desc())
            .offset(keep)
            .limit(1000)
        )
    )
    if overflow:
        db.execute(delete(PasswordHistory).where(PasswordHistory.id.in_(overflow)))
