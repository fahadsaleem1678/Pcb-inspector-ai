from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PCB_", env_file=".env", extra="ignore")

    # Fail closed instead of accidentally deploying local identity/demo inference.
    environment: Literal["local", "test"] = "local"
    detector: Literal["demo"] = "demo"
    database_url: str = "sqlite:///.runtime/pcb.db"
    storage_path: Path = Path(".runtime/objects")
    local_user_id: str = "local-developer"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=20_000_000, gt=0)
    min_image_dimension: int = Field(default=64, gt=0)
    max_image_dimension: int = Field(default=8192, gt=0)
    worker_poll_seconds: float = Field(default=1, gt=0)
    lease_seconds: int = Field(default=120, gt=0)
    max_attempts: int = Field(default=3, gt=0, le=10)
    retry_delay_seconds: float = Field(default=2, ge=0)

    auth_mode: Literal["local", "cognito"] = "local"
    cognito_user_pool_id: str | None = Field(
        default=None,
        pattern=r"^[a-z]{2}(?:-[a-z0-9]+)+-\d_[A-Za-z0-9]+$",
        max_length=64,
    )
    cognito_client_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]+$", max_length=128)
    cognito_required_scopes: tuple[str, ...] = ()
    cognito_audience: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_cognito_configuration(self) -> Self:
        if self.auth_mode == "cognito" and (
            not self.cognito_user_pool_id or not self.cognito_client_id
        ):
            raise ValueError("Cognito mode requires user pool ID and app client ID")
        return self
