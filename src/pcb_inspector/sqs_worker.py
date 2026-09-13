"""SQS deliveries wake a database-fenced worker; only durable completion permits ACK."""

import logging
import math
import threading
import time

from pcb_inspector.database import Inspection
from pcb_inspector.queue import Delivery, SQSQueue
from pcb_inspector.schemas import Status
from pcb_inspector.worker import Worker

logger = logging.getLogger(__name__)


class Heartbeat:
    def __init__(self, worker: Worker, queue: SQSQueue, delivery: Delivery, job: Inspection):
        self.worker, self.queue, self.delivery, self.job = worker, queue, delivery, job
        self.stopped = threading.Event()
        self.lost = threading.Event()
        self.interval = (
            min(worker.settings.lease_seconds, queue.settings.sqs_visibility_seconds) / 3
        )
        self.thread = threading.Thread(target=self.run, daemon=True, name="sqs-lease-renewal")

    def pulse(self) -> bool:
        try:
            if not self.worker.repository.renew(self.job, self.worker.settings):
                event_id, inspection_id = self.delivery.identities()
                state = self.worker.repository.message_job(event_id, inspection_id)
                if state is not None and state.status in (Status.COMPLETED, Status.FAILED):
                    return False  # A committed terminal transition naturally retires its lease.
                raise RuntimeError("Database lease lost")
            self.queue.renew(self.delivery)
            return True
        except Exception as exc:
            self.lost.set()
            logger.error(
                "worker_lease_lost:%s", type(exc).__name__, extra={"inspection_id": self.job.id}
            )
            return False

    def run(self) -> None:
        while not self.stopped.wait(self.interval):
            if not self.pulse():
                return

    def close(self) -> None:
        self.stopped.set()
        self.thread.join()


class SQSWorker:
    def __init__(self, worker: Worker, queue: SQSQueue):
        self.worker, self.queue = worker, queue

    def run_once(self) -> bool:
        delivery = self.queue.receive()
        if delivery is None:
            return False
        try:
            event_id, inspection_id = delivery.identities()
        except (ValueError, TypeError, AttributeError):
            logger.error("invalid_queue_event")
            return True  # Native SQS redrive quarantines poison events; never ACK them.
        repository = self.worker.repository
        state = repository.message_job(event_id, inspection_id)
        if state is None:
            logger.error("unknown_queue_event")
            return True
        if state.status == Status.COMPLETED:
            self.queue.delete(delivery)
            return True
        if state.status == Status.FAILED:
            return True  # Retain failed jobs for native DLQ redrive.
        job = repository.claim(self.worker.settings, inspection_id=inspection_id)
        if job is None:
            # A duplicate may arrive while the original worker holds the lease. Do not ACK:
            # the first worker could crash before committing a result.
            return True
        heartbeat = Heartbeat(self.worker, self.queue, delivery, job)
        if not heartbeat.pulse():
            return True
        heartbeat.thread.start()
        try:
            self.worker.process(job, can_commit=lambda: not heartbeat.lost.is_set())
        finally:
            heartbeat.close()
        state = repository.message_job(event_id, inspection_id)
        if state is not None and state.status == Status.COMPLETED:
            self.queue.delete(delivery)
        elif not heartbeat.lost.is_set() and state is not None and state.status == Status.QUEUED:
            delay = max(1, min(43200, math.ceil(state.available_at - time.time())))
            self.queue.renew(delivery, delay)
        return True
