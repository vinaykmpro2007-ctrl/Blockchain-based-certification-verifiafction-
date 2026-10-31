import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import engine
from app import models, schemas, admin_schemas, documents, revocation, certificate_pdf
from app.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
)
from app.dependencies import get_current_admin, get_db
from app.migrate import ensure_schema


app = FastAPI(
    title="CertiChain API",
    description="Backend for certificate verification",
    version="0.2.0",
)


# Create tables and add any new columns to an existing database.
ensure_schema(engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def iso(value) -> str | None:
    """UTC datetime -> ISO 8601 string ending in Z."""
    return value.isoformat(timespec="seconds") + "Z" if value else None


def certificate_public(cert: models.Certificate) -> dict:
    """What anyone verifying a certificate may see."""
    return {
        "kind": "CERTIFICATE",
        "certificate_id": cert.certificate_id,
        "student_name": cert.student_name,
        "student_id": cert.student_id,
        "course": cert.course,
        "institution": cert.institution,
        "issue_date": cert.issue_date,
        "status": cert.status,
        "revoked_at": iso(cert.revoked_at),
    }


def certificate_admin(cert: models.Certificate) -> dict:
    """Certificate details for administrators (adds who/why)."""
    return {
        **certificate_public(cert),
        "issued_by": cert.issued_by,
        "revoked_by": cert.revoked_by,
        "revoke_reason": cert.revoke_reason,
    }


def document_details(doc: models.IssuedDocument) -> dict | None:
    return json.loads(doc.details) if doc.details else None


def document_public(doc: models.IssuedDocument) -> dict:
    """What anyone verifying a document may see. Numbers are masked."""
    return {
        "kind": "DOCUMENT",
        "document_id": doc.document_id,
        "doc_type": doc.doc_type,
        "doc_type_label": documents.DOCUMENT_TYPES[doc.doc_type],
        "holder_name": doc.person.full_name,
        "issuing_institution": doc.issuing_institution,
        "issue_date": doc.issue_date,
        "number_masked": doc.number_masked,
        "status": doc.status,
        "revoked_at": iso(doc.revoked_at),
        "details": document_details(doc),
    }


def document_admin(doc: models.IssuedDocument) -> dict:
    return {
        **document_public(doc),
        "person_ref": doc.person.person_ref,
        "record_hash": doc.record_hash,
        "issued_by": doc.issued_by,
        "revoked_by": doc.revoked_by,
        "revoke_reason": doc.revoke_reason,
    }


def person_dict(person: models.Person) -> dict:
    return {
        "person_ref": person.person_ref,
        "full_name": person.full_name,
        "date_of_birth": person.date_of_birth,
        "document_count": len(person.documents),
        "documents": [
            {
                "document_id": doc.document_id,
                "doc_type": doc.doc_type,
                "doc_type_label": documents.DOCUMENT_TYPES[doc.doc_type],
                "issuing_institution": doc.issuing_institution,
                "number_masked": doc.number_masked,
                "status": doc.status,
            }
            for doc in person.documents
        ],
    }


def may_revoke(
    admin: models.Admin,
    institution: str,
    issued_by: str | None,
) -> bool:
    """An admin may revoke what they issued, or anything issued by their
    own institution. Nothing else."""
    if issued_by and issued_by == admin.username:
        return True

    return revocation.normalize_institution(
        admin.institution
    ) == revocation.normalize_institution(institution)


def revoke_item(
    db: Session,
    *,
    model,
    key_column,
    key_value: str,
    target_type: str,
    admin: models.Admin,
    reason: str,
):
    """Revoke one certificate or document and log it.

    The status change is a conditional UPDATE, so two simultaneous requests
    can never both succeed (and never both be counted).
    """
    item = db.query(model).filter(key_column == key_value).first()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    institution = (
        item.institution
        if target_type == "CERTIFICATE"
        else item.issuing_institution
    )

    if not may_revoke(admin, institution, item.issued_by):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only revoke items issued by your institution.",
        )

    if item.status == "REVOKED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already revoked.",
        )

    now = models.utcnow()

    changed = (
        db.query(model)
        .filter(key_column == key_value, model.status != "REVOKED")
        .update(
            {
                "status": "REVOKED",
                "revoked_at": now,
                "revoked_by": admin.username,
                "revoke_reason": reason,
            },
            synchronize_session=False,
        )
    )

    if changed != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already revoked.",
        )

    revocation.record_revocation(
        db,
        target_type=target_type,
        target_id=key_value,
        admin=admin,
        institution=institution,
        reason=reason,
    )
    db.commit()

    summary = revocation.build_summary(db, admin)

    return {
        "id": key_value,
        "status": "REVOKED",
        "revoked_at": iso(now),
        "warning": summary["message"] if summary["level"] != "OK" else None,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------

# Home endpoint.
@app.get("/")
def home():
    return {
        "message": "Welcome to CertiChain API",
        "status": "running",
    }


# Health check endpoint.
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "certichain-backend",
    }


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

