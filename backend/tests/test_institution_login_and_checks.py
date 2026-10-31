from app import urls

PASSWORD = "correct-horse-battery"


def login(client, username, institution, password=PASSWORD):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password, "institution": institution},
    )


# ---------------------------------------------------------------- login

def test_admin_signs_in_only_with_their_own_institution(client, make_admin):
    make_admin("owner", "NIE Mysuru")

    assert login(client, "owner", "NIE Mysuru").status_code == 200
    # Spacing and case do not matter.
    assert login(client, "owner", "  nie   MYSURU ").status_code == 200

    wrong = login(client, "owner", "ABC College")
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Incorrect username, password or institution"

    # Same message for a wrong password or an unknown user: nothing is leaked.
    assert login(client, "owner", "NIE Mysuru", "wrong-password-here").json() == wrong.json()
    assert login(client, "nobody", "NIE Mysuru").json() == wrong.json()


def test_institution_is_required_for_admin_login(client, make_admin):
    make_admin("owner", "NIE Mysuru")
    response = client.post("/api/auth/login", json={"username": "owner", "password": PASSWORD})
    assert response.status_code == 422


def test_verifier_login_does_not_need_an_institution(client):
    client.post("/api/auth/register/user", json={"username": "priya", "password": "a-very-long-password"})
    ok = client.post("/api/auth/user/login", json={"username": "priya", "password": "a-very-long-password"})
    assert ok.status_code == 200


# ---------------------------------------------------------- real / fake

def test_found_records_are_real_and_unknown_ids_are_fake(client, make_admin, issue_certificate):
    owner = make_admin("owner", "NIE Mysuru")
    cert_id = issue_certificate(owner)

    real = client.get(f"/api/verify/{cert_id}")
    assert real.status_code == 200 and real.json()["authenticity"] == "REAL"

    for fake_id in ("CERT-DOESNOTEXIST", "DOC-NOPE", "HELLO-1"):
        fake = client.get(f"/api/verify/{fake_id}")
        assert fake.status_code == 404
        assert fake.json()["authenticity"] == "FAKE"
        assert isinstance(fake.json()["detail"], str)


def test_revoked_record_is_still_real_but_revoked(client, make_admin, issue_certificate):
    owner = make_admin("owner", "NIE Mysuru")
    cert_id = issue_certificate(owner)
    client.post(f"/api/certificates/{cert_id}/revoke", headers=owner, json={"reason": "Issued by mistake"})

    body = client.get(f"/api/verify/{cert_id}").json()
    assert body["status"] == "REVOKED" and body["authenticity"] == "REAL"


# ------------------------------------------- other institutions' documents

def _person_with_two_issuers(client, make_admin):
    uidai = make_admin("uidai-admin", "UIDAI")
    tax = make_admin("tax-admin", "Income Tax Department")
    person = client.post(
        "/api/persons", headers=uidai,
        json={"full_name": "Rahul Sharma", "date_of_birth": "2004-05-17"},
    ).json()["person_ref"]
    for headers, kind, number in ((uidai, "AADHAAR", "000000001234"), (tax, "PAN", "ABCDE1234F")):
        r = client.post("/api/documents", headers=headers, json={
            "person_ref": person, "doc_type": kind, "document_number": number, "issue_date": "2020-07-01"})
        assert r.status_code == 201, r.text
    return uidai, tax, person


def test_admin_sees_a_persons_documents_from_other_institutions(client, make_admin):
    uidai, tax, person = _person_with_two_issuers(client, make_admin)

    detail = client.get(f"/api/persons/{person}", headers=uidai).json()
    by_type = {d["doc_type"]: d for d in detail["documents"]}
    assert set(by_type) == {"AADHAAR", "PAN"}
    assert by_type["PAN"]["issuing_institution"] == "Income Tax Department"
    assert by_type["PAN"]["can_revoke"] is False        # view only: not their institution
    assert by_type["AADHAAR"]["can_revoke"] is True
    assert by_type["PAN"]["number_masked"] == "XXXXXX234F"      # never the full number

    assert client.get("/api/persons/PER-NOPE", headers=uidai).status_code == 404
    assert client.get(f"/api/persons/{person}").status_code in (401, 403)   # admins only


