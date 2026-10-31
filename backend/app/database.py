import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Store the database in the backend folder (override with DATABASE_URL).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./certichain.db")

# Create the database engine.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Create database sessions.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for database models.
Base = declarative_base()
