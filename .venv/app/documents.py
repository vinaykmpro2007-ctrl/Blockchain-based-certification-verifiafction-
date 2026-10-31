"""Helpers for issued documents: Aadhaar, PAN and SSLC marks cards.

Privacy rules used here:
  * The full document number is NEVER stored. We store a masked form
    (last four characters visible) and a keyed HMAC-SHA256 of the number.
  * A plain SHA-256 of a 12-digit Aadhaar or a PAN could be brute-forced, so
    the hash is keyed with a secret derived from SECRET_KEY. Changing
    SECRET_KEY therefore invalidates number checks for existing documents.
  * Only masked numbers appear in API responses.
"""

import hashlib
import hmac
import json
import os
import re
import uuid

from dotenv import load_dotenv

from app import models

load_dotenv()

DOCUMENT_TYPES = {
    "AADHAAR": "Aadhaar Card",
    "PAN": "PAN Card",
    "SSLC_MARKS": "SSLC Marks Card",
}

# A subject is passed when it scores at least this share of its maximum.
SSLC_PASS_PERCENT = 35

_PATTERNS = {
    "AADHAAR": re.compile(r"^\d{12}$"),
    "PAN": re.compile(r"^[A-Z]{5}\d{4}[A-Z]$"),
    "SSLC_MARKS": re.compile(r"^[A-Z0-9]{6,20}$"),
}

_FORMAT_HELP = {
    "AADHAAR": "an Aadhaar number must be exactly 12 digits",
    "PAN": "a PAN must look like ABCDE1234F",
    "SSLC_MARKS": "a register number must be 6-20 letters or digits",
}


def normalize_number(doc_type: str, raw: str) -> str:
    """Strip spaces and dashes, upper-case, and validate the format."""
    if doc_type not in _PATTERNS:
        raise ValueError(f"Unsupported document type: {doc_type}")

    value = re.sub(r"[\s-]", "", raw or "").upper()

    if not _PATTERNS[doc_type].match(value):
        raise ValueError(f"Invalid document number: {_FORMAT_HELP[doc_type]}.")

    return value


def mask_number(doc_type: str, normalized: str) -> str:
    """Hide everything except the last four characters."""
    hidden = "X" * (len(normalized) - 4)
    masked = hidden + normalized[-4:]

    if doc_type == "AADHAAR":
        return f"{masked[0:4]} {masked[4:8]} {masked[8:12]}"

    return masked


def _hash_key() -> bytes:
    secret = os.getenv("SECRET_KEY")

    if not secret:
        raise RuntimeError("SECRET_KEY is missing. Configure it in the environment.")

    return hmac.new(
        secret.encode(), b"certichain:document-number:v1", hashlib.sha256
    ).digest()


def number_hash(doc_type: str, normalized: str) -> str:
    """Keyed hash of the document number (hex)."""
    return hmac.new(
        _hash_key(), f"{doc_type}:{normalized}".encode(), hashlib.sha256
    ).hexdigest()


def numbers_match(doc_type: str, normalized: str, stored_hash: str) -> bool:
    return hmac.compare_digest(number_hash(doc_type, normalized), stored_hash)


def sslc_summary(subjects: list[dict]) -> dict:
    """Total, percentage and pass/fail for an SSLC marks card."""
    total = sum(item["marks_obtained"] for item in subjects)
    maximum = sum(item["max_marks"] for item in subjects)

    passed = all(
        item["marks_obtained"] * 100 >= SSLC_PASS_PERCENT * item["max_marks"]
        for item in subjects
    )

    return {
        "total_marks": total,
        "max_total_marks": maximum,
        "percentage": round(total * 100 / maximum, 2),
        "result": "PASS" if passed else "FAIL",
    }


def canonical_json(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_record_hash(
    *,
    document_id: str,
    doc_type: str,
    person_ref: str,
    holder_name: str,
    issuing_institution: str,
    issue_date: str,
    number_hash_value: str,
    details: dict | None,
) -> str:
    """SHA-256 over the canonical record: what gets anchored on-chain."""
    record = {
        "document_id": document_id,
        "doc_type": doc_type,
        "person_ref": person_ref,
        "holder_name": holder_name,
        "issuing_institution": issuing_institution,
        "issue_date": issue_date,
        "number_hash": number_hash_value,
        "details": details,
    }

    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def create_document(
    *,
    person: "models.Person",
    doc_type: str,
    raw_number: str,
    issue_date: str,
    institution: str,
    issued_by: str,
    subjects: list[dict] | None = None,
    exam_year: int | None = None,
) -> "models.IssuedDocument":
    """Build an IssuedDocument (not yet added to a session).

    Shared by the API and the seed script so both hash, mask and fingerprint
    documents identically. Raises ValueError for a badly formatted number.
    """
    number = normalize_number(doc_type, raw_number)

    stored_details = None

    if subjects is not None:
        stored_details = {
            "exam_year": exam_year,
            "subjects": subjects,
            **sslc_summary(subjects),
        }

    document_id = f"DOC-{uuid.uuid4().hex[:12].upper()}"
    hashed_number = number_hash(doc_type, number)

    record_hash = compute_record_hash(
        document_id=document_id,
        doc_type=doc_type,
        person_ref=person.person_ref,
        holder_name=person.full_name,
        issuing_institution=institution,
        issue_date=issue_date,
        number_hash_value=hashed_number,
        details=stored_details,
    )

    return models.IssuedDocument(
        document_id=document_id,
        person_id=person.id,
        doc_type=doc_type,
        issuing_institution=institution,
        issue_date=issue_date,
        number_masked=mask_number(doc_type, number),
        number_hash=hashed_number,
        details=canonical_json(stored_details) if stored_details else None,
        record_hash=record_hash,
        status="ISSUED",
        issued_by=issued_by,
    )
