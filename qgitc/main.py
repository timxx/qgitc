# -*- coding: utf-8 -*-

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QStyle,
    QMessageBox)

from .gitutils import Git
from .excepthandler import ExceptHandler
from .application import Application
from .mainwindow import MainWindow
from .blameview import BlameWindow

import os
import sys
import argparse


def setAppUserId(appId):
    if os.name != "nt":
        return

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appId)
    except:
        pass


def unsetEnv(varnames):
    if hasattr(os, "unsetenv"):
        for var in varnames:
            os.unsetenv(var)
    else:
        for var in varnames:
            try:
                del os.environ[var]
            except KeyError:
                pass


def _setup_argument(prog):
    parser = argparse.ArgumentParser(
        usage=prog + " [-h] <command> [<args>]")
    subparsers = parser.add_subparsers(
        title="The <command> list",
        dest="cmd", metavar="")

    log_parser = subparsers.add_parser(
        "log",
        help="Show commit logs")
    log_parser.add_argument(
        "-c", "--compare-mode", action="store_true",
        help="Compare mode, show two branches for comparing")
    log_parser.add_argument(
        "file", metavar="<file>", nargs="?",
        help="The file to filter.")

    mergetool_parser = subparsers.add_parser(
        "mergetool",
        help="Run mergetool to resolve merge conflicts.")

    blame_parser = subparsers.add_parser(
        "blame",
        help="Show what revision and author last modified each line of a file.")
    blame_parser.add_argument(
        "file", metavar="<file>", nargs="?",
        help="The file to blame.")

    return parser.parse_args()


def _move_center(window):
    window.setGeometry(QStyle.alignedRect(
        Qt.LeftToRight, Qt.AlignCenter,
        window.size(),
        qApp.desktop().availableGeometry()))


def _do_log(app, args):
    merge_mode = args.cmd == "mergetool"
    if merge_mode and not Git.isMergeInProgress():
        QMessageBox.information(None, app.applicationName(),
                                app.translate("app", "Not in merge state, now quit!"))
        return 0

    window = MainWindow(merge_mode)
    _move_center(window)

    if args.cmd == "log":
        # merge mode will also change to compare view
        if args.compare_mode:
            window.setCompareMode()

        if args.file:
            window.setFilterFile(args.file)

    repoDir = Git.repoTopLevelDir(os.getcwd())
    if repoDir:
        window.setRepoDir(repoDir)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return app.exec_()


def _do_blame(app, args):
    window = BlameWindow()
    _move_center(window)
    window.showMaximized()

    return app.exec_()


def main():
    unsetEnv(["QT_SCALE_FACTOR", "QT_AUTO_SCREEN_SCALE_FACTOR"])

    args = _setup_argument(os.path.basename(sys.argv[0]))

    setAppUserId("appid.qgitc.xyz")
    app = Application(sys.argv)

    sys.excepthook = ExceptHandler

    if args.cmd == "blame":
        return _do_blame(app, args)
    else:
        return _do_log(app, args)

    return 0


if __name__ == "__main__":
    main()
