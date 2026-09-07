import json
import logging
import time

from prometheus_client import CollectorRegistry, Counter, Histogram


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": time.time(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "inspection_id": getattr(record, "inspection_id", None),
                "request_id": getattr(record, "request_id", None),
            }
        )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "pcb_api_requests",
            "API responses",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "pcb_api_request_duration_seconds",
            "API latency",
            ["method", "route"],
            registry=self.registry,
        )
