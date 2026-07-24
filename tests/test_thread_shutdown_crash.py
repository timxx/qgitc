# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import textwrap
import unittest


class TestThreadShutdownCrash(unittest.TestCase):

    def _runChild(self, script):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        return subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", textwrap.dedent(script)],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def _assertChildSucceeded(self, result):
        self.assertEqual(
            result.returncode,
            0,
            f"child process crashed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_terminate_thread_shuts_down_cooperatively(self):
        result = self._runChild(
            """
            import os
            import time

            os.environ["QT_QPA_PLATFORM"] = "offscreen"

            from PySide6.QtCore import QThread
            from qgitc.application import Application


            class SlowCooperativeThread(QThread):
                def run(self):
                    while not self.isInterruptionRequested():
                        self.msleep(1)
                    # Keep Python on the thread briefly after acknowledging
                    # interruption. QThread.terminate() here would corrupt the
                    # interpreter and later exit with 0xC0000005 on Windows.
                    time.sleep(0.05)


            app = Application([], testing=True)
            thread = SlowCooperativeThread()
            thread.start()
            while not thread.isRunning():
                app.processEvents()

            # A zero budget forces the orphan path: the thread must NOT be killed,
            # ownership is transferred to the application for async cleanup.
            orphaned = app.terminateThread(thread, waitTime=0)
            if not orphaned:
                raise AssertionError("expected still-running thread to be orphaned")

            # The orphaned thread finishes its Python cooperatively.
            deadline = time.monotonic() + 5
            while thread.isRunning() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.001)
            if thread.isRunning():
                raise AssertionError("orphaned thread did not finish cooperatively")

            app.aboutToQuit.emit()
            app.quit()
            """
        )
        self._assertChildSucceeded(result)
        output = result.stdout + result.stderr
        self.assertNotIn("QBasicTimer::stop: Failed", output)
        self.assertNotIn("QObject::killTimer", output)
        self.assertNotIn("QThreadStorage:", output)

    def test_orphaned_thread_awaited_at_exit(self):
        result = self._runChild(
            """
            import os
            import time

            os.environ["QT_QPA_PLATFORM"] = "offscreen"

            from PySide6.QtCore import QThread
            from qgitc.application import Application
            from shiboken6 import delete


            class BusyThread(QThread):
                def run(self):
                    # Ignores interruption for a while, mimicking a worker stuck
                    # in a long CPU-bound parse that cannot be force-killed.
                    time.sleep(0.3)


            app = Application([], testing=True)
            thread = BusyThread()
            thread.start()
            while not thread.isRunning():
                app.processEvents()

            if not app.terminateThread(thread, waitTime=0):
                raise AssertionError("expected the busy thread to be orphaned")

            # Exit must drain orphaned threads so the interpreter is not torn
            # down while a thread is still executing Python.
            app.aboutToQuit.emit()
            if thread.isRunning():
                raise AssertionError("orphaned thread still running after exit drain")

            app.quit()
            delete(app)
            """
        )
        self._assertChildSucceeded(result)
        output = result.stdout + result.stderr
        self.assertNotIn("QBasicTimer::stop: Failed", output)
        self.assertNotIn("QObject::killTimer", output)
        self.assertNotIn("QThreadStorage:", output)

    def test_blame_show_commit_survives_log_worker_shutdown(self):
        result = self._runChild(
            """
            import gc
            import os
            import threading
            import time

            os.environ["QT_QPA_PLATFORM"] = "offscreen"

            from PySide6.QtCore import QBasicTimer, QObject
            from qgitc.application import Application
            from qgitc.logsfetcherimpl import LogsFetcherImpl
            from qgitc.windowtype import WindowType
            from shiboken6 import delete


            app = Application([], testing=True)
            oldThresholds = gc.get_threshold()
            gc.set_threshold(1, 1, 1)

            class TimedCycle(QObject):
                def __init__(self):
                    super().__init__()
                    self.timer = QBasicTimer()
                    self.timer.start(1000, self)
                    self.cycle = self

            timed = TimedCycle()
            del timed

            blameWindow = app.getWindow(WindowType.BlameWindow)
            blameWindow.blame("qgitc/datafetcher.py", repoDir=os.getcwd())

            deadline = time.monotonic() + 5
            viewer = blameWindow._view.viewer
            while not viewer.panel.revisions and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.001)
            if not viewer.panel.revisions:
                raise AssertionError("blame data did not load")

            blameLog = blameWindow._view.commitPanel.logView
            while blameLog.fetcher.isLoading() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.001)

            parseEntered = threading.Event()
            originalParse = LogsFetcherImpl.parse

            def slowParse(self, data):
                parseEntered.set()
                deadline = time.monotonic() + 5
                value = 0
                while time.monotonic() < deadline:
                    value += 1
                return originalParse(self, data)

            LogsFetcherImpl.parse = slowParse
            originalTerminateThread = app.terminateThread
            terminateCalls = []

            def terminateImmediately(thread, waitTime=3000):
                terminateCalls.append(thread)
                return originalTerminateThread(thread, waitTime=0)

            app.terminateThread = terminateImmediately

            # Exercise the real blame context-menu action and posted event.
            viewer._curIndexForMenu = 0
            viewer._onMenuShowCommitLog()
            while app._logWindow is None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.001)
            while not parseEntered.is_set() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.001)
            if not parseEntered.is_set():
                raise AssertionError("log worker did not enter parse")
            logFetcher = app._logWindow.ui.gitViewA.logView.fetcher
            if not logFetcher.isLoading():
                raise AssertionError("menu-triggered log worker already stopped")

            # Closing the log window follows LogView.queryClose() ->
            # LogsFetcher.cancel(True), the lifecycle that used to force-kill
            # Python while the menu-triggered worker was still executing.
            app._logWindow.close()
            app.processEvents()
            if not terminateCalls:
                raise AssertionError("log window close did not enter terminateThread")
            blameWindow.close()
            gc.set_threshold(*oldThresholds)
            gc.collect()
            app.aboutToQuit.emit()
            app.quit()
            delete(app)
            """
        )
        self._assertChildSucceeded(result)
        output = result.stdout + result.stderr
        self.assertNotIn("QBasicTimer::stop: Failed", output)
        self.assertNotIn("QObject::killTimer", output)
        self.assertNotIn("QThreadStorage:", output)


if __name__ == "__main__":
    unittest.main()
