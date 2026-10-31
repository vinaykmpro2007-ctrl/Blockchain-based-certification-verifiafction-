from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (SQLite stores no timezone)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)

    certificate_id = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    student_name = Column(String, nullable=False)
    student_id = Column(String, nullable=False)
    course = Column(String, nullable=False)
    institution = Column(String, nullable=False)
    issue_date = Column(String, nullable=False)

    status = Column(
        String,
        default="PENDING",
        nullable=False
    )

    # Who issued the certificate (admin username).
    issued_by = Column(String, nullable=True)

    # Revocation details, filled in when status becomes REVOKED.
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(String, nullable=True)
    revoke_reason = Column(String, nullable=True)


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    hashed_password = Column(
        String,
        nullable=False
    )

    institution = Column(
        String,
        nullable=False
    )

    is_active = Column(
        Integer,
        default=1,
        nullable=False
    )


class User(Base):
    """A public user who verifies certificates and documents."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Integer, default=1, nullable=False)


class Person(Base):
    """A real person who can hold documents issued by several institutions."""

    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    person_ref = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    date_of_birth = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    documents = relationship(
        "IssuedDocument",
        back_populates="person",
        order_by="IssuedDocument.id",
    )


class IssuedDocument(Base):
    """An identity or academic document (Aadhaar, PAN, SSLC marks card...)
    issued to a person by an institution.

    The full document number is never stored. We keep a masked form for
    display and a keyed hash so a verifier holding the paper document can
    confirm the number matches.
    """

    __tablename__ = "issued_documents"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String, unique=True, index=True, nullable=False)

    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False, index=True)
    person = relationship("Person", back_populates="documents")

    doc_type = Column(String, nullable=False)  # AADHAAR | PAN | SSLC_MARKS
    issuing_institution = Column(String, nullable=False)
    issue_date = Column(String, nullable=False)

    number_masked = Column(String, nullable=False)
    number_hash = Column(String, nullable=False)

    # JSON text: SSLC subject marks and computed result. Null for Aadhaar/PAN.
    details = Column(Text, nullable=True)

    # SHA-256 of the canonical record. This is the value that can be
    # anchored on the blockchain with Certificate.issueCertificate().
    record_hash = Column(String, nullable=False)

    status = Column(String, default="ISSUED", nullable=False)
    issued_by = Column(String, nullable=True)

    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(String, nullable=True)
    revoke_reason = Column(String, nullable=True)


class Revocation(Base):
    """Append-only log of every revocation, used for the admin warnings."""

    __tablename__ = "revocations"

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String, nullable=False)  # CERTIFICATE | DOCUMENT
    target_id = Column(String, nullable=False, index=True)
    admin_username = Column(String, nullable=False, index=True)
    institution = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    revoked_at = Column(DateTime, default=utcnow, nullable=False, index=True)
