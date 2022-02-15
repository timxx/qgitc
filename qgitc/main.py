# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QStyle)

from .gitutils import Git
from .excepthandler import ExceptHandler
from .application import Application
from .mainwindow import MainWindow
from .shell import setup_shell_args
from .common import isXfce4

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


def _setup_argument(prog):
    parser = argparse.ArgumentParser(
        usage=prog + " [-h] <command> [<args>]")
    subparsers = parser.add_subparsers(
        title="The <command> list",
        dest="cmd", metavar="")
    parser.set_defaults(func=_do_log)

    log_parser = subparsers.add_parser(
        "log",
        help="Show commit logs")
    log_parser.add_argument(
        "-c", "--compare-mode", action="store_true",
        help="Compare mode, show two branches for comparing")
    log_parser.add_argument(
        "file", metavar="<file>", nargs="?",
        help="The file to filter.")
    log_parser.set_defaults(func=_do_log)

    mergetool_parser = subparsers.add_parser(
        "mergetool",
        help="Run mergetool to resolve merge conflicts.")
    log_parser.set_defaults(func=_do_log)

    blame_parser = subparsers.add_parser(
        "blame",
        help="Show what revision and author last modified each line of a file.")
    blame_parser.add_argument(
        "--line-number", "-l",
        metavar="N", type=int,
        default=0,
        help="Goto the specify line number when opening a file.")
    blame_parser.add_argument(
        "--rev", "-r",
        metavar="<rev>",
        help="Blame with <rev>.")
    blame_parser.add_argument(
        "file", metavar="<file>",
        help="The file to blame.")
    blame_parser.set_defaults(func=_do_blame)

    setup_shell_args(subparsers)

    return parser.parse_args()


def _move_center(window):
    window.setGeometry(QStyle.alignedRect(
        Qt.LeftToRight, Qt.AlignCenter,
        window.size(),
        qApp.primaryScreen().availableGeometry()))


def _init_gui():
    setAppUserId("appid.qgitc.xyz")
    app = Application(sys.argv)

    sys.excepthook = ExceptHandler

    return app


def _do_log(args):
    app = _init_gui()

    merge_mode = args.cmd == "mergetool"
    window = app.getWindow(Application.LogWindow)
    if merge_mode:
        window.setMode(MainWindow.MergeMode)
    _move_center(window)

    if args.cmd == "log":
        # merge mode will also change to compare view
        if args.compare_mode:
            window.setMode(MainWindow.CompareMode)

        if args.file:
            filterFile = args.file
            if not os.path.isabs(filterFile):
                filterFile = os.path.abspath(filterFile)

            if Git.REPO_DIR:
                normPath = os.path.normcase(os.path.normpath(filterFile))
                repoDir = os.path.normcase(os.path.normpath(Git.REPO_DIR))
                if normPath.find(repoDir) != -1:
                    filterFile = filterFile[len(repoDir) + 1:]

            window.setFilterFile(filterFile)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return app.exec()


def _do_blame(args):
    app = _init_gui()

    window = app.getWindow(Application.BlameWindow)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    window.blame(args.file, args.rev, args.line_number)

    return app.exec()


def main():
    args = _setup_argument(os.path.basename(sys.argv[0]))
    return args.func(args)


if __name__ == "__main__":
    main()
