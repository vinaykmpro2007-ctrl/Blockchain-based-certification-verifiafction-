import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.migrate import ensure_schema


def test_user_registration_and_login(client):
    created = client.post("/api/auth/register/user", json={"username": "priya", "password": "a-very-long-password"})
    assert created.status_code == 201 and created.json()["access_token"]

    assert client.post("/api/auth/register/user", json={"username": "priya", "password": "a-very-long-password"}).status_code == 409
    assert client.post("/api/auth/register/user", json={"username": "short", "password": "tooshort"}).status_code == 422

    ok = client.post("/api/auth/user/login", json={"username": "priya", "password": "a-very-long-password"})
    assert ok.status_code == 200
    assert client.post("/api/auth/user/login", json={"username": "priya", "password": "wrong-password-here"}).status_code == 401


def test_admin_accounts_cannot_be_self_registered(client):
    response = client.post("/api/auth/register/admin", json={"username": "x", "password": "y", "institution": "z"})
    assert response.status_code == 403
    assert "create_admin.py" in response.json()["detail"]


def test_admin_profile_endpoint(client, make_admin):
    headers = make_admin("subhash", "NIE")
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["username"] == "subhash" and me["institution"] == "NIE"
    assert me["verify_base_url"].startswith("http")


def test_existing_database_is_upgraded_without_losing_rows(tmp_path: Path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE certificates (
            id INTEGER NOT NULL, certificate_id VARCHAR NOT NULL, student_name VARCHAR NOT NULL,
            student_id VARCHAR NOT NULL, course VARCHAR NOT NULL, institution VARCHAR NOT NULL,
            issue_date VARCHAR NOT NULL, status VARCHAR NOT NULL, PRIMARY KEY (id));
        INSERT INTO certificates VALUES (1,'CERT-OLD','Rahul Sharma','STU1001','BCA','ABC College','2026-10-30','PENDING');
        """
    )
    con.commit(); con.close()

    engine = create_engine(f"sqlite:///{path}")
    added = ensure_schema(engine)
    assert set(added) == {"certificates.issued_by", "certificates.revoked_at",
                          "certificates.revoked_by", "certificates.revoke_reason"}
    assert {"persons", "issued_documents", "revocations", "users"} <= set(inspect(engine).get_table_names())

    row = sqlite3.connect(path).execute("select certificate_id, status, revoked_at from certificates").fetchone()
    assert row == ("CERT-OLD", "PENDING", None)

    assert ensure_schema(engine) == []          # second run changes nothing


def test_frontend_pages_are_served(client):
    for page in ("/login.html", "/admin.html", "/user.html"):
        response = client.get(page)
        assert response.status_code == 200 and "<html" in response.text.lower(), page
    assert client.get("/static/js/app.js").status_code == 200
