# -*- coding: utf-8 -*-

import argparse
import logging
import logging.handlers
import os
import sys

from PySide6.QtCore import QMessageLogContext, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QStyle

from qgitc.application import Application
from qgitc.applicationbase import ApplicationBase
from qgitc.common import attachConsole, logger
from qgitc.excepthandler import ExceptHandler
from qgitc.gitutils import Git
from qgitc.mainwindow import MainWindow
from qgitc.shell import setup_shell_args
from qgitc.windowtype import WindowType


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
        "-r", "--rev",
        metavar="<rev>",
        help="Show changes for <rev>.")
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

    commit_parser = subparsers.add_parser(
        "commit",
        help="Show commit window to commit changes.")
    commit_parser.set_defaults(func=_do_commit)

    chat_parser = subparsers.add_parser(
        "chat",
        help="Show chat window.")
    chat_parser.set_defaults(func=_do_chat)

    setup_shell_args(subparsers)

    return parser.parse_args()


def _move_center(window):
    window.setGeometry(QStyle.alignedRect(
        Qt.LeftToRight, Qt.AlignCenter,
        window.size(),
        ApplicationBase.instance().primaryScreen().availableGeometry()))


def _setup_logging():
    logDir = os.path.join(os.path.expanduser("~"), ".qgitc")
    os.makedirs(logDir, exist_ok=True)
    logFile = os.path.join(logDir, "qgitc.log")

    rootLogger = logging.getLogger()
    rootLogger.setLevel(ApplicationBase.instance().settings().logLevel())

    handler = logging.handlers.RotatingFileHandler(
        logFile, maxBytes=1 * 1024 * 1024, backupCount=3, encoding="utf-8")
    rootLogger.addHandler(handler)

    formatter = logging.Formatter(
        "[%(levelname)s][%(asctime)s]%(filename)s:%(lineno)d - %(message)s")
    handler.setFormatter(formatter)


def _qt_message_handler(type: QtMsgType, context: QMessageLogContext, msg: str):
    if type == QtMsgType.QtWarningMsg:
        logger.warning(msg)
    elif type == QtMsgType.QtCriticalMsg:
        logger.critical(msg)
    elif type == QtMsgType.QtFatalMsg:
        logger.fatal(msg)
    elif type == QtMsgType.QtInfoMsg:
        logger.info(msg)
    else:
        logger.debug(msg)


def _init_gui():
    setAppUserId("appid.qgitc.xyz")
    qInstallMessageHandler(_qt_message_handler)

    app = Application(sys.argv)

    sys.excepthook = ExceptHandler
    _setup_logging()

    styleName = app.settings().styleName()
    if styleName and styleName.lower() != app.style().name().lower():
        app.setStyle(styleName)
        logger.info("Set style: %s", styleName)

    return app


def _detect_and_fix_repo(filterFile):
    needFix = False
    if Git.REPO_DIR:
        needFix = Git.repoTopLevelDir(Git.REPO_DIR) is None
    else:
        needFix = True
    if needFix:
        repoDir = Git.repoTopLevelDir(os.path.dirname(filterFile))
        if repoDir:
            ApplicationBase.instance().updateRepoDir(repoDir)


def _do_log(args):
    app = _init_gui()

    merge_mode = args.cmd == "mergetool"
    window = app.getWindow(WindowType.LogWindow)
    if merge_mode:
        window.setMode(MainWindow.MergeMode)
    _move_center(window)

    if args.cmd == "log":
        # merge mode will also change to compare view
        if args.compare_mode:
            window.setMode(MainWindow.CompareMode)

        filterOpts = ""
        if args.rev:
            filterOpts = args.rev

        if args.file:
            filterFile = args.file
            if not os.path.isabs(filterFile):
                filterFile = os.path.abspath(filterFile)

            _detect_and_fix_repo(filterFile)

            if Git.REPO_DIR:
                normPath = os.path.normcase(os.path.normpath(filterFile))
                repoDir = os.path.normcase(os.path.normpath(Git.REPO_DIR))
                if normPath.find(repoDir) != -1:
                    filterFile = filterFile[len(repoDir) + 1:]

            if filterOpts:
                filterOpts += " -- " + filterFile
            else:
                filterOpts = "-- " + filterFile
        window.setFilterOptions(filterOpts)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return app.exec()


def _do_blame(args):
    app = _init_gui()

    window = app.getWindow(WindowType.BlameWindow)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    file = os.path.abspath(args.file)
    _detect_and_fix_repo(file)

    window.blame(file, args.rev, args.line_number)

    return app.exec()


def _do_commit(args):
    app = _init_gui()

    window = app.getWindow(WindowType.CommitWindow)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return app.exec()


def _do_chat(args):
    app = _init_gui()

    window = app.getWindow(WindowType.AiAssistant)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return app.exec()


def main():
    attachConsole()
    args = _setup_argument(os.path.basename(sys.argv[0]))
    return args.func(args)


if __name__ == "__main__":
    main()
