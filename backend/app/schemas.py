from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CertificateCreate(BaseModel):
    student_name: str = Field(min_length=2, max_length=150)
    student_id: str = Field(min_length=1, max_length=50)
    course: str = Field(min_length=2, max_length=200)
    # Ignored by the server: certificates are always issued under the
    # signed-in admin's institution. Kept so older clients still work.
    institution: str | None = Field(default=None, max_length=200)
    issue_date: date

    @field_validator("student_name", "course")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        value = " ".join(value.split())

        if len(value) < 2:
            raise ValueError("Must contain at least 2 non-whitespace characters.")

        return value

    @field_validator("student_id")
    @classmethod
    def validate_student_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Student ID cannot be empty.")

        return value

    @field_validator("issue_date")
    @classmethod
    def validate_issue_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Issue date cannot be in the future.")

        return value


class CertificateResponse(BaseModel):
    certificate_id: str
    student_name: str
    student_id: str
    course: str
    institution: str
    issue_date: date
    status: str


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------

class RevokeRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=300)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = " ".join(value.split())

        if len(value) < 5:
            raise ValueError("Give a reason of at least 5 characters.")

        return value


# ---------------------------------------------------------------------------
# Public user accounts
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=12, max_length=128)


# ---------------------------------------------------------------------------
# Persons and issued documents
# ---------------------------------------------------------------------------

class PersonCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    date_of_birth: date

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())

        if len(value) < 2:
            raise ValueError("Must contain at least 2 non-whitespace characters.")

        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("Date of birth must be in the past.")

        return value


class SubjectMark(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    max_marks: int = Field(ge=1, le=200)
    marks_obtained: int = Field(ge=0, le=200)

    @field_validator("name")
    @classmethod
    def clean_subject(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def marks_within_maximum(self):
        if self.marks_obtained > self.max_marks:
            raise ValueError(
                f"{self.name}: marks obtained cannot exceed maximum marks."
            )

        return self


class SSLCDetails(BaseModel):
    exam_year: int = Field(ge=1950)
    subjects: list[SubjectMark] = Field(min_length=1, max_length=12)

    @field_validator("exam_year")
    @classmethod
    def year_not_in_future(cls, value: int) -> int:
        if value > date.today().year:
            raise ValueError("Exam year cannot be in the future.")

        return value


class DocumentCreate(BaseModel):
    person_ref: str = Field(min_length=3, max_length=40)
    doc_type: Literal["AADHAAR", "PAN", "SSLC_MARKS"]
    document_number: str = Field(min_length=1, max_length=40)
    issue_date: date
    details: SSLCDetails | None = None

    @field_validator("issue_date")
    @classmethod
    def validate_issue_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Issue date cannot be in the future.")

        return value

    @model_validator(mode="after")
    def details_match_type(self):
        if self.doc_type == "SSLC_MARKS" and self.details is None:
            raise ValueError("SSLC marks cards need subject marks in 'details'.")

        if self.doc_type != "SSLC_MARKS" and self.details is not None:
            raise ValueError("Only SSLC marks cards take 'details'.")

        return self


class NumberCheck(BaseModel):
    document_number: str = Field(min_length=1, max_length=40)


class DocumentCheck(BaseModel):
    """Optional number read from the paper document, for administrators."""

    document_number: str | None = Field(default=None, max_length=40)
