# -*- coding: utf-8 -*-
import logging
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from functools import partial
from unittest.mock import patch

from PySide6.QtCore import (
    QElapsedTimer,
    QMessageLogContext,
    QThread,
    QtMsgType,
    qInstallMessageHandler,
)
from shiboken6 import delete

from qgitc.application import Application
from qgitc.common import logger
from qgitc.gitutils import Git, GitProcess

knownQtWarnings = [
    "This plugin does not support propagateSizeHints()",
    "This plugin does not support raise()",
]


def _qt_message_handler(type: QtMsgType, context: QMessageLogContext, msg: str):
    if type == QtMsgType.QtWarningMsg and msg in knownQtWarnings:
        return

    print(msg)


def _setup_logging():
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.WARNING)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(levelname)s][%(asctime)s]%(filename)s:%(lineno)d - %(message)s")
    handler.setFormatter(formatter)

    rootLogger.addHandler(handler)

    thirdLoggers = ["requests", "urllib3"]
    for name in thirdLoggers:
        logger = logging.getLogger(name)
        if logger:
            logger.setLevel(logging.WARNING)

    qInstallMessageHandler(_qt_message_handler)


def createRepo(dir, url="https://foo.com/bar/test.git"):
    if not os.path.exists(dir):
        os.makedirs(dir)

    Git.checkOutput(["init", "-bmain"], repoDir=dir)
    Git.checkOutput(["config", "--local", "user.name", "foo"], repoDir=dir)
    Git.checkOutput(["config", "--local", "user.email",
                    "foo@bar.com"], repoDir=dir)
    Git.checkOutput(["config", "--local", "remote.origin.url",
                    url], repoDir=dir)

    with open(os.path.join(dir, "README.md"), "w") as f:
        f.write("# Test Submodule Repo\n")

    date = datetime.fromtimestamp(
        datetime.now().timestamp() - 3600).strftime("%Y-%m-%d %H:%M:%S")

    Git.addFiles(repoDir=dir, files=["README.md"])
    Git.commit("Initial commit", repoDir=dir, date=date)

    with open(os.path.join(dir, "test.py"), "w") as f:
        f.write("#!/usr/bin/python3\n")
        f.write("print('Hello, World!')\n")

    date = datetime.fromtimestamp(
        datetime.now().timestamp() - 1800).strftime("%Y-%m-%d %H:%M:%S")
    Git.addFiles(repoDir=dir, files=["test.py"])
    Git.commit("Add test.py", repoDir=dir, date=date)


def addSubmoduleRepo(dir, submoduleDir, subdir):
    Git.checkOutput(["-c", "protocol.file.allow=always",
                    "submodule", "add", submoduleDir, subdir], repoDir=dir)
    Git.commit("Add submodule", repoDir=dir)


class TemporaryDirectory:
    def __init__(self):
        self.name = tempfile.mkdtemp()

    def __repr__(self):
        return "<{} {!r}>".format(self.__class__.__name__, self.name)

    def __enter__(self):
        return self.name

    def __exit__(self, exc, value, tb):
        self.cleanup()

    def cleanup(self):
        def removeReadonly(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        if os.path.exists(self.name):
            if sys.version_info < (3, 12):
                shutil.rmtree(self.name, onerror=removeReadonly)
            else:
                shutil.rmtree(self.name, onexc=removeReadonly)


_setup_logging()


# see https://github.com/nedbat/coveragepy/issues/686
_original_qthread_init = QThread.__init__


def _run_with_trace(instance):
    logger.info("run Thread %s", instance)
    if "coverage" in sys.modules:
        sys.settrace(threading._trace_hook)
    instance._base_run()
    logger.info("finished QThread %s", instance)


def _init_with_trace(instance, *args, **kwargs):
    _original_qthread_init(instance, *args, **kwargs)
    instance._base_run = instance.run
    instance.run = partial(_run_with_trace, instance)
    logger.info("create QThread %s, parent %s", instance, instance.parent())


class TestBase(unittest.TestCase):
    def setUp(self):
        self.oldDir = Git.REPO_DIR or os.getcwd()
        self.gitDir = None
        self.submoduleDir = None
        self.doCreateRepo()

        self.app = Application(sys.argv, testing=True)
        # clear settings to avoid test interference
        self.app.settings().remove("")

        self._threadPatcher = patch.object(
            QThread, "__init__", new=_init_with_trace)
        self._threadPatcher.start()

    def tearDown(self):
        self._threadPatcher.stop()
        self.app.settings().clear()
        self.processEvents()
        self.app.quit()
        # FIXME: `RuntimeError: Please destroy the Application singleton before creating a new Application instance`
        delete(self.app)
        del self.app

        os.chdir(self.oldDir)
        Git.REPO_DIR = self.oldDir

        if self.gitDir:
            time.sleep(0.1)
            self.gitDir.cleanup()
            if self.submoduleDir:
                self.submoduleDir.cleanup()

    def processEvents(self):
        self.app.sendPostedEvents()
        self.app.processEvents()

    def wait(self, timeout: int, condition: callable = None):
        # QTest.qWait is not working as expected in the test
        timer = QElapsedTimer()
        timer.start()
        while timer.elapsed() < timeout and (condition is None or condition()):
            self.processEvents()

    def createSubmodule(self):
        return False

    def createSubRepo(self):
        return False

    def doCreateRepo(self):
        self.gitDir = TemporaryDirectory()
        self.submoduleDir = None
        os.chdir(self.gitDir.name)

        # HACK: do not depend on application
        GitProcess.GIT_BIN = shutil.which("git")

        createRepo(self.gitDir.name)
        if self.createSubmodule():
            self.submoduleDir = TemporaryDirectory()
            createRepo(self.submoduleDir.name,
                       "https://foo.com/bar/submodule.git")
            addSubmoduleRepo(self.gitDir.name,
                             self.submoduleDir.name, "submodule")
        if self.createSubRepo():
            with open(os.path.join(self.gitDir.name, ".gitignore"), "w+") as f:
                f.write("/subRepo/\n")
            Git.addFiles(repoDir=self.gitDir.name, files=[".gitignore"])
            Git.commit("Add .gitignore", repoDir=self.gitDir.name)

            subRepoDir = os.path.join(self.gitDir.name, "subRepo")
            createRepo(subRepoDir, "https://foo.com/bar/subRepo.git")
