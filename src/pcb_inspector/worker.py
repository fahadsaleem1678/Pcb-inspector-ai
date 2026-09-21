import argparse
import io
import logging
import signal
import threading
import time
from collections.abc import Callable
from types import FrameType

from PIL import Image

from pcb_inspector.config import Settings
from pcb_inspector.database import Inspection, make_engine
from pcb_inspector.inference import DemoDetector, Detector, decide
from pcb_inspector.observability import configure_logging
from pcb_inspector.repository import Repository
from pcb_inspector.schemas import Report
from pcb_inspector.storage import ObjectStore, make_store

logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        repository: Repository,
        storage: ObjectStore,
        settings: Settings,
        detector: Detector | None = None,
    ):
        self.repository = repository
        self.storage = storage
        self.settings = settings
        if detector is not None:
            self.detector = detector
        elif settings.detector == "research":
            from pcb_inspector.research_detector import ResearchDetector

            assert settings.research_checkpoint is not None
            self.detector = ResearchDetector(settings.research_checkpoint)
        else:
            self.detector = DemoDetector()

    def run_once(self) -> bool:
        job = self.repository.claim(self.settings)
        if job is None:
            return False
        self.process(job)
        return True

    def process(self, job: Inspection, can_commit: Callable[[], bool] = lambda: True) -> None:
        started = time.perf_counter()
        try:
            with Image.open(io.BytesIO(self.storage.get(job.image_key))) as image:
                image.load()
                predictions = self.detector.predict(image)
                experimental = bool(getattr(self.detector, "is_experimental", False))
                findings, ignored = decide(
                    predictions, image.width, image.height, experimental=experimental
                )
                report = Report(
                    inspection_id=job.id,
                    model_version=self.detector.version,
                    is_demo=self.detector.is_demo,
                    is_experimental=experimental,
                    decision_policy_version=(
                        "portfolio-display-0.25-v1" if experimental else "provisional-1"
                    ),
                    overall_result=(
                        "NOT_EVALUATED"
                        if self.detector.is_demo
                        else "REVIEW_REQUIRED"
                        if findings
                        else "NO_VISIBLE_DEFECTS_DETECTED"
                    ),
                    inference_time_ms=round((time.perf_counter() - started) * 1000),
                    image_width=image.width,
                    image_height=image.height,
                    detections=findings,
                    ignored_detection_count=ignored,
                    limitations=[
                        "AI-assisted visual inspection only; "
                        "no electrical or functional certification.",
                        "Experimental trained model; unreviewed labels. AP50 45.97% on 256 "
                        "public validation images, not an accuracy percentage. Display threshold "
                        "0.25 is uncalibrated. No PCB/quality classifier "
                        "or board acceptance decision."
                        if experimental
                        else "Demo mode: no trained model or PCB/quality classifier was run."
                        if self.detector.is_demo
                        else "Decision thresholds are provisional; calibration is required.",
                    ],
                )
            committed = can_commit() and self.repository.complete(job, report)
            logger.info(
                "inspection_completed" if committed else "stale_result_discarded",
                extra={"inspection_id": job.id},
            )
        except Exception as exc:
            # Expose only a stable error code to clients, not paths or credentials.
            logger.error("inference_error:%s", type(exc).__name__, extra={"inspection_id": job.id})
            if can_commit():
                self.repository.fail(job, self.settings)


def main() -> None:
    parser = argparse.ArgumentParser(description="PCB inspection worker (local demo)")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    args = parser.parse_args()
    configure_logging()
    settings = Settings()
    engine = make_engine(settings.database_url)
    worker = Worker(Repository(engine), make_store(settings), settings)
    run_once = worker.run_once
    if settings.queue_backend == "sqs":
        from pcb_inspector.queue import SQSQueue
        from pcb_inspector.sqs_worker import SQSWorker

        queue = SQSQueue.from_settings(settings)
        queue.validate()
        run_once = SQSWorker(worker, queue).run_once
    stopped = threading.Event()

    def stop(signum: int, frame: FrameType | None) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        if args.once:
            run_once()
            return
        logger.info("worker_started:%s", settings.detector)
        while not stopped.is_set():
            try:
                busy = run_once()
            except Exception as exc:
                logger.error("worker_poll_error:%s", type(exc).__name__)
                busy = False
            if not busy:
                stopped.wait(settings.worker_poll_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
