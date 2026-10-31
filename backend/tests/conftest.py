import os
import sys
import tempfile
from pathlib import Path

import pytest

# Configure the environment BEFORE the app is imported.
_tmp = tempfile.mkdtemp(prefix="certichain-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use-1234567890"
os.environ["REVOKE_WARN_THRESHOLD"] = "3"
os.environ["REVOKE_CRITICAL_THRESHOLD"] = "5"
os.environ["REVOKE_WINDOW_DAYS"] = "30"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402
from app.auth import get_password_hash  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def make_admin(client):
    """Create an administrator and return auth headers for it."""

    def _make(username: str, institution: str) -> dict:
        db = SessionLocal()
        try:
            db.add(
                models.Admin(
                    username=username,
                    hashed_password=get_password_hash(PASSWORD),
                    institution=institution,
                    is_active=1,
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/auth/login", json={"username": username, "password": PASSWORD, "institution": institution},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _make


@pytest.fixture
def issue_certificate(client):
    def _issue(headers, institution="NIE Mysuru", name="Asha Rao"):
        response = client.post(
            "/api/certificates",
            headers=headers,
            json={
                "student_name": name,
                "student_id": "STU1",
                "course": "B.Tech CSE",
                "institution": institution,
                "issue_date": "2026-01-15",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["certificate_id"]

    return _issue
