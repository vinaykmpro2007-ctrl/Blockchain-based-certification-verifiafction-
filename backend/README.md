# CertiChain backend

FastAPI + SQLite backend for certificate / document verification.

## Run

    cd xmm/.venv                      # the folder containing certichain.db and app/
    pip install -r app/requirements.txt
    python -m app.create_admin        # once per administrator (admins are NOT self-service)
    uvicorn app.main:app --reload --host 0.0.0.0     # 0.0.0.0 lets phones on your Wi-Fi reach it

Open http://localhost:8000/login.html (admin and user pages are served by the backend),
API docs at http://localhost:8000/docs.

The database is upgraded automatically on start-up (new tables and columns are added,
existing rows are kept).

## Admin sign-in needs the institution

The admin login asks for **institution name + username + password**. The institution must be the one
the account belongs to (spacing and capitals are ignored). A wrong institution gives the same
"Incorrect username, password or institution" message as a wrong password, so nothing is revealed.
`POST /api/auth/login` now takes `{"username", "password", "institution"}`.

## Real / Fake

Every verification result carries `authenticity`:

* **REAL** - the ID exists in the register, i.e. an institution issued it (a revoked record is still REAL, but shows as revoked).
* **FAKE** - no such ID (`/api/verify/...` answers 404 with `"authenticity": "FAKE"`). When a certificate **PDF** is uploaded, its name, student ID, course, institution and date must also match the issuer's record; a real ID on an edited PDF is shown as FAKE.

Admins can open **People** to see all documents of a person from every institution, and use
**View / Check** (`POST /api/documents/{id}/check`) to verify one: it re-computes the record fingerprint and can
compare the number on the paper document. Revoking is still limited to your own institution.

## Revocation warnings

Administrators can revoke certificates and documents (a reason is required, revocation
cannot be undone). Every revocation is logged. The number of revocations an administrator
made in a rolling window drives a warning on the dashboard, in the revoke dialog (before
the action) and in the API response:

| Level    | When (defaults)                      |
|----------|--------------------------------------|
| OK       | fewer than 3 revocations in 30 days  |
| WARNING  | 3 or more                            |
| CRITICAL | 5 or more                            |

Change with these optional lines in `.env`:

    REVOKE_WARN_THRESHOLD=3
    REVOKE_CRITICAL_THRESHOLD=5
    REVOKE_WINDOW_DAYS=30

An administrator may revoke what they issued, or anything issued by their own institution.

## Issued documents (Aadhaar, PAN, SSLC marks)

One `persons` row can hold many `issued_documents`, each issued by a different institution.
Sample data (one fictional person, three institutes):

    python -m app.seed_documents                 # safe to repeat
    python -m app.seed_documents --demo-admins   # also one demo admin per institute (passwords printed once)

Privacy: the full Aadhaar/PAN/register number is **never stored**. The database keeps a masked
form (last 4 characters) and an HMAC hash keyed from `SECRET_KEY`, so
`POST /api/documents/{id}/verify-number` can confirm a number without revealing it.
Changing `SECRET_KEY` makes existing number checks fail. The seed numbers are fictional and invalid.

## Main endpoints

| Method | Path | Who |
|---|---|---|
| GET | `/api/verify/{CERT-... or DOC-...}` | public |
| GET | `/api/certificates/{id}`, `/api/documents/{id}` | public (documents masked) |
| POST | `/api/documents/{id}/verify-number` | public |
| POST | `/api/certificates`, `/api/persons`, `/api/documents` | admin |
| GET | `/api/certificates`, `/api/persons`, `/api/documents` | admin |
| POST | `/api/certificates/{id}/revoke`, `/api/documents/{id}/revoke` | admin |
| GET | `/api/certificates/{id}/pdf` (certificate PDF with QR code) | admin |
| POST | `/api/admins` (add a colleague, always at your own institution) | admin |
| GET | `/api/admins` (admins of your institution) | admin |
| GET | `/api/persons?q=`, `/api/persons/{person_ref}` (all documents, any institution) | admin |
| POST | `/api/documents/{id}/check` (integrity + optional number check) | admin |
| GET | `/api/admin/revocations/summary`, `/api/admin/revocations` | admin |

## Team accounts

An admin can add colleagues from the **Team** page (or `POST /api/admins`). The new account always
joins the creator's institution; there is no way to pick another one. Admins cannot be created
from the public login page. `create_admin.py` is still how the very first admin of an institution is made.

## Certificate PDF and QR links

`GET /api/certificates/{id}/pdf` builds the PDF with reportlab (no extra tools). The QR code opens
`/user.html?id=CERT-...`, which verifies automatically. If you are browsing on `localhost`, the QR code uses this
computer's Wi-Fi/LAN address instead (a phone cannot open `localhost`), so run uvicorn with `--host 0.0.0.0`, keep the phone
on the same network and allow port 8000 in the firewall. Set `PUBLIC_BASE_URL` in `.env`
(for example `https://certs.example.edu`) when the site is served behind a proxy or on a real domain;
otherwise the address of the request is used.

## Tests

    pip install -r requirements-dev.txt
    pytest