def test_person_search(client, make_admin):
    uidai, _, person = _person_with_two_issuers(client, make_admin)
    assert len(client.get("/api/persons?q=rahul", headers=uidai).json()) == 1
    assert len(client.get(f"/api/persons?q={person.lower()}", headers=uidai).json()) == 1
    assert client.get("/api/persons?q=zzz", headers=uidai).json() == []


def test_admin_can_check_another_institutions_document(client, make_admin):
    uidai, tax, person = _person_with_two_issuers(client, make_admin)
    pan_id = next(d["document_id"] for d in client.get(f"/api/persons/{person}", headers=uidai).json()["documents"]
                  if d["doc_type"] == "PAN")

    ok = client.post(f"/api/documents/{pan_id}/check", headers=uidai, json={"document_number": "abcde 1234f"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["authenticity"] == "REAL" and body["integrity_ok"] and body["number_matches"] is True
    assert body["issued_by_your_institution"] is False

    wrong = client.post(f"/api/documents/{pan_id}/check", headers=uidai, json={"document_number": "ZZZZZ9999Z"}).json()
    assert wrong["authenticity"] == "FAKE" and wrong["number_matches"] is False

    no_number = client.post(f"/api/documents/{pan_id}/check", headers=uidai, json={}).json()
    assert no_number["authenticity"] == "REAL" and no_number["number_matches"] is None

    bad_format = client.post(f"/api/documents/{pan_id}/check", headers=uidai, json={"document_number": "12"})
    assert bad_format.status_code == 422
    assert client.post(f"/api/documents/{pan_id}/check", json={}).status_code in (401, 403)


def test_tampered_record_is_flagged_fake(client, make_admin):
    from app.database import SessionLocal
    from app import models
    uidai, _, person = _person_with_two_issuers(client, make_admin)
    doc_id = client.get(f"/api/persons/{person}", headers=uidai).json()["documents"][0]["document_id"]

    db = SessionLocal()
    try:
        db.query(models.IssuedDocument).filter_by(document_id=doc_id).update({"issue_date": "1999-01-01"})
        db.commit()
    finally:
        db.close()

    body = client.post(f"/api/documents/{doc_id}/check", headers=uidai, json={}).json()
    assert body["integrity_ok"] is False and body["authenticity"] == "FAKE"


# --------------------------------------------------------------- QR links

def test_qr_base_url_never_uses_localhost_when_a_lan_address_exists(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setattr(urls, "lan_ip", lambda: "192.168.1.20")

    assert urls.public_base_url("http://localhost:8000/") == "http://192.168.1.20:8000"
    assert urls.public_base_url("http://127.0.0.1:8000/") == "http://192.168.1.20:8000"
    assert urls.public_base_url("https://certs.example.edu/") == "https://certs.example.edu"
    assert urls.public_base_url("http://192.168.1.99:8000/") == "http://192.168.1.99:8000"

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://certs.example.edu/")
    assert urls.public_base_url("http://localhost:8000/") == "https://certs.example.edu"

    monkeypatch.delenv("PUBLIC_BASE_URL")
    monkeypatch.setattr(urls, "lan_ip", lambda: None)   # offline: keep what we have
    assert urls.public_base_url("http://localhost:8000/") == "http://localhost:8000"


def test_pdf_qr_points_at_the_lan_address(make_admin, issue_certificate, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    # The admin is browsing on the server itself, so the request says "localhost".
    client = TestClient(app, base_url="http://localhost:8000")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setattr(urls, "lan_ip", lambda: "192.168.1.20")
    owner = make_admin("owner", "NIE Mysuru")
    cert_id = issue_certificate(owner)

    captured = {}
    from app import certificate_pdf
    real = certificate_pdf.build_certificate_pdf
    monkeypatch.setattr(certificate_pdf, "build_certificate_pdf",
                        lambda cert, base: captured.setdefault("base", base) and real(cert, base))
    assert client.get(f"/api/certificates/{cert_id}/pdf", headers=owner).status_code == 200
    assert captured["base"] == "http://192.168.1.20:8000"

    me = client.get("/api/auth/me", headers=owner).json()
    assert me["verify_base_url"].startswith("http://192.168.1.20")
