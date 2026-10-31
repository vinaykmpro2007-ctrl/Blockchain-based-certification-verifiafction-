from pydantic import BaseModel, Field, ConfigDict


class AdminCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    institution: str = Field(min_length=2, max_length=200)


class TeamAdminCreate(BaseModel):
    """A colleague added by an existing admin. No institution field: it is
    always the creator's institution."""

    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._@-]+$")
    password: str = Field(min_length=12, max_length=128)


class AdminLogin(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class AdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    institution: str
    is_active: int


class AdminLoginRequest(BaseModel):
    """Administrator sign-in. The institution must match the account's own."""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=128)
    institution: str = Field(min_length=2, max_length=200)
