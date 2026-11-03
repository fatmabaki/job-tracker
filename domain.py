from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["saved", "applied", "interview", "offer", "rejected"]
class ApplicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(min_length=1, max_length=150)
    role: str = Field(min_length=1, max_length=150)
    status: Status = "saved"
    notes: str = Field(default="", max_length=5000)
    @field_validator("company", "role")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()

class ReminderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    scheduled_at: datetime | None = None
    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Include a timezone, for example +00:00")
        return value

class NotFound(Exception):
    pass

@dataclass(frozen=True)
class Settings:
    database_url: str
    sslmode: str
    token: str
    resend_key: str
    email_from: str
    worker_enabled: bool = True
    poll_seconds: float = 2.0
