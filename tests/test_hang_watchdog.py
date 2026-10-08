# -*- coding: utf-8 -*-
"""TestBase's watchdog must survive a freeze no Python thread can escape."""

import os
import subprocess
import sys
import textwrap
import time
import unittest


class TestHangWatchdog(unittest.TestCase):
    """A GIL-bound deadlock must still fail the run, with a stack dump.

    The threading.Timer watchdog is a Python thread: once a deadlock keeps the
    GIL busy (a worker thread destroying a QObject holds a Qt lock while
    waiting for the GIL, while the GUI thread holds the GIL and waits for that
    lock) the timer can never fire and the suite hangs silently until the CI
    job times out. faulthandler's watchdog is a C thread and still reports.
    """

    def _runChild(self, script, timeout):
        repoRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONPATH"] = repoRoot + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            cwd=repoRoot,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def testWatchdogFiresWhileNoPythonThreadCanRun(self):
        started = time.time()
        try:
            result = self._runChild(
                """
                import ctypes
                import os
                import sys
                import tempfile
                import unittest

                os.environ["QT_QPA_PLATFORM"] = "offscreen"
                os.chdir(tempfile.mkdtemp())

                from tests.base import TestBase

                class TestHoldsTheGil(TestBase):
                    TEST_TIMEOUT_SECONDS = 3

                    def doCreateRepo(self):
                        pass

                    def testHoldTheGil(self):
                        print("HOLDING-GIL", flush=True)
                        # PyDLL does not release the GIL, so no Python
                        # thread — the threading.Timer watchdog included —
                        # can run until this returns
                        if sys.platform == "win32":
                            ctypes.PyDLL("kernel32").Sleep(60000)
                        else:
                            ctypes.PyDLL(None).sleep(60)

                unittest.main(argv=[sys.argv[0]], exit=False)
                """,
                timeout=25,
            )
        except subprocess.TimeoutExpired:
            self.fail("the watchdog did not fire: the child stayed frozen")

        elapsed = time.time() - started
        self.assertIn("HOLDING-GIL", result.stdout)
        self.assertEqual(
            result.returncode,
            1,
            f"child did not exit through the watchdog:\nstdout:\n"
            f"{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn("Timeout (", result.stderr)
        # the Python-level watchdog cannot run while the GIL is held
        self.assertNotIn("TEST TIMEOUT", result.stderr)
        # and the run must not have waited for the 60s GIL hold
        self.assertLess(elapsed, 20)


if __name__ == "__main__":
    unittest.main()
