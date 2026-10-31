from datetime import timedelta

from app import models
from app.database import SessionLocal


def revoke(client, headers, certificate_id, reason="Issued with wrong name"):
    return client.post(
        f"/api/certificates/{certificate_id}/revoke",
        headers=headers,
        json={"reason": reason},
    )


def test_issuing_and_listing_require_admin_token(client, make_admin):
    body = {
        "student_name": "Asha Rao", "student_id": "S1", "course": "BCA",
        "institution": "NIE", "issue_date": "2026-01-01",
    }
    assert client.post("/api/certificates", json=body).status_code in (401, 403)
    assert client.get("/api/certificates").status_code in (401, 403)


def test_user_token_cannot_act_as_admin_even_with_same_username(client, make_admin):
    make_admin("shared-name", "NIE")
    user = client.post(
        "/api/auth/register/user",
        json={"username": "shared-name", "password": "a-very-long-password"},
    )
    assert user.status_code == 201
    headers = {"Authorization": f"Bearer {user.json()['access_token']}"}

    assert client.get("/api/certificates", headers=headers).status_code == 401
    assert client.get("/api/admin/revocations/summary", headers=headers).status_code == 401


def test_revoke_marks_certificate_and_public_view_hides_reason(client, make_admin, issue_certificate):
    headers = make_admin("subhash", "NIE Mysuru")
    cert_id = issue_certificate(headers)

    response = revoke(client, headers, cert_id)
    assert response.status_code == 200
    assert response.json()["status"] == "REVOKED"

    public = client.get(f"/api/certificates/{cert_id}").json()
    assert public["status"] == "REVOKED"
    assert public["revoked_at"].endswith("Z")
    assert "revoke_reason" not in public
    assert "issued_by" not in public

    listed = client.get("/api/certificates", headers=headers).json()[0]
    assert listed["revoke_reason"] == "Issued with wrong name"
    assert listed["revoked_by"] == "subhash"


def test_revoke_needs_a_reason_and_cannot_repeat(client, make_admin, issue_certificate):
    headers = make_admin("subhash", "NIE Mysuru")
    cert_id = issue_certificate(headers)

    assert revoke(client, headers, cert_id, reason="no").status_code == 422
    assert revoke(client, headers, cert_id).status_code == 200
    assert revoke(client, headers, cert_id).status_code == 409
    assert revoke(client, headers, "CERT-DOESNOTEXIST").status_code == 404


def test_only_own_institution_or_issuer_may_revoke(client, make_admin, issue_certificate):
    owner = make_admin("owner", "NIE Mysuru")
    colleague = make_admin("colleague", "nie  mysuru")      # same institution, different spelling
    outsider = make_admin("outsider", "ABC College")
    cert_id = issue_certificate(owner)

    assert revoke(client, outsider, cert_id).status_code == 403
    assert client.get(f"/api/certificates/{cert_id}").json()["status"] == "PENDING"
    assert revoke(client, colleague, cert_id).status_code == 200

    # The institution typed on the form is ignored (it is forced to the
    # admin's own), and an admin can always revoke what they issued.
    cert_2 = issue_certificate(outsider, institution="Some Other Name")
    assert revoke(client, outsider, cert_2).status_code == 200


def test_warning_levels_escalate_with_number_of_revokes(client, make_admin, issue_certificate):
    headers = make_admin("subhash", "NIE Mysuru")
    ids = [issue_certificate(headers) for _ in range(6)]

    results = [revoke(client, headers, cert_id).json() for cert_id in ids[:5]]

    assert [r["summary"]["level"] for r in results] == ["OK", "OK", "WARNING", "WARNING", "CRITICAL"]
    assert results[0]["warning"] is None
    assert results[1]["summary"]["remaining_before_warning"] == 1
    assert "Warning" in results[2]["warning"] and "3" in results[2]["warning"]
    assert results[4]["warning"].startswith("Critical")

    summary = client.get("/api/admin/revocations/summary", headers=headers).json()
    assert summary["level"] == "CRITICAL"
    assert summary["own_revocations"] == 5
    assert summary["institution_revocations"] == 5
    assert summary["warn_threshold"] == 3 and summary["critical_threshold"] == 5


def test_counts_are_per_admin_and_only_inside_the_window(client, make_admin, issue_certificate):
    a = make_admin("admin-a", "NIE Mysuru")
    b = make_admin("admin-b", "NIE Mysuru")

    for _ in range(3):
        assert revoke(client, a, issue_certificate(a)).status_code == 200

    assert client.get("/api/admin/revocations/summary", headers=a).json()["level"] == "WARNING"

    summary_b = client.get("/api/admin/revocations/summary", headers=b).json()
    assert summary_b["level"] == "OK"
    assert summary_b["own_revocations"] == 0
    assert summary_b["institution_revocations"] == 3       # institution total is still visible

    # Age two of A's revocations beyond the 30-day window -> back to OK.
    db = SessionLocal()
    try:
        old = models.utcnow() - timedelta(days=45)
        for entry in db.query(models.Revocation).limit(2).all():
            entry.revoked_at = old
        db.commit()
    finally:
        db.close()

    summary_a = client.get("/api/admin/revocations/summary", headers=a).json()
    assert summary_a["own_revocations"] == 1
    assert summary_a["level"] == "OK"


def test_revocation_log_is_scoped_to_the_institution(client, make_admin, issue_certificate):
    mine = make_admin("mine", "NIE Mysuru")
    other = make_admin("other", "ABC College")

    revoke(client, mine, issue_certificate(mine))
    revoke(client, other, issue_certificate(other, institution="ABC College"))

    log = client.get("/api/admin/revocations", headers=mine).json()
    assert len(log) == 1
    assert log[0]["revoked_by"] == "mine" and log[0]["target_type"] == "CERTIFICATE"


def test_policy_from_environment(client, make_admin, issue_certificate, monkeypatch):
    monkeypatch.setenv("REVOKE_WARN_THRESHOLD", "1")
    monkeypatch.setenv("REVOKE_CRITICAL_THRESHOLD", "2")
    headers = make_admin("subhash", "NIE Mysuru")

    first = revoke(client, headers, issue_certificate(headers)).json()
    second = revoke(client, headers, issue_certificate(headers)).json()

    assert first["summary"]["level"] == "WARNING"
    assert second["summary"]["level"] == "CRITICAL"
