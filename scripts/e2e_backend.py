"""Isolated backend for browser tests; never touches the developer database."""

import os
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw
from processes import stop_process

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    runtime = (ROOT / ".runtime").resolve()
    runtime.mkdir(exist_ok=True)
    # The image is a generated test fixture, not a dataset or detector benchmark.
    fixture = runtime / "e2e-fixtures" / "board.png"
    fixture.parent.mkdir(exist_ok=True)
    image = Image.new("RGB", (640, 400), "#284b37")
    draw = ImageDraw.Draw(image)
    for y in range(45, 375, 25):
        draw.line([(20, y), (600, y), (615, y - 15)], fill="#91aa6b", width=2)
    for x in range(60, 610, 75):
        draw.rectangle((x, 75, x + 40, 130), fill="#c4c1a9", outline="#243b27", width=3)
        draw.rectangle((x, 240, x + 40, 285), fill="#252b25", outline="#aeb99c", width=2)
    draw.rectangle((230, 150, 400, 235), fill="#161e18", outline="#ced0b0", width=3)
    image.save(fixture)
    with tempfile.TemporaryDirectory(prefix="browser-", dir=runtime) as directory:
        temporary = Path(directory).resolve()
        assert temporary.is_relative_to(runtime)
        env = os.environ.copy()
        env.update(
            {
                "PCB_DATABASE_URL": f"sqlite:///{temporary / 'test.db'}",
                "PCB_STORAGE_PATH": str(temporary / "objects"),
                "PCB_ENVIRONMENT": "test",
                "PCB_DETECTOR": "demo",
                "PCB_AUTH_MODE": "local",
                "PCB_WORKER_POLL_SECONDS": "0.3",
            }
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True
        )
        stopped = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
        signal.signal(signal.SIGINT, lambda *_: stopped.set())
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        processes = []
        try:
            for command in [
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "pcb_inspector.api:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8011",
                ],
                [sys.executable, "-m", "pcb_inspector.worker"],
            ]:
                processes.append(subprocess.Popen(command, cwd=ROOT, env=env, **kwargs))
            while not stopped.wait(0.5):
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError("A browser-test backend process stopped")
        finally:
            for process in processes:
                stop_process(process)


if __name__ == "__main__":
    main()