# Create a certificate record (administrators only).
@app.post(
    "/api/certificates",
    response_model=schemas.CertificateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_certificate(
    certificate: schemas.CertificateCreate,
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    certificate_id = f"CERT-{uuid4().hex[:12].upper()}"

    new_certificate = models.Certificate(
        certificate_id=certificate_id,
        student_name=certificate.student_name,
        student_id=certificate.student_id,
        course=certificate.course,
        # Always the signed-in admin's institution; anything typed is ignored.
        institution=admin.institution,
        issue_date=certificate.issue_date.isoformat(),
        status="PENDING",
        issued_by=admin.username,
    )

    db.add(new_certificate)
    db.commit()
    db.refresh(new_certificate)

    return certificate_public(new_certificate)


# List certificate records (administrators only).
@app.get("/api/certificates")
def list_certificates(
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    certificates = (
        db.query(models.Certificate)
        .order_by(models.Certificate.id.desc())
        .all()
    )

    return [certificate_admin(cert) for cert in certificates]


# Retrieve one certificate using its certificate ID (public).
@app.get("/api/certificates/{certificate_id}")
def get_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
):
    certificate = (
        db.query(models.Certificate)
        .filter(
            models.Certificate.certificate_id == certificate_id
        )
        .first()
    )

    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found",
        )

    return certificate_public(certificate)


# Download a certificate as a PDF (administrators only).
@app.get("/api/certificates/{certificate_id}/pdf")
def download_certificate_pdf(
    certificate_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    certificate = (
        db.query(models.Certificate)
        .filter(models.Certificate.certificate_id == certificate_id)
        .first()
    )

    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found",
        )

    # Use PUBLIC_BASE_URL when set (needed behind a proxy); otherwise the
    # address this request came in on.
    base_url = os.getenv("PUBLIC_BASE_URL") or str(request.base_url)
    content = certificate_pdf.build_certificate_pdf(
        certificate_public(certificate), base_url
    )

    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{certificate.certificate_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )


# Revoke a certificate (administrators only).
@app.post("/api/certificates/{certificate_id}/revoke")
def revoke_certificate(
    certificate_id: str,
    body: schemas.RevokeRequest,
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    return revoke_item(
        db,
        model=models.Certificate,
        key_column=models.Certificate.certificate_id,
        key_value=certificate_id,
        target_type="CERTIFICATE",
        admin=admin,
        reason=body.reason,
    )


# ---------------------------------------------------------------------------
# Persons and issued documents (Aadhaar, PAN, SSLC marks)
# ---------------------------------------------------------------------------

# Register a person who can hold documents.
@app.post("/api/persons", status_code=status.HTTP_201_CREATED)
def create_person(
    person: schemas.PersonCreate,
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    new_person = models.Person(
        person_ref=f"PER-{uuid4().hex[:10].upper()}",
        full_name=person.full_name,
        date_of_birth=person.date_of_birth.isoformat(),
    )

    db.add(new_person)
    db.commit()
    db.refresh(new_person)

    return person_dict(new_person)


# List persons together with all their documents from every institution.
@app.get("/api/persons")
def list_persons(
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    persons = db.query(models.Person).order_by(models.Person.id).all()

    return [person_dict(person) for person in persons]


# Issue a document to a person. The issuer is always the admin's institution.
@app.post("/api/documents", status_code=status.HTTP_201_CREATED)
def issue_document(
    payload: schemas.DocumentCreate,
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    person = (
        db.query(models.Person)
        .filter(models.Person.person_ref == payload.person_ref)
        .first()
    )

    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )

    try:
        document = documents.create_document(
            person=person,
            doc_type=payload.doc_type,
            raw_number=payload.document_number,
            issue_date=payload.issue_date.isoformat(),
            institution=admin.institution,
            issued_by=admin.username,
            subjects=(
                [item.model_dump() for item in payload.details.subjects]
                if payload.details is not None
                else None
            ),
            exam_year=(
                payload.details.exam_year if payload.details is not None else None
            ),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    db.add(document)
    db.commit()
    db.refresh(document)

    return document_admin(document)


# List documents (administrators only).
@app.get("/api/documents")
def list_documents(
    person_ref: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    query = db.query(models.IssuedDocument).join(models.Person)

    if person_ref:
        query = query.filter(models.Person.person_ref == person_ref)

    items = query.order_by(models.IssuedDocument.id.desc()).all()

    return [document_admin(doc) for doc in items]


def find_document(db: Session, document_id: str) -> models.IssuedDocument:
    document = (
        db.query(models.IssuedDocument)
        .filter(models.IssuedDocument.document_id == document_id)
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return document


# Retrieve one document (public, masked).
@app.get("/api/documents/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    return document_public(find_document(db, document_id))


# Check that the number printed on a physical document matches the record.
@app.post("/api/documents/{document_id}/verify-number")
def verify_document_number(
    document_id: str,
    body: schemas.NumberCheck,
    db: Session = Depends(get_db),
):
    document = find_document(db, document_id)

    try:
        number = documents.normalize_number(
            document.doc_type, body.document_number
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )

    return {
        "document_id": document.document_id,
        "number_matches": documents.numbers_match(
            document.doc_type, number, document.number_hash
        ),
        "status": document.status,
    }


# Revoke a document (administrators only).
@app.post("/api/documents/{document_id}/revoke")
def revoke_document(
    document_id: str,
    body: schemas.RevokeRequest,
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    return revoke_item(
        db,
        model=models.IssuedDocument,
        key_column=models.IssuedDocument.document_id,
        key_value=document_id,
        target_type="DOCUMENT",
        admin=admin,
        reason=body.reason,
    )


# One verification endpoint for QR codes: CERT-... or DOC-...
@app.get("/api/verify/{identifier}")
def verify_identifier(identifier: str, db: Session = Depends(get_db)):
    identifier = identifier.strip().upper()

    if identifier.startswith("DOC-"):
        return document_public(find_document(db, identifier))

    if identifier.startswith("CERT-"):
        return get_certificate(identifier, db)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Unknown identifier. Expected an ID starting with CERT- or DOC-.",
    )


# ---------------------------------------------------------------------------
# Revocation warnings and log
# ---------------------------------------------------------------------------

# Current warning level and counts for the signed-in administrator.
@app.get("/api/admin/revocations/summary")
def revocation_summary(
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    return revocation.build_summary(db, admin)


# Recent revocations made by the administrator's institution.
@app.get("/api/admin/revocations")
def revocation_log(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    key = revocation.normalize_institution(admin.institution)

    entries = (
        db.query(models.Revocation)
        .order_by(models.Revocation.id.desc())
        .all()
    )

    visible = [
        entry
        for entry in entries
        if revocation.normalize_institution(entry.institution) == key
        or entry.admin_username == admin.username
    ][:limit]

    return [
        {
            "target_type": entry.target_type,
            "target_id": entry.target_id,
            "revoked_by": entry.admin_username,
            "institution": entry.institution,
            "reason": entry.reason,
            "revoked_at": iso(entry.revoked_at),
        }
        for entry in visible
    ]


# ---------------------------------------------------------------------------
# Team accounts: an administrator can add colleagues at their own institution
# ---------------------------------------------------------------------------

def admin_member(member: models.Admin) -> dict:
    return {
        "username": member.username,
        "institution": member.institution,
        "is_active": bool(member.is_active),
    }


# Add another administrator. The institution is always the creator's own;
# there is deliberately no way to choose a different one.
@app.post("/api/admins", status_code=status.HTTP_201_CREATED)
def create_team_admin(
    payload: admin_schemas.TeamAdminCreate,
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    existing = (
        db.query(models.Admin)
        .filter(models.Admin.username == payload.username)
        .first()
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username is already taken.",
        )

    member = models.Admin(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        institution=admin.institution,
        is_active=1,
    )

    db.add(member)
    db.commit()

    return admin_member(member)


# List the administrators of the signed-in admin's institution.
@app.get("/api/admins")
def list_team_admins(
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    key = revocation.normalize_institution(admin.institution)

    members = db.query(models.Admin).order_by(models.Admin.id).all()

    return [
        admin_member(member)
        for member in members
        if revocation.normalize_institution(member.institution) == key
    ]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

# Administrator login endpoint.
@app.post("/api/auth/login")
def admin_login(
    credentials: admin_schemas.AdminLogin,
    db: Session = Depends(get_db),
):
    # Find the administrator by username.
    admin = (
        db.query(models.Admin)
        .filter(models.Admin.username == credentials.username)
        .first()
    )

    # Reject missing accounts and incorrect passwords.
    if admin is None or not verify_password(
        credentials.password,
        admin.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject disabled administrator accounts.
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator account is inactive",
        )

    # Generate a signed access token.
    access_token = create_access_token(subject=admin.username, role="admin")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 1800,
    }


# Who is signed in (used to pre-fill the institution on the admin page).
@app.get("/api/auth/me")
def current_admin_profile(admin: models.Admin = Depends(get_current_admin)):
    return {"username": admin.username, "institution": admin.institution}


# Administrator accounts are NOT self-service: anyone could otherwise become
# an administrator and revoke or issue documents for any institution.
@app.post("/api/auth/register/admin")
def register_admin():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Administrator accounts are created by the system owner "
            "with create_admin.py."
        ),
    )


# Public user registration.
@app.post("/api/auth/register/user", status_code=status.HTTP_201_CREATED)
def register_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    existing = (
        db.query(models.User)
        .filter(models.User.username == payload.username)
        .first()
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username is already taken.",
        )

    user = models.User(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        is_active=1,
    )

    db.add(user)
    db.commit()

    return {
        "access_token": create_access_token(subject=user.username, role="user"),
        "token_type": "bearer",
        "expires_in": 1800,
    }


# Public user login.
@app.post("/api/auth/user/login")
def user_login(
    credentials: admin_schemas.AdminLogin,
    db: Session = Depends(get_db),
):
    user = (
        db.query(models.User)
        .filter(models.User.username == credentials.username)
        .first()
    )

    if user is None or not verify_password(
        credentials.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return {
        "access_token": create_access_token(subject=user.username, role="user"),
        "token_type": "bearer",
        "expires_in": 1800,
    }


# ---------------------------------------------------------------------------
# Frontend (the pages in ../real.static)
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(
    os.getenv("FRONTEND_DIR", Path(__file__).resolve().parents[2] / "real.static")
)

if (FRONTEND_DIR / "static").is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=FRONTEND_DIR / "static"),
        name="static",
    )

    def _page(filename: str):
        def serve():
            return FileResponse(FRONTEND_DIR / "static" / filename)

        return serve

    # The pages link to each other as /login.html, /admin.html, /user.html.
    for _name in ("login.html", "admin.html", "user.html"):
        app.add_api_route(
            f"/{_name}", _page(_name), include_in_schema=False, methods=["GET"]
        )

    _hero = FRONTEND_DIR / "Neon Blockchain Security Shield.png"

    if _hero.is_file():
        app.add_api_route(
            "/Neon Blockchain Security Shield.png",
            lambda: FileResponse(_hero),
            include_in_schema=False,
            methods=["GET"],
        )
