import os
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from dotenv import load_dotenv

# Load SECRET_KEY and other settings from the .env file.
load_dotenv()

# Password hashing using Argon2.
password_hash = PasswordHash.recommended()


# JWT configuration.
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def get_password_hash(password: str) -> str:
    """Convert a plain-text password into a secure password hash."""
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    """Check whether a password matches its stored hash."""
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    role: str = "admin",
) -> str:
    """Create a signed JWT access token.

    The role claim ("admin" or "user") keeps a public user's token from
    being accepted on administrator endpoints.
    """

    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is missing. Configure it in the environment."
        )

    now = datetime.now(timezone.utc)
    expiry = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": expiry,
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Verify a JWT and return its payload."""

    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is missing. Configure it in the environment."
        )

    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "exp"]},
    )