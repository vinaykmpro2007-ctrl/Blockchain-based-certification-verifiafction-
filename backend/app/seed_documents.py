"""Seed ONE sample person with documents from three different institutions.

    python -m app.seed_documents                 # add the sample data
    python -m app.seed_documents --demo-admins   # also create a demo admin
                                                 # account for each institution

Run it from the folder that contains certichain.db (the same folder you start
uvicorn from). It is safe to run more than once: nothing is duplicated.

ALL VALUES BELOW ARE FICTIONAL SAMPLE DATA. The Aadhaar number 0000 0000 1234
is not a valid Aadhaar number, and ABCDE1234F is not a valid PAN. Do not put
real personal document numbers into a demo database.
"""

import argparse
import secrets

from app import models
from app.auth import get_password_hash
from app.database import SessionLocal, engine
from app.documents import create_document
from app.migrate import ensure_schema

PERSON = {
    "full_name": "Rahul Sharma",
    "date_of_birth": "2004-05-17",
}

UIDAI = "UIDAI"
TAX = "Income Tax Department"
BOARD = "Karnataka Secondary Education Examination Board"

SAMPLE_DOCUMENTS = [
    {
        "doc_type": "AADHAAR",
        "institution": UIDAI,
        "raw_number": "0000 0000 1234",
        "issue_date": "2016-08-22",
    },
    {
        "doc_type": "PAN",
        "institution": TAX,
        "raw_number": "ABCDE1234F",
        "issue_date": "2022-06-15",
    },
    {
        "doc_type": "SSLC_MARKS",
        "institution": BOARD,
        "raw_number": "KA2020R004217",
        "issue_date": "2020-07-30",
        "exam_year": 2020,
        "subjects": [
            {"name": "First Language (Kannada)", "max_marks": 125, "marks_obtained": 112},
            {"name": "Second Language (English)", "max_marks": 100, "marks_obtained": 91},
            {"name": "Third Language (Hindi)", "max_marks": 100, "marks_obtained": 88},
            {"name": "Mathematics", "max_marks": 100, "marks_obtained": 95},
            {"name": "Science", "max_marks": 100, "marks_obtained": 90},
            {"name": "Social Science", "max_marks": 100, "marks_obtained": 93},
        ],
    },
]


def get_or_create_person(db) -> tuple[models.Person, bool]:
    person = (
        db.query(models.Person)
        .filter(
            models.Person.full_name == PERSON["full_name"],
            models.Person.date_of_birth == PERSON["date_of_birth"],
        )
        .first()
    )

    if person is not None:
        return person, False

    person = models.Person(
        person_ref=f"PER-{secrets.token_hex(5).upper()}",
        full_name=PERSON["full_name"],
        date_of_birth=PERSON["date_of_birth"],
    )
    db.add(person)
    db.flush()
    return person, True


def create_demo_admins(db) -> list[tuple[str, str, str]]:
    """One admin per institution. Returns (username, password, institution)
    for the accounts created now; existing accounts are left alone."""
    created = []

    for institution, username in (
        (UIDAI, "uidai-admin"),
        (TAX, "incometax-admin"),
        (BOARD, "kseeb-admin"),
    ):
        exists = (
            db.query(models.Admin)
            .filter(models.Admin.username == username)
            .first()
        )

        if exists:
            continue

        password = secrets.token_urlsafe(15)  # 20 characters, above the 12 minimum
        db.add(
            models.Admin(
                username=username,
                hashed_password=get_password_hash(password),
                institution=institution,
                is_active=1,
            )
        )
        created.append((username, password, institution))

    return created


def main():
    parser = argparse.ArgumentParser(description="Seed sample issued documents.")
    parser.add_argument(
        "--demo-admins",
        action="store_true",
        help="also create one demo admin account per issuing institution",
    )
    args = parser.parse_args()

    ensure_schema(engine)
    db = SessionLocal()

    try:
        person, person_is_new = get_or_create_person(db)
        added = []

        for spec in SAMPLE_DOCUMENTS:
            already = (
                db.query(models.IssuedDocument)
                .filter(
                    models.IssuedDocument.person_id == person.id,
                    models.IssuedDocument.doc_type == spec["doc_type"],
                    models.IssuedDocument.issuing_institution == spec["institution"],
                )
                .first()
            )

            if already:
                continue

            document = create_document(
                person=person,
                doc_type=spec["doc_type"],
                raw_number=spec["raw_number"],
                issue_date=spec["issue_date"],
                institution=spec["institution"],
                issued_by="seed-script",
                subjects=spec.get("subjects"),
                exam_year=spec.get("exam_year"),
            )
            db.add(document)
            added.append(document)

        demo_admins = create_demo_admins(db) if args.demo_admins else []

        db.commit()

        print(f"Person: {person.full_name} ({person.person_ref})"
              f"{' - created' if person_is_new else ' - already existed'}")

        if added:
            for doc in added:
                print(f"  + {doc.document_id}  {doc.doc_type:<10} {doc.number_masked:<16}"
                      f" issued by {doc.issuing_institution}")
        else:
            print("  Documents already present - nothing added.")

        if demo_admins:
            print("\nDemo admin accounts (shown once, development use only):")
            for username, password, institution in demo_admins:
                print(f"  {username:<16} {password}   [{institution}]")

    finally:
        db.close()


if __name__ == "__main__":
    main()
