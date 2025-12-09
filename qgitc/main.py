# -*- coding: utf-8 -*-

import argparse
import logging
import logging.handlers
import os
import subprocess
import sys
import tempfile
import threading
import traceback

from PySide6.QtCore import (
    QCoreApplication,
    QMessageLogContext,
    Qt,
    QtMsgType,
    qInstallMessageHandler,
)
from PySide6.QtWidgets import QStyle

from qgitc.application import Application
from qgitc.applicationbase import ApplicationBase
from qgitc.common import attachConsole, logger
from qgitc.excepthandler import ExceptHandler
from qgitc.gitutils import Git, GitProcess
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
    commit_parser.add_argument(
        "--ai", action="store_true",
        help="Generate commit message using AI in console mode")
    commit_parser.set_defaults(func=_do_commit)

    chat_parser = subparsers.add_parser(
        "chat",
        help="Show chat window.")
    chat_parser.set_defaults(func=_do_chat)

    branch_compare_parser = subparsers.add_parser(
        "bcompare",
        help="Compare changes between branches.")
    branch_compare_parser.set_defaults(func=_do_branch_compare)

    pick_branch_parser = subparsers.add_parser(
        "pick",
        help="Cherry-pick commits from one branch to another.")
    pick_branch_parser.add_argument(
        "source_branch",
        metavar="<branch>",
        nargs="?",
        help="Source branch to cherry-pick from.")
    pick_branch_parser.set_defaults(func=_do_pick_branch)

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


def _log_bad_timer_frame():
    mainThread = threading.main_thread()
    frames = sys._current_frames()
    mainFrame = frames.get(mainThread.ident)
    if mainFrame:
        stack = traceback.format_stack(mainFrame)
        logger.error(f"Bad stop/killTimer (main):\n{''.join(stack)}")

    curThread = threading.current_thread()
    if curThread is mainThread:
        return
    curFrame = frames.get(curThread.ident)
    if curFrame:
        stack = traceback.format_stack(curFrame)
        logger.error(f"Bad stop/killTimer (child):\n{''.join(stack)}")


def _qt_message_handler(type: QtMsgType, context: QMessageLogContext, msg: str):
    if type == QtMsgType.QtWarningMsg:
        if msg.startswith("QBasicTimer::stop: Failed") or msg.startswith("QObject::killTimer"):
            _log_bad_timer_frame()
        logger.warning(msg)
    elif type == QtMsgType.QtCriticalMsg:
        logger.critical(msg)
    elif type == QtMsgType.QtFatalMsg:
        logger.fatal(msg)
    elif type == QtMsgType.QtInfoMsg:
        logger.info(msg)
    else:
        logger.debug(msg)


def _init_gui(cmd: str):
    setAppUserId("appid.qgitc.xyz")
    qInstallMessageHandler(_qt_message_handler)

    app = Application(sys.argv)

    sys.excepthook = ExceptHandler
    _setup_logging()

    styleName = app.settings().styleName()
    if styleName and styleName.lower() != app.style().name().lower():
        app.setStyle(styleName)
        logger.info("Set style: %s", styleName)

    app.telemetry().logger().info(
        "app activity", extra={
            "event.type": "user_activity",
            "user.id": app.settings().userId(),
            "app.cmd": cmd
        })

    return app


def _do_exec(app: ApplicationBase):
    ret = app.exec()
    app.telemetry().shutdown()
    return ret


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
    app = _init_gui(args.cmd)

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

    return _do_exec(app)


def _do_blame(args):
    app = _init_gui(args.cmd)

    window = app.getWindow(WindowType.BlameWindow)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    file = os.path.abspath(args.file)
    _detect_and_fix_repo(file)

    window.blame(file, args.rev, args.line_number)

    return _do_exec(app)


