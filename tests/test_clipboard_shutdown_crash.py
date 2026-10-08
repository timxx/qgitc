# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import textwrap
import unittest


class TestClipboardShutdownCrash(unittest.TestCase):
    """The clipboard must not be handed a Python-created QMimeData.

    QClipboard takes ownership of the QMimeData passed to setMimeData(), and
    Qt's exit-time cleanup then destroys its Python wrapper — by which point
    the interpreter is gone, so the process segfaults on exit. That only shows
    up in the process return code, hence the child process.
    """

    def _runChild(self, script):
        repoRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        # the child chdirs out of the repository (so no submodule scan runs)
        # but must still import the checked out qgitc
        env["PYTHONPATH"] = repoRoot + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c",
             textwrap.dedent(script)],
            cwd=repoRoot,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _assertChildSucceeded(self, result, expected):
        self.assertEqual(
            result.returncode,
            0,
            f"child process crashed:\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}",
        )
        self.assertIn(expected, result.stdout)

    def testTextViewerCopySurvivesShutdown(self):
        """Copying the selection must leave an exit code of 0."""
        result = self._runChild(
            """
            import os
            import tempfile

            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            os.chdir(tempfile.mkdtemp())

            from shiboken6 import delete

            from qgitc.application import Application
            from qgitc.textviewer import TextViewer

            app = Application([], testing=True)
            viewer = TextViewer()
            viewer.resize(300, 200)
            viewer.appendLines(["line %d" % i for i in range(5)])
            app.processEvents()

            viewer.selectAll()
            viewer.copy()
            print("copied: %r" % app.clipboard().text(), flush=True)

            # what every TestBase test does, and what used to crash on exit
            delete(app)
            """
        )

        self._assertChildSucceeded(result, "line 4")

    def testLogViewCopyAbbrevCommitSurvivesShutdown(self):
        """The 'Copy abbrev commit' action must leave an exit code of 0."""
        result = self._runChild(
            """
            import os
            import tempfile
            import types

            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            os.chdir(tempfile.mkdtemp())

            from shiboken6 import delete

            import qgitc.logview as logview
            from qgitc.application import Application
            from qgitc.logview import LogView

            class StubProgress:
                def setValue(self, value):
                    pass

                def wasCanceled(self):
                    return False

            app = Application([], testing=True)
            view = LogView()
            view.curIdx = 0
            view.getSelectedCommits = lambda: [
                types.SimpleNamespace(sha1="a" * 40)]
            logview.Git.abbrevCommit = staticmethod(lambda sha1: "abc1234")
            view._createProgressDialog = lambda title, count: StubProgress()

            # only the action is needed, not the modal context menu
            view._LogView__ensureContextMenu()
            view.acCopyAbbrevCommit.trigger()
            print("copied: %r" % app.clipboard().text(), flush=True)

            delete(app)
            """
        )

        self._assertChildSucceeded(result, "abc1234")


if __name__ == "__main__":
    unittest.main()
