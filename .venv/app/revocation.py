"""Revocation policy and the warning shown to administrators.

Every revocation is written to the `revocations` table. The warning level for
an administrator depends on how many revocations *they* performed inside a
rolling time window:

    OK        fewer than REVOKE_WARN_THRESHOLD
    WARNING   at least REVOKE_WARN_THRESHOLD
    CRITICAL  at least REVOKE_CRITICAL_THRESHOLD

Settings (all optional, read from the environment / .env):

    REVOKE_WARN_THRESHOLD      default 3
    REVOKE_CRITICAL_THRESHOLD  default 5
    REVOKE_WINDOW_DAYS         default 30
"""

import os
from dataclasses import dataclass
from datetime import timedelta

from dotenv import load_dotenv
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models

load_dotenv()


@dataclass(frozen=True)
class RevocationPolicy:
    warn_threshold: int
    critical_threshold: int
    window_days: int


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a whole number, got {raw!r}.")

    if value < 1:
        raise RuntimeError(f"{name} must be at least 1.")

    return value


def get_policy() -> RevocationPolicy:
    """Read the policy from the environment on every call."""
    warn = _env_int("REVOKE_WARN_THRESHOLD", 3)
    critical = _env_int("REVOKE_CRITICAL_THRESHOLD", 5)
    window = _env_int("REVOKE_WINDOW_DAYS", 30)

    if critical < warn:
        raise RuntimeError(
            "REVOKE_CRITICAL_THRESHOLD must not be lower than "
            "REVOKE_WARN_THRESHOLD."
        )

    return RevocationPolicy(warn, critical, window)


def normalize_institution(name: str) -> str:
    return " ".join((name or "").split()).lower()


def record_revocation(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    admin: models.Admin,
    institution: str,
    reason: str,
) -> models.Revocation:
    """Add a log row. The caller commits it together with the status change."""
    entry = models.Revocation(
        target_type=target_type,
        target_id=target_id,
        admin_username=admin.username,
        institution=institution,
        reason=reason,
        revoked_at=models.utcnow(),
    )
    db.add(entry)
    return entry


def build_summary(db: Session, admin: models.Admin) -> dict:
    """Revocation counts and the warning level for one administrator."""
    policy = get_policy()
    since = models.utcnow() - timedelta(days=policy.window_days)

    own_count = (
        db.query(func.count(models.Revocation.id))
        .filter(
            models.Revocation.admin_username == admin.username,
            models.Revocation.revoked_at >= since,
        )
        .scalar()
    )

    institution_key = normalize_institution(admin.institution)
    institution_count = sum(
        1
        for (name,) in db.query(models.Revocation.institution)
        .filter(models.Revocation.revoked_at >= since)
        .all()
        if normalize_institution(name) == institution_key
    )

    if own_count >= policy.critical_threshold:
        level = "CRITICAL"
        message = (
            f"Critical: you have revoked {own_count} item(s) in the last "
            f"{policy.window_days} days (critical limit "
            f"{policy.critical_threshold}). Review these revocations "
            f"before revoking anything else."
        )
    elif own_count >= policy.warn_threshold:
        level = "WARNING"
        message = (
            f"Warning: you have revoked {own_count} item(s) in the last "
            f"{policy.window_days} days (warning limit "
            f"{policy.warn_threshold}). A high number of revocations may "
            f"indicate mistakes or misuse."
        )
    else:
        level = "OK"
        message = (
            f"You have revoked {own_count} item(s) in the last "
            f"{policy.window_days} days."
        )

    remaining = max(policy.warn_threshold - own_count, 0)

    return {
        "level": level,
        "message": message,
        "own_revocations": own_count,
        "institution_revocations": institution_count,
        "window_days": policy.window_days,
        "warn_threshold": policy.warn_threshold,
        "critical_threshold": policy.critical_threshold,
        "remaining_before_warning": remaining,
    }