def _do_commit_ai(app: Application, args):
    """Console mode commit with AI-generated message"""
    import itertools
    import time

    from qgitc.aicommitmessage import AiCommitMessage

    if not Git.REPO_DIR:
        print(QCoreApplication.translate("AiCommit", "Not in a git repository"))
        return 1

    print(QCoreApplication.translate("AiCommit", "Collecting staged files..."))
    status_data = Git.status(Git.REPO_DIR)
    if not status_data:
        print(QCoreApplication.translate("AiCommit", "No changes detected"))
        return 1

    staged_files = []
    lines = status_data.decode("utf-8", errors="replace").split("\0")
    for line in lines:
        if not line or len(line) < 4:
            continue
        status_code = line[:2]
        file_path = line[3:]
        # Files with status in the index (first character is not space or ?)
        if status_code[0] not in (' ', '?'):
            staged_files.append(file_path)

    if not staged_files:
        print(QCoreApplication.translate("AiCommit",
              "No staged files found. Please stage your changes first."))
        return 1

    print(QCoreApplication.translate("AiCommit",
          "Found {0} staged file(s):").format(len(staged_files)))
    for f in staged_files:
        print(f"  - {f}")

    submodule_files = {None: staged_files}

    print(QCoreApplication.translate("AiCommit",
          "\nGenerating commit message using AI..."))

    ai_message = AiCommitMessage()
    message_received = [None]
    error_received = [None]
    finished = [False]

    def on_message_available(msg):
        message_received[0] = msg
        finished[0] = True
        app.quit()

    def on_error_occurred(err):
        error_received[0] = err
        finished[0] = True
        app.quit()

    ai_message.messageAvailable.connect(on_message_available)
    ai_message.errorOccurred.connect(on_error_occurred)

    # Show progress indicator
    progress_chars = itertools.cycle(
        ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])

    def show_progress():
        working_text = QCoreApplication.translate("AiCommit", "Working...")
        while not finished[0]:
            sys.stdout.write(f'\r{next(progress_chars)} {working_text}')
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write('\r' + ' ' * 20 + '\r')
        sys.stdout.flush()

    progress_thread = threading.Thread(target=show_progress, daemon=True)
    progress_thread.start()

    ai_message.generate(submodule_files)

    app.trackFeatureUsage("commit.ai_gen_console")
    app.exec()

    # Wait for progress thread to finish
    progress_thread.join(timeout=1.0)

    if error_received[0]:
        print(QCoreApplication.translate("AiCommit",
              "\nError: {0}").format(error_received[0]))
        return 1

    if not message_received[0]:
        print(QCoreApplication.translate(
            "AiCommit", "\nNo commit message generated"))
        return 1

    commit_message = message_received[0]

    print("=" * 60)
    print(commit_message)
    print("=" * 60)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(commit_message)
        temp_file = f.name

    try:
        process = subprocess.run(
            [GitProcess.GIT_BIN, "commit", "-e", "-F", temp_file,])
        if process.returncode == 0:
            print(QCoreApplication.translate(
                "AiCommit", "\nCommit successful!"))
            return 0
        else:
            print(QCoreApplication.translate(
                "AiCommit", "\nCommit cancelled or failed"))
            return 1
    finally:
        try:
            os.unlink(temp_file)
        except:
            pass


def _do_commit(args):
    app = _init_gui(args.cmd)

    if args.ai:
        ret = _do_commit_ai(app, args)
        app.quit()
        # _onAboutToQuit will not be called as event loop may not be started
        app._onAboutToQuit()
        app.telemetry().shutdown()
        return ret

    window = app.getWindow(WindowType.CommitWindow)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return _do_exec(app)


def _do_chat(args):
    app = _init_gui(args.cmd)

    window = app.getWindow(WindowType.AiAssistant)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return _do_exec(app)


def _do_branch_compare(args):
    app = _init_gui(args.cmd)

    window = app.getWindow(WindowType.BranchCompareWindow)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return _do_exec(app)


def _do_pick_branch(args):
    app = _init_gui(args.cmd)

    window = app.getWindow(WindowType.PickBranchWindow)
    _move_center(window)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    # Set source branch if specified
    if args.source_branch:
        window.setSourceBranch(args.source_branch)

    return _do_exec(app)


def main():
    attachConsole()
    args = _setup_argument(os.path.basename(sys.argv[0]))
    return args.func(args)


if __name__ == "__main__":
    main()
