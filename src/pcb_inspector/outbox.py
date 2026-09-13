"""Leased, at-least-once publication of committed submission events."""

import argparse
import logging
import signal
import threading
import time
from types import FrameType
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pcb_inspector.config import Settings
from pcb_inspector.database import Inspection, SubmissionOutbox, make_engine
from pcb_inspector.observability import configure_logging
from pcb_inspector.queue import SQSQueue
from pcb_inspector.repository import Repository
from pcb_inspector.schemas import Status

logger = logging.getLogger(__name__)


class Outbox:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.settings = settings

    def claim(self, now: float | None = None) -> SubmissionOutbox | None:
        now = time.time() if now is None else now
        eligible = (
            SubmissionOutbox.published_at.is_(None),
            SubmissionOutbox.available_at <= now,
            or_(SubmissionOutbox.lease_until.is_(None), SubmissionOutbox.lease_until <= now),
        )
        for _ in range(10):
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                event_id = session.scalar(
                    select(SubmissionOutbox.id)
                    .where(*eligible)
                    .order_by(SubmissionOutbox.created_at)
                    .limit(1)
                )
                if event_id is None:
                    return None
                event = session.scalar(
                    update(SubmissionOutbox)
                    .where(
                        SubmissionOutbox.id == event_id,
                        *eligible,
                    )
                    .values(
                        lease_token=str(uuid4()),
                        lease_until=now + self.settings.outbox_lease_seconds,
                        attempts=SubmissionOutbox.attempts + 1,
                    )
                    .returning(SubmissionOutbox)
                )
                if event is not None:
                    return event
        return None

    def finish(self, event: SubmissionOutbox, *, published: bool, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with Session(self.engine) as session, session.begin():
            return (
                session.scalar(
                    update(SubmissionOutbox)
                    .where(
                        SubmissionOutbox.id == event.id,
                        SubmissionOutbox.published_at.is_(None),
                        SubmissionOutbox.lease_token == event.lease_token,
                        SubmissionOutbox.lease_until > now,
                    )
                    .values(
                        published_at=now if published else None,
                        available_at=now
                        if published
                        else now + min(300, 2 ** min(event.attempts, 8)),
                        lease_token=None,
                        lease_until=None,
                    )
                    .returning(SubmissionOutbox.id)
                )
                is not None
            )

    def redrive(self, inspection_id: str, now: float | None = None) -> bool:
        """Explicit operator retry, never an automatic response to poison/terminal messages."""
        now = time.time() if now is None else now
        with Session(self.engine) as session, session.begin():
            changed = session.scalar(
                update(Inspection)
                .where(
                    Inspection.id == inspection_id,
                    Inspection.queue_backend == "sqs",
                    Inspection.status == Status.FAILED,
                )
                .values(
                    status=Status.QUEUED,
                    attempts=0,
                    available_at=now,
                    completed_at=None,
                    error_code=None,
                    lease_token=None,
                    lease_until=None,
                )
                .returning(Inspection.id)
            )
            if changed is None:
                return False
            event_id = session.scalar(
                update(SubmissionOutbox)
                .where(
                    SubmissionOutbox.inspection_id == inspection_id,
                )
                .values(
                    published_at=None,
                    available_at=now,
                    lease_token=None,
                    lease_until=None,
                )
                .returning(SubmissionOutbox.id)
            )
            if event_id is None:
                raise ValueError("Failed SQS job has no outbox event")
            Repository._event(
                session, inspection_id, "inspection_redrive_requested", now, event_id=event_id
            )
            return True


class Publisher:
    def __init__(self, outbox: Outbox, queue: SQSQueue):
        self.outbox = outbox
        self.queue = queue

    def run_once(self) -> bool:
        event = self.outbox.claim()
        if event is None:
            return False
        try:
            self.queue.send(event.id, event.inspection_id)
        except Exception as exc:
            logger.error("outbox_send_error:%s", type(exc).__name__)
            self.outbox.finish(event, published=False)
            return True
        # A crash or lost commit acknowledgement here causes the same event to be resent.
        # The consumer checks database state and lease ownership before processing it.
        self.outbox.finish(event, published=True)
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish pending PCB submission events")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument(
        "--redrive",
        type=UUID,
        metavar="INSPECTION_ID",
        help="Explicitly requeue one failed SQS job and record an audit event",
    )
    args = parser.parse_args()
    settings = Settings()
    if settings.queue_backend != "sqs":
        parser.error("Outbox publisher requires PCB_QUEUE_BACKEND=sqs")
    configure_logging()
    if args.redrive:
        engine = make_engine(settings.database_url)
        try:
            if not Outbox(engine, settings).redrive(str(args.redrive)):
                parser.error("Inspection is not a failed SQS job")
            print("Retry recorded; run the outbox publisher to deliver it.")
        finally:
            engine.dispose()
        return
    queue = SQSQueue.from_settings(settings)
    queue.validate()
    engine = make_engine(settings.database_url)
    publisher = Publisher(Outbox(engine, settings), queue)
    stopped = threading.Event()

    def stop(signum: int, frame: FrameType | None) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        if args.once:
            publisher.run_once()
            return
        while not stopped.is_set():
            try:
                busy = publisher.run_once()
            except Exception as exc:
                logger.error("outbox_poll_error:%s", type(exc).__name__)
                busy = False
            if not busy:
                stopped.wait(settings.worker_poll_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
