# -*- coding: utf-8 -*-
import logging
import os
import subprocess
from shiboken6 import delete
from qgitc.application import Application

import sys
import unittest


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

    subprocess.check_output(["git", "init", "-bmain", dir])
    subprocess.check_call(
        ["git", "config", "--local", "user.name", "foo"], cwd=dir)
    subprocess.check_call(
        ["git", "config", "--local", "user.email", "foo@bar.com"], cwd=dir)

    with open(os.path.join(dir, "README.md"), "w") as f:
        f.write("# Test Submodule Repo\n")
    subprocess.check_output(["git", "add", "README.md"], cwd=dir)
    subprocess.check_output(["git", "commit", "-m", "Initial commit"], cwd=dir)

    with open(os.path.join(dir, "test.py"), "w") as f:
        f.write("#!/usr/bin/python3\n")
        f.write("print('Hello, World!')\n")

    subprocess.check_output(["git", "add", "test.py"], cwd=dir)
    subprocess.check_output(["git", "commit", "-m", "Add test.py"], cwd=dir)


def addSubmoduleRepo(dir, submoduleDir, subdir):
    subprocess.check_output(["git", "-c", "protocol.file.allow=always",
                            "submodule", "add", submoduleDir, subdir], cwd=dir, stderr=subprocess.DEVNULL)
    subprocess.check_output(["git", "commit", "-m", "Add submodule"], cwd=dir)


_setup_logging()


class TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(sys.argv, testing=True)

    @classmethod
    def tearDownClass(cls):
        cls.processEvents(cls)
        cls.app.quit()
        # FIXME: `RuntimeError: Please destroy the Application singleton before creating a new Application instance`
        delete(cls.app)
        del cls.app

    def processEvents(self):
        self.app.sendPostedEvents()
        self.app.processEvents()
