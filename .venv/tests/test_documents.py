import json
import sqlite3

from app.database import engine

AADHAAR = "0000 0000 1234"
PAN = "ABCDE1234F"

SSLC = {
    "exam_year": 2020,
    "subjects": [
        {"name": "First Language (Kannada)", "max_marks": 125, "marks_obtained": 110},
        {"name": "English", "max_marks": 100, "marks_obtained": 88},
        {"name": "Mathematics", "max_marks": 100, "marks_obtained": 92},
    ],
}


def make_person(client, headers, name="Rahul Sharma"):
    response = client.post(
        "/api/persons", headers=headers,
        json={"full_name": name, "date_of_birth": "2004-05-17"},
    )
    assert response.status_code == 201, response.text
    return response.json()["person_ref"]


def issue(client, headers, person_ref, doc_type, number, details=None, issue_date="2020-07-01"):
    body = {"person_ref": person_ref, "doc_type": doc_type,
            "document_number": number, "issue_date": issue_date}
    if details is not None:
        body["details"] = details
    return client.post("/api/documents", headers=headers, json=body)


def test_one_person_holds_documents_from_different_institutes(client, make_admin):
    uidai = make_admin("uidai-admin", "UIDAI")
    tax = make_admin("tax-admin", "Income Tax Department")
    board = make_admin("board-admin", "Karnataka Secondary Education Examination Board")

    person = make_person(client, uidai)
    assert issue(client, uidai, person, "AADHAAR", AADHAAR).status_code == 201
    assert issue(client, tax, person, "PAN", PAN).status_code == 201
    assert issue(client, board, person, "SSLC_MARKS", "KA2020A12345", SSLC).status_code == 201

    persons = client.get("/api/persons", headers=uidai).json()
    assert len(persons) == 1 and persons[0]["document_count"] == 3
    assert {d["issuing_institution"] for d in persons[0]["documents"]} == {
        "UIDAI", "Income Tax Department",
        "Karnataka Secondary Education Examination Board",
    }
    assert {d["doc_type"] for d in persons[0]["documents"]} == {"AADHAAR", "PAN", "SSLC_MARKS"}


def test_issuer_is_the_admins_institution_not_client_supplied(client, make_admin):
    admin = make_admin("uidai-admin", "UIDAI")
    person = make_person(client, admin)
    body = {"person_ref": person, "doc_type": "AADHAAR", "document_number": AADHAAR,
            "issue_date": "2020-07-01", "issuing_institution": "Someone Else"}
    created = client.post("/api/documents", headers=admin, json=body).json()
    assert created["issuing_institution"] == "UIDAI"


def test_full_numbers_are_never_stored_or_returned(client, make_admin):
    admin = make_admin("uidai-admin", "UIDAI")
    person = make_person(client, admin)
    created = issue(client, admin, person, "AADHAAR", AADHAAR)
    pan = issue(client, admin, person, "PAN", PAN)

    assert created.json()["number_masked"] == "XXXX XXXX 1234"
    assert pan.json()["number_masked"] == "XXXXXX234F"

    everything = json.dumps(client.get("/api/documents", headers=admin).json())
    everything += json.dumps(client.get("/api/persons", headers=admin).json())
    everything += client.get(f"/api/documents/{created.json()['document_id']}").text
    assert "000000001234" not in everything and "ABCDE1234F" not in everything

    raw = engine.url.database
    dump = "\n".join(sqlite3.connect(raw).iterdump())
    assert "000000001234" not in dump and "0000 0000 1234" not in dump
    assert "ABCDE1234F" not in dump


def test_number_check_matches_only_the_real_number(client, make_admin):
    admin = make_admin("uidai-admin", "UIDAI")
    person = make_person(client, admin)
    doc_id = issue(client, admin, person, "AADHAAR", AADHAAR).json()["document_id"]
    url = f"/api/documents/{doc_id}/verify-number"

    assert client.post(url, json={"document_number": "0000 0000 1234"}).json()["number_matches"] is True
    assert client.post(url, json={"document_number": "000000001234"}).json()["number_matches"] is True
    assert client.post(url, json={"document_number": "000000001235"}).json()["number_matches"] is False
    assert client.post(url, json={"document_number": "12"}).status_code == 422


