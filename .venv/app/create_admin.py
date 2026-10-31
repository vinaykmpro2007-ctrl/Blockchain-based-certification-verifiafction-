from getpass import getpass

from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app import models
from app.auth import get_password_hash


def main():
    # Ensure the database tables exist.
    Base.metadata.create_all(bind=engine)

    username = input("Admin username: ").strip()
    institution = input("Institution name: ").strip()

    if len(username) < 3:
        print("Username must contain at least 3 characters.")
        return

    if len(institution) < 2:
        print("Institution name must contain at least 2 characters.")
        return

    password = getpass("Admin password (minimum 12 characters): ")
    confirm_password = getpass("Confirm password: ")

    if len(password) < 12:
        print("Password must contain at least 12 characters.")
        return

    if len(password) > 128:
        print("Password must not exceed 128 characters.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    db: Session = SessionLocal()

    try:
        existing_admin = (
            db.query(models.Admin)
            .filter(models.Admin.username == username)
            .first()
        )

        if existing_admin:
            print("An administrator with that username already exists.")
            return

        admin = models.Admin(
            username=username,
            hashed_password=get_password_hash(password),
            institution=institution,
            is_active=1,
        )

        db.add(admin)
        db.commit()

        print(f"Administrator '{username}' created successfully.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()