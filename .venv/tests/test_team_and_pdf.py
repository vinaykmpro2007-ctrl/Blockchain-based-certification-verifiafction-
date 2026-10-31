PASSWORD = "correct-horse-battery"


def login(client, username):
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_new_admin_always_gets_the_creators_institution(client, make_admin):
    owner = make_admin("owner", "NIE Mysuru")

    # A client-supplied institution is ignored.
    response = client.post(
        "/api/admins", headers=owner,
        json={"username": "second.admin", "password": PASSWORD, "institution": "Somewhere Else"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["institution"] == "NIE Mysuru"

    # The new account can sign in and acts for the same institution.
    second = login(client, "second.admin")
    assert client.get("/api/auth/me", headers=second).json()["institution"] == "NIE Mysuru"


def test_team_list_only_shows_own_institution(client, make_admin):
    owner = make_admin("owner", "NIE Mysuru")
    make_admin("outsider", "ABC College")
    client.post("/api/admins", headers=owner, json={"username": "teammate", "password": PASSWORD})

    names = {m["username"] for m in client.get("/api/admins", headers=owner).json()}
    assert names == {"owner", "teammate"}


def test_team_account_rules(client, make_admin):
    owner = make_admin("owner", "NIE Mysuru")
    body = {"username": "teammate", "password": PASSWORD}

    assert client.post("/api/admins", json=body).status_code in (401, 403)          # no token
    assert client.post("/api/admins", headers=owner, json=body).status_code == 201
    assert client.post("/api/admins", headers=owner, json=body).status_code == 409   # duplicate
    short = {"username": "another", "password": "short"}
    assert client.post("/api/admins", headers=owner, json=short).status_code == 422


def test_user_token_cannot_create_admins(client):
    token = client.post(
        "/api/auth/register/user", json={"username": "visitor", "password": PASSWORD}
    ).json()["access_token"]
    response = client.post(
        "/api/admins", headers={"Authorization": f"Bearer {token}"},
        json={"username": "sneaky", "password": PASSWORD},
    )
    assert response.status_code == 401


def test_certificate_institution_is_forced(client, make_admin, issue_certificate):
    owner = make_admin("owner", "NIE Mysuru")
    cert_id = issue_certificate(owner, institution="Forged University")
    assert client.get(f"/api/certificates/{cert_id}").json()["institution"] == "NIE Mysuru"

    # And the field is no longer required.
    response = client.post(
        "/api/certificates", headers=owner,
        json={"student_name": "Asha Rao", "student_id": "S1", "course": "MBA", "issue_date": "2026-01-15"},
    )
    assert response.status_code == 201


def test_pdf_download(client, make_admin, issue_certificate):
    owner = make_admin("owner", "NIE Mysuru")
    cert_id = issue_certificate(owner)

    response = client.get(f"/api/certificates/{cert_id}/pdf", headers=owner)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert cert_id in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")

    # Revoked certificates still download (stamped as revoked).
    client.post(f"/api/certificates/{cert_id}/revoke", headers=owner, json={"reason": "Issued by mistake"})
    assert client.get(f"/api/certificates/{cert_id}/pdf", headers=owner).status_code == 200


def test_pdf_requires_admin_and_existing_certificate(client, make_admin):
    owner = make_admin("owner", "NIE Mysuru")
    assert client.get("/api/certificates/CERT-X/pdf").status_code in (401, 403)
    assert client.get("/api/certificates/CERT-NOPE/pdf", headers=owner).status_code == 404
