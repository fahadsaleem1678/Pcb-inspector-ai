from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PCB_", env_file=".env", extra="ignore")

    # Fail closed instead of accidentally deploying local identity/demo inference.
    environment: Literal["local", "test", "portfolio"] = "local"
    detector: Literal["demo", "research"] = "demo"
    research_checkpoint: Path | None = None
    database_url: str = "sqlite:///.runtime/pcb.db"
    storage_path: Path = Path(".runtime/objects")
    storage_backend: Literal["local", "s3"] = "local"
    queue_backend: Literal["database", "sqs"] = "database"
    aws_region: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[a-z0-9]+)+-\d$")
    s3_bucket: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
    s3_prefix: str = "pcb-inspector"
    s3_kms_key_id: str | None = Field(default=None, min_length=1)
    sqs_queue_url: str | None = None
    sqs_visibility_seconds: int = Field(default=120, ge=30, le=3600)
    outbox_lease_seconds: int = Field(default=120, ge=30, le=3600)
    local_user_id: str = "local-developer"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=20_000_000, gt=0)
    min_image_dimension: int = Field(default=64, gt=0)
    max_image_dimension: int = Field(default=8192, gt=0)
    worker_poll_seconds: float = Field(default=1, gt=0)
    lease_seconds: int = Field(default=120, gt=0)
    max_attempts: int = Field(default=3, gt=0, le=10)
    retry_delay_seconds: float = Field(default=2, ge=0)

    cors_origins: tuple[str, ...] = ()

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
    def require_backend_configuration(self) -> Self:
        from urllib.parse import urlsplit

        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("CORS origins must be exact HTTPS origins without paths")
        if self.environment == "portfolio" and self.auth_mode != "cognito":
            raise ValueError("Public portfolio deployments require Cognito user isolation")
        if self.detector == "research" and self.research_checkpoint is None:
            raise ValueError("Research detector requires a checkpoint path")
        if self.auth_mode == "cognito" and (
            not self.cognito_user_pool_id or not self.cognito_client_id
        ):
            raise ValueError("Cognito mode requires user pool ID and app client ID")
        if self.storage_backend == "s3" and (not self.aws_region or not self.s3_bucket):
            raise ValueError("S3 storage requires an AWS region and bucket")
        if (
            not self.s3_prefix
            or self.s3_prefix.startswith("/")
            or len(self.s3_prefix.encode("utf-8")) > 400
            or any(ord(c) < 32 for c in self.s3_prefix)
            or "\\" in self.s3_prefix
            or any(part in ("", ".", "..") for part in self.s3_prefix.split("/"))
        ):
            raise ValueError("S3 prefix must be a nonempty relative namespace")
        if self.queue_backend == "sqs":
            import re

            if self.storage_backend != "s3":
                raise ValueError("SQS workers require shared S3 storage")
            region = re.escape(self.aws_region or "")
            if not re.fullmatch(
                rf"https://sqs\.{region}\.amazonaws\.com(?:\.cn)?/\d{{12}}/[A-Za-z0-9_-]{{1,80}}",
                self.sqs_queue_url or "",
            ):
                raise ValueError("SQS requires a standard AWS queue URL in the configured region")
            if self.lease_seconds < 30:
                raise ValueError("SQS database leases must be at least 30 seconds")
        return self
