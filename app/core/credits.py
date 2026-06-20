"""
Atomic credit reservation — prevents overspend / lost updates when
multiple Celery workers and the in-process send-now task all decrement
the same user's balance concurrently.

Uses optimistic locking (compare-and-swap on the credits value), which
works on both SQLite (local dev) and PostgreSQL (production) without
requiring SELECT ... FOR UPDATE.
"""

from app import models


def reserve_credits(db, user_id: int, want: int, max_retries: int = 5) -> int:
    """
    Atomically reserve up to `want` credits from the user's balance.
    Returns the amount actually reserved (0 if the user is broke).

    The caller MUST refund any reserved-but-unused credits via
    refund_credits() — typically for hits that failed to send.
    """
    if want <= 0:
        return 0
    for _ in range(max_retries):
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or user.credits <= 0:
            return 0
        take = min(want, user.credits)
        # Compare-and-swap: only succeeds if credits is still what we read.
        updated = (
            db.query(models.User)
            .filter(models.User.id == user_id, models.User.credits == user.credits)
            .update(
                {models.User.credits: models.User.credits - take},
                synchronize_session=False,
            )
        )
        db.commit()
        if updated:
            return take
        # Another worker changed the balance — refresh and retry.
        db.expire_all()
    return 0


def refund_credits(db, user_id: int, amount: int) -> None:
    """Atomically return unused credits to the user's balance."""
    if amount <= 0:
        return
    db.query(models.User).filter(models.User.id == user_id).update(
        {models.User.credits: models.User.credits + amount},
        synchronize_session=False,
    )
    db.commit()
