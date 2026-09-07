"""Run the local API, demo worker and React development server together."""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

from processes import stop_process

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=5173)
    parser.add_argument("--stop", action="store_true", help="Stop this local port pair")
    args = parser.parse_args()
    stop_file = ROOT / ".runtime" / f"dev-{args.api_port}-{args.web_port}.stop"
    stop_file.parent.mkdir(exist_ok=True)
    if args.stop:
        stop_file.touch()
        print("Stop requested for the local development services.")
        return
    stop_file.unlink(missing_ok=True)
    node = shutil.which("node")
    vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite.is_file():
        parser.error("Install Node.js and run pnpm install in frontend/ first.")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True, timeout=30
    )
    env = os.environ.copy()
    env["PCB_API_PROXY"] = f"http://127.0.0.1:{args.api_port}"
    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    processes = []
    try:
        for command, directory in [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "pcb_inspector.api:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.api_port),
                ],
                ROOT,
            ),
            ([sys.executable, "-m", "pcb_inspector.worker"], ROOT),
            (
                [
                    node,
                    str(vite),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.web_port),
                    "--strictPort",
                ],
                ROOT / "frontend",
            ),
        ]:
            processes.append(subprocess.Popen(command, cwd=directory, env=env, **kwargs))
        print(
            f"PCB workspace: http://127.0.0.1:{args.web_port} — Ctrl+C stops all services.",
            flush=True,
        )
        while not stopped.wait(0.5):
            if stop_file.exists():
                break
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("A development service stopped; see its logs above.")
    finally:
        for process in processes:
            stop_process(process)
        stop_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
