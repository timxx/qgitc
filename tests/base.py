# -*- coding: utf-8 -*-
from functools import partial
import logging
import os
import sys
import threading
import unittest
from unittest.mock import patch

from shiboken6 import delete
from PySide6.QtCore import QThread
from qgitc.application import Application
from qgitc.gitutils import Git


_log_inited = False


def _setup_logging():
    global _log_inited
    if _log_inited:
        return

    _log_inited = True
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


def createRepo(dir):
    if not os.path.exists(dir):
        os.makedirs(dir)

    Git.checkOutput(["init", "-bmain"], repoDir=dir)
    Git.checkOutput(["config", "--local", "user.name", "foo"], repoDir=dir)
    Git.checkOutput(["config", "--local", "user.email",
                    "foo@bar.com"], repoDir=dir)

    with open(os.path.join(dir, "README.md"), "w") as f:
        f.write("# Test Submodule Repo\n")

    Git.addFiles(repoDir=dir, files=["README.md"])
    Git.commit("Initial commit", repoDir=dir)

    with open(os.path.join(dir, "test.py"), "w") as f:
        f.write("#!/usr/bin/python3\n")
        f.write("print('Hello, World!')\n")

    Git.addFiles(repoDir=dir, files=["test.py"])
    Git.commit("Add test.py", repoDir=dir)


def addSubmoduleRepo(dir, submoduleDir, subdir):
    Git.checkOutput(["-c", "protocol.file.allow=always",
                    "submodule", "add", submoduleDir, subdir], repoDir=dir)
    Git.commit("Add submodule", repoDir=dir)


_setup_logging()


# see https://github.com/nedbat/coveragepy/issues/686
_original_qthread_init = QThread.__init__


def _run_with_trace(instance):
    if "coverage" in sys.modules:
        sys.settrace(threading._trace_hook)
    instance._base_run()


def _init_with_trace(instance, *args, **kwargs):
    _original_qthread_init(instance, *args, **kwargs)
    instance._base_run = instance.run
    instance.run = partial(_run_with_trace, instance)


class TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(sys.argv, testing=True)

        cls._threadPatcher = patch.object(
            QThread, "__init__", new=_init_with_trace)
        cls._threadPatcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._threadPatcher.stop()
        cls.processEvents(cls)
        cls.app.quit()
        # FIXME: `RuntimeError: Please destroy the Application singleton before creating a new Application instance`
        delete(cls.app)
        del cls.app

    def processEvents(self):
        self.app.sendPostedEvents()
        self.app.processEvents()
