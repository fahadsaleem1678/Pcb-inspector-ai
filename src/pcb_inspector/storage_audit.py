"""Read-only orphan candidates. Never deletes objects or changes inspection records."""

import argparse
import json
import math
import time
from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pcb_inspector.config import Settings
from pcb_inspector.database import Inspection, make_engine
from pcb_inspector.storage import LocalObjectStore, S3ObjectStore, make_store


def inventory(store: LocalObjectStore | S3ObjectStore) -> Iterator[tuple[str, float]]:
    if isinstance(store, LocalObjectStore):
        for path in store.root.joinpath("uploads").glob("*/original.png"):
            yield path.relative_to(store.root).as_posix(), path.stat().st_mtime
        return
    prefix = store.prefix + "/"
    pages = store.client.get_paginator("list_objects_v2").paginate(
        Bucket=store.bucket,
        Prefix=prefix + "uploads/",
    )
    for page in pages:
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.startswith(prefix):
                yield key[len(prefix) :], item["LastModified"].timestamp()


def audit(
    engine: Engine,
    objects: Iterable[tuple[str, float]],
    *,
    min_age_seconds: float = 86400,
    now: float | None = None,
) -> dict[str, Any]:
    if not math.isfinite(min_age_seconds) or min_age_seconds <= 0:
        raise ValueError("Orphan audit requires a positive age grace period")
    now = time.time() if now is None else now
    candidates = []
    scanned = 0
    with Session(engine) as session:
        for key, modified in objects:
            scanned += 1
            if modified > now - min_age_seconds:
                continue
            referenced = session.scalar(
                select(Inspection.id).where(Inspection.image_key == key).limit(1)
            )
            if referenced is None:
                candidates.append({"image_key": key, "modified_at": modified})
    return {
        "schema_version": "1.0",
        "read_only": True,
        "scanned": scanned,
        "min_age_seconds": min_age_seconds,
        "candidates": candidates,
        "deletion_approved": False,
        "limitation": "Concurrent uploads/commits may change references. "
        "Pause submissions and recheck before any separately approved cleanup.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List old unreferenced upload candidates; no deletion"
    )
    parser.add_argument("--min-age-hours", type=float, default=24)
    args = parser.parse_args()
    settings = Settings()
    engine = make_engine(settings.database_url)
    try:
        store = make_store(settings)
        if not isinstance(store, LocalObjectStore | S3ObjectStore):
            raise TypeError("Unsupported inventory store")
        print(
            json.dumps(
                audit(engine, inventory(store), min_age_seconds=args.min_age_hours * 3600), indent=2
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
