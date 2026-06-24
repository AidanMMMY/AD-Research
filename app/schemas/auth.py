"""Authentication-related Pydantic schemas."""

from pydantic import BaseModel


class UserResponse(BaseModel):
    username: str
    role: str
