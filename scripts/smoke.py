"""Exercise separate HTTP API and worker processes with isolated local storage."""

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image
from processes import stop_process

ROOT = Path(__file__).resolve().parents[1]


def run() -> None:
    runtime = (ROOT / ".runtime").resolve()
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="smoke-", dir=runtime) as directory:
        temporary = Path(directory).resolve()
        assert temporary.is_relative_to(runtime)
        env = os.environ.copy()
        env.update(
            {
                "PCB_ENVIRONMENT": "test",
                "PCB_DETECTOR": "demo",
                "PCB_AUTH_MODE": "local",
                "PCB_DATABASE_URL": env.get(
                    "PCB_SMOKE_DATABASE_URL", f"sqlite:///{temporary / 'db.sqlite'}"
                ),
                "PCB_STORAGE_PATH": str(temporary / "objects"),
                "PCB_LOCAL_USER_ID": temporary.name,
            }
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=30,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "pcb_inspector.api:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        output = io.BytesIO()
        Image.new("RGB", (128, 96), (24, 96, 64)).save(output, "PNG")

        def start(log):
            return subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                **kwargs,
            )

        def ready(client, process):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Smoke API process exited unexpectedly")
                try:
                    if client.get("/ready").status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            raise RuntimeError("Smoke API did not become ready")

        with (temporary / "api.log").open("w") as log:
            process = start(log)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                    ready(client, process)
                    response = client.post(
                        "/api/v1/inspections/upload",
                        files={"file": ("smoke.png", output.getvalue(), "image/png")},
                    )
                    response.raise_for_status()
                    assert response.status_code == 202
                    job_id = response.json()["inspection_id"]
                    path = f"/api/v1/inspections/{job_id}"
                    assert client.get(path).json()["status"] == "QUEUED"
                    subprocess.run(
                        [sys.executable, "-m", "pcb_inspector.worker", "--once"],
                        cwd=ROOT,
                        env=env,
                        check=True,
                        timeout=30,
                        **kwargs,
                    )
                    assert client.get(path).json()["status"] == "COMPLETED"
                    report = client.get(path + "/report").json()
                    assert report["is_demo"] and report["overall_result"] == "NOT_EVALUATED"
                    stop_process(process)
                    try:
                        httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
                    except httpx.HTTPError:
                        pass
                    else:
                        raise AssertionError("Stopped API still accepts connections")
                    process = start(log)
                    ready(client, process)
                    assert client.get(path + "/results").json() == report
                    assert client.get(path + "/image").status_code == 200
                    summary = {
                        "status": "passed",
                        "separate_processes": True,
                        "restart_persistence": True,
                        "report": report,
                    }
                    (runtime / "last-smoke-result.json").write_text(
                        json.dumps(summary, indent=2),
                        encoding="utf-8",
                    )
                    print(
                        "PASS: HTTP upload -> separate worker -> report -> API restart persistence"
                    )
            except Exception:
                log.flush()
                print((temporary / "api.log").read_text(encoding="utf-8"))
                raise
            finally:
                stop_process(process)


if __name__ == "__main__":
    run()
