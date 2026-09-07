"""Stop only child processes launched by this project's development/test scripts."""

import subprocess
import sys


def stop_process(process):
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        # The venv launcher can have a separate interpreter child. Stop that owned tree too.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
