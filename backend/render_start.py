"""Supervise the API and one job runner in a single free Render instance.

Both stop when Render suspends the service. This is not an always-on scheduler.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def supervise(commands):
    processes = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for command in commands:
            if stopping:
                return 0
            processes.append(subprocess.Popen(command, cwd=ROOT, start_new_session=True))
        while not stopping:
            for process in processes:
                if process.poll() is not None:
                    # Even a clean unexpected child exit must restart the service.
                    print("A required service process exited; stopping the instance.", flush=True)
                    return 1
            time.sleep(0.25)
        return 0
    finally:
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 10
        for process in processes:
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        # Include grandchildren, such as an export being rendered by execute_job.
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    if os.getenv("DJANGO_SETTINGS_MODULE") != "config.render_settings":
        raise SystemExit("Render startup requires DJANGO_SETTINGS_MODULE=config.render_settings.")
    # Free services have no pre-deploy command. Migrations must succeed before
    # either long-running process starts. Deploy manually after reviewing them.
    for arguments in (["check"], ["migrate", "--noinput"], ["collectstatic", "--noinput"]):
        subprocess.run([sys.executable, "manage.py", *arguments], cwd=ROOT, check=True)
    port = int(os.getenv("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise SystemExit("Invalid PORT.")
    return supervise(
        [
            [
                sys.executable,
                "-m",
                "gunicorn",
                "config.wsgi:application",
                "--bind",
                f"0.0.0.0:{port}",
                "--workers",
                "1",
                "--threads",
                "2",
                "--timeout",
                "60",
                "--graceful-timeout",
                "8",
                "--max-requests",
                "300",
                "--max-requests-jitter",
                "30",
                "--error-logfile",
                "-",
            ],
            [sys.executable, "manage.py", "run_jobs"],
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
