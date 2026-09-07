import argparse
import io
import logging
import signal
import threading
import time
from types import FrameType

from PIL import Image

from pcb_inspector.config import Settings
from pcb_inspector.database import make_engine
from pcb_inspector.inference import DemoDetector, Detector, decide
from pcb_inspector.observability import configure_logging
from pcb_inspector.repository import Repository
from pcb_inspector.schemas import Report
from pcb_inspector.storage import LocalObjectStore, ObjectStore

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
        self.detector = detector if detector is not None else DemoDetector()

    def run_once(self) -> bool:
        job = self.repository.claim(self.settings)
        if job is None:
            return False
        started = time.perf_counter()
        try:
            with Image.open(io.BytesIO(self.storage.get(job.image_key))) as image:
                image.load()
                predictions = self.detector.predict(image)
                findings, ignored = decide(predictions, image.width, image.height)
                report = Report(
                    inspection_id=job.id,
                    model_version=self.detector.version,
                    is_demo=self.detector.is_demo,
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
                        "Demo mode: no trained model or PCB/quality classifier was run."
                        if self.detector.is_demo
                        else "Decision thresholds are provisional; calibration is required.",
                    ],
                )
            committed = self.repository.complete(job, report)
            logger.info(
                "inspection_completed" if committed else "stale_result_discarded",
                extra={"inspection_id": job.id},
            )
        except Exception as exc:
            # Expose only a stable error code to clients, not paths or credentials.
            logger.error("inference_error:%s", type(exc).__name__, extra={"inspection_id": job.id})
            self.repository.fail(job, self.settings)
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="PCB inspection worker (local demo)")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    args = parser.parse_args()
    configure_logging()
    settings = Settings()
    engine = make_engine(settings.database_url)
    worker = Worker(Repository(engine), LocalObjectStore(settings.storage_path), settings)
    stopped = threading.Event()

    def stop(signum: int, frame: FrameType | None) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        if args.once:
            worker.run_once()
            return
        logger.info("worker_started_demo_mode")
        while not stopped.is_set():
            try:
                busy = worker.run_once()
            except Exception as exc:
                logger.error("worker_poll_error:%s", type(exc).__name__)
                busy = False
            if not busy:
                stopped.wait(settings.worker_poll_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
