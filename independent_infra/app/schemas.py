from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ModuleId = Literal["purchase_orders", "sales_orders"]


class LicenseRequest(BaseModel):
    key: str = Field(min_length=8, max_length=128)
    hwid: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    appVersion: str = Field(min_length=1, max_length=32)


class CreateLicenseRequest(BaseModel):
    discord_user_id: str | None = Field(default=None, max_length=32)
    duration_days: int | None = Field(default=30, ge=1, le=3650)
    duration_hours: int | None = Field(default=None, ge=1, le=87_600)
    device_limit: int = Field(default=1, ge=1, le=25)
    modules: list[ModuleId] = Field(
        default_factory=lambda: ["purchase_orders", "sales_orders"]
    )
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_duration(self) -> "CreateLicenseRequest":
        if self.duration_hours is not None and self.duration_days not in (None, 30):
            raise ValueError("informe duration_days ou duration_hours, nao ambos")
        if not self.modules:
            raise ValueError("ao menos um modulo e obrigatorio")
        self.modules = list(dict.fromkeys(self.modules))
        return self


class ExtendLicenseRequest(BaseModel):
    days: int = Field(ge=1, le=3650)


class LicenseCreated(BaseModel):
    id: str
    key: str
    key_preview: str
    expires_at: datetime
    device_limit: int
    modules: list[ModuleId]


class LicenseSummary(BaseModel):
    id: str
    key_preview: str
    discord_user_id: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    device_limit: int
    device_count: int
    modules: list[ModuleId]
    notes: str
    last_activity: datetime | None


class StatsResponse(BaseModel):
    active: int
    expires_within_7_days: int
    expired: int
    revoked: int
    devices: int
    total: int

