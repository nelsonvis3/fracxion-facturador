"""Process-level checks: a failed worker and SIGTERM must not leave siblings alive."""

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"


class SupervisorTests(unittest.TestCase):
    def run_case(self, child_exits):
        with tempfile.TemporaryDirectory(prefix="fracxion-supervisor-") as directory:
            root = Path(directory)
            sleeper = root / "sleeper.py"
            sleeper.write_text(
                "import os, time\nfrom pathlib import Path\n"
                f"Path({str(root / 'pid')!r}).write_text(str(os.getpid()))\n"
                "time.sleep(60)\n"
            )
            commands = [[sys.executable, str(sleeper)]]
            if child_exits:
                commands.append(
                    [
                        sys.executable,
                        "-c",
                        "import time; time.sleep(0.5); raise SystemExit(2)",
                    ]
                )
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    f"from render_start import supervise; raise SystemExit(supervise({commands!r}))",
                ],
                cwd=BACKEND,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 5
                while not (root / "pid").exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue((root / "pid").exists())
                child_pid = int((root / "pid").read_text())
                if not child_exits:
                    process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(
                    process.returncode, 1 if child_exits else 0, stdout + stderr
                )
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=15)

    def test_child_failure_stops_sibling(self):
        self.run_case(True)

    def test_sigterm_stops_children(self):
        self.run_case(False)


if __name__ == "__main__":
    unittest.main()
