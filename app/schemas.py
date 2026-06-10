import re
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, description="Unique username")
    password: str = Field(..., min_length=12, max_length=128, description="User password (min 12 characters)")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username must contain only alphanumeric characters, underscores, or hyphens.")
        return v

class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MessageCreate(BaseModel):
    receiver_id: int
    content: str = Field(..., min_length=1, max_length=4000, description="Message text content")

class MessageResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True
