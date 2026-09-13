"""AWS SDK construction. Uses the SDK credential chain; no embedded credentials/endpoints."""

from importlib import import_module
from typing import Any

from pcb_inspector.config import Settings


def aws_client(service: str, settings: Settings) -> Any:
    boto3 = import_module("boto3")
    config = import_module("botocore.config").Config(
        connect_timeout=3,
        read_timeout=25,
        retries={"mode": "standard", "total_max_attempts": 3},
    )
    return boto3.client(service, region_name=settings.aws_region, config=config)