def test_rejects_bad_numbers_and_mismatched_details(client, make_admin):
    admin = make_admin("admin-a", "UIDAI")
    person = make_person(client, admin)

    assert issue(client, admin, person, "AADHAAR", "1234").status_code == 422
    assert issue(client, admin, person, "PAN", "1234567890").status_code == 422
    assert issue(client, admin, person, "SSLC_MARKS", "KA2020A12345").status_code == 422        # needs details
    assert issue(client, admin, person, "AADHAAR", AADHAAR, SSLC).status_code == 422            # must not have details
    assert issue(client, admin, "PER-NOPE", "AADHAAR", AADHAAR).status_code == 404
    assert issue(client, admin, person, "AADHAAR", AADHAAR, issue_date="2999-01-01").status_code == 422

    too_high = {"exam_year": 2020, "subjects": [{"name": "Maths", "max_marks": 100, "marks_obtained": 101}]}
    assert issue(client, admin, person, "SSLC_MARKS", "KA2020A12345", too_high).status_code == 422


def test_sslc_total_percentage_and_result_are_computed_by_the_server(client, make_admin):
    admin = make_admin("board", "Karnataka Secondary Education Examination Board")
    person = make_person(client, admin)

    doc = issue(client, admin, person, "SSLC_MARKS", "KA2020A12345", SSLC).json()
    assert doc["details"]["total_marks"] == 290
    assert doc["details"]["max_total_marks"] == 325
    assert doc["details"]["percentage"] == 89.23
    assert doc["details"]["result"] == "PASS"

    failing = {"exam_year": 2020, "subjects": [
        {"name": "Maths", "max_marks": 100, "marks_obtained": 34},
        {"name": "Science", "max_marks": 100, "marks_obtained": 90}]}
    doc = issue(client, admin, person, "SSLC_MARKS", "KA2020A99999", failing).json()
    assert doc["details"]["result"] == "FAIL"


def test_public_verify_endpoint_handles_certificates_and_documents(client, make_admin, issue_certificate):
    admin = make_admin("admin-a", "UIDAI")
    person = make_person(client, admin, "Rahul Sharma")
    doc_id = issue(client, admin, person, "AADHAAR", AADHAAR).json()["document_id"]
    cert_id = issue_certificate(admin)

    doc = client.get(f"/api/verify/{doc_id.lower()}").json()
    assert doc["kind"] == "DOCUMENT" and doc["holder_name"] == "Rahul Sharma"
    assert doc["doc_type_label"] == "Aadhaar Card" and doc["status"] == "ISSUED"
    assert "record_hash" not in doc and "person_ref" not in doc and "issued_by" not in doc

    assert client.get(f"/api/verify/{cert_id}").json()["kind"] == "CERTIFICATE"
    assert client.get("/api/verify/DOC-NOPE").status_code == 404
    assert client.get("/api/verify/XYZ-1").status_code == 404


def test_listing_persons_and_documents_requires_admin(client):
    assert client.get("/api/persons").status_code in (401, 403)
    assert client.get("/api/documents").status_code in (401, 403)
    assert client.post("/api/persons", json={"full_name": "A B", "date_of_birth": "2000-01-01"}).status_code in (401, 403)


def test_revoking_documents_is_scoped_and_counts_towards_the_warning(client, make_admin):
    uidai = make_admin("uidai-admin", "UIDAI")
    tax = make_admin("tax-admin", "Income Tax Department")
    person = make_person(client, uidai)

    ids = [issue(client, uidai, person, "AADHAAR", f"00000000{n:04d}").json()["document_id"] for n in range(3)]
    pan_id = issue(client, tax, person, "PAN", PAN).json()["document_id"]

    # The tax department cannot revoke an Aadhaar card.
    assert client.post(f"/api/documents/{ids[0]}/revoke", headers=tax, json={"reason": "not mine to revoke"}).status_code == 403

    results = [client.post(f"/api/documents/{i}/revoke", headers=uidai, json={"reason": "Duplicate record"}).json() for i in ids]
    assert [r["summary"]["level"] for r in results] == ["OK", "OK", "WARNING"]
    assert "UIDAI" not in (results[2]["warning"] or "")      # message speaks to the admin, not the org

    revoked = client.get(f"/api/documents/{ids[0]}").json()
    assert revoked["status"] == "REVOKED" and revoked["revoked_at"].endswith("Z")
    assert client.get(f"/api/documents/{pan_id}").json()["status"] == "ISSUED"   # untouched
    assert client.post(f"/api/documents/{ids[0]}/revoke", headers=uidai, json={"reason": "Duplicate record"}).status_code == 409
