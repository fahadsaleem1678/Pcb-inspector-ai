from pathlib import Path
from typing import Literal

from pydantic import Field
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
