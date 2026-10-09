# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment

from qgitc.gitutils import GitProcess
from qgitc.resolver.enums import (
    ResolveEventKind,
    ResolveFailureReason,
    ResolveMethod,
    ResolveOutcomeStatus,
    ResolvePromptKind,
)
from qgitc.resolver.handlers.base import ResolveHandler
from qgitc.resolver.models import (
    ResolveContext,
    ResolveEvent,
    ResolveOutcome,
    ResolvePrompt,
)
from qgitc.resolver.services import ResolveServices

# Output git mergetool writes when it cannot use a merge tool for this
# repository. It then waits on stdin for an answer that never comes, which is
# why the pick window used to look frozen instead of reporting the problem.
_NO_USABLE_MERGETOOL_MARKERS = (
    "merge.tool' is not configured",
    "hit return to start merge resolution tool",
    "set to unknown tool",
    "unknown mergetool",
    "no known mergetool is available",
    "is not available as",
    "cmd not set for tool",
)


def isNoUsableMergetoolOutput(text: str) -> bool:
    """Whether @text is git mergetool complaining about the merge tool config."""

    lower = (text or "").lower()
    if not lower:
        return False

    return any(marker in lower for marker in _NO_USABLE_MERGETOOL_MARKERS)


class GitMergetoolHandler(ResolveHandler):

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._ctx: Optional[ResolveContext] = None
        self._services: ResolveServices = None
        self._process: Optional[QProcess] = None
        self._promptId = 1
        self._awaitingPrompt = False
        self._pendingPrompt: Optional[ResolvePrompt] = None
        self._noMergetool = False
        self._outcomeEmitted = False

    def start(self, ctx: ResolveContext, services: ResolveServices):
        self._ctx = ctx
        self._services = services

        self._start()

    def cancel(self):
        if self._process is not None:
            self._process.kill()

    def _emit(self, ev: ResolveEvent):
        self._services.manager.emitEvent(ev)

    def _emitOutcome(self, handled: bool, outcome: Optional[ResolveOutcome]):
        if self._outcomeEmitted:
            return

        self._outcomeEmitted = True
        self.finished.emit(handled, outcome)

    def _noMergetoolOutcome(self) -> ResolveOutcome:
        return ResolveOutcome(
            status=ResolveOutcomeStatus.FAILED,
            message=self.tr("No merge tool is configured"),
            details={"reason": ResolveFailureReason.NO_MERGETOOL},
        )

    def _requestPrompt(self, prompt: ResolvePrompt):
        self._services.manager.requestPrompt(prompt)

    def onPromptReply(self, promptId: int, choice: object):
        if not self._awaitingPrompt or not self._pendingPrompt:
            return
        if self._pendingPrompt.promptId != promptId:
            return
        if self._process is None:
            return

        kind = self._pendingPrompt.kind
        ch = str(choice)

        # Deleted conflict options: 'c'/'m'/'d'/'a'
        if kind == ResolvePromptKind.DELETED_CONFLICT_CHOICE:
            self._process.write((ch + "\n").encode("utf-8"))
        elif kind == ResolvePromptKind.SYMLINK_CONFLICT_CHOICE:
            self._process.write((ch + "\n").encode("utf-8"))
        else:
            self._process.write((ch + "\n").encode("utf-8"))

        self._awaitingPrompt = False
        self._pendingPrompt = None

    def _start(self):
        ctx = self._ctx
        if ctx is None or self._services is None:
            self.finished.emit(False, None)
            return

        # git mergetool falls back to guessing a tool and then blocks on stdin
        # when the repository has no merge tool, so refuse to run it without an
        # explicit tool and let the caller tell the user to configure one.
        if not ctx.mergetoolName:
            self._emitOutcome(True, self._noMergetoolOutcome())
            return

        # Start mergetool.
        args = ["mergetool", "--no-prompt", f"--tool={ctx.mergetoolName}"]
        args.append(ctx.path)

        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._onStdout)
        self._process.finished.connect(self._onFinished)
        self._process.errorOccurred.connect(self._onErrorOccurred)
        self._process.setWorkingDirectory(ctx.repoDir)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("LANGUAGE", "en_US")
        self._process.setProcessEnvironment(env)

        self._emit(ResolveEvent(
            kind=ResolveEventKind.STEP,
            message=self.tr("Launching merge tool: {0}").format(
                ctx.mergetoolName),
            method=ResolveMethod.MERGETOOL))
        self._process.start(GitProcess.GIT_BIN, args)

    def _onStdout(self):
        if self._process is None or not self._process.bytesAvailable():
            return
        data = self._process.readAllStandardOutput().data()

        # Auto-answer: do not continue other unresolved paths.
        if b"Continue merging other unresolved paths [y/n]?" in data:
            self._process.write(b"n\n")
            return

        if b"Deleted merge conflict for" in data:
            text = data.decode("utf-8", errors="replace")
            isCreated = "(c)reated" in text
            promptText = text
            promptText = promptText.replace("(c)reated", "created")
            promptText = promptText.replace("(m)odified", "modified")
            promptText = promptText.replace("(d)eleted", "deleted")
            promptText = promptText.replace("(a)bort", "abort")

            options = ["c" if isCreated else "m", "d", "a"]
            p = ResolvePrompt(
                promptId=self._promptId,
                kind=ResolvePromptKind.DELETED_CONFLICT_CHOICE,
                title=self.tr("Deleted merge conflict"),
                text=promptText,
                options=options,
                meta={"isCreated": isCreated},
            )
            self._promptId += 1
            self._awaitingPrompt = True
            self._pendingPrompt = p
            self._requestPrompt(p)
            return

        if b"Symbolic link merge conflict for" in data:
            text = data.decode("utf-8", errors="replace")
            promptText = text
            promptText = promptText.replace("(l)ocal", "local")
            promptText = promptText.replace("(r)emote", "remote")
            promptText = promptText.replace("(a)bort", "abort")

            p = ResolvePrompt(
                promptId=self._promptId,
                kind=ResolvePromptKind.SYMLINK_CONFLICT_CHOICE,
                title=self.tr("Symlink conflict"),
                text=promptText,
                options=["l", "r", "a"],
            )
            self._promptId += 1
            self._awaitingPrompt = True
            self._pendingPrompt = p
            self._requestPrompt(p)
            return

        if b"Was the merge successful [y/n]?" in data:
            # Keep current behavior.
            self._process.write(b"n\n")
            return

        text = data.decode("utf-8", errors="replace")
        if isNoUsableMergetoolOutput(text):
            # There is no merge tool to run: rather than answering git's prompt
            # about a guessed tool, stop the process and report the real problem.
            self._noMergetool = True
            self._process.kill()
            return

        if b"?" in data:
            # Unknown prompt; do not guess.
            return

    def _onErrorOccurred(self, error: object):
        if error != QProcess.ProcessError.FailedToStart:
            return

        # QProcess does not emit `finished` when the process could not start,
        # so report it here or the caller waits forever.
        self._emitOutcome(True, ResolveOutcome(
            status=ResolveOutcomeStatus.FAILED,
            message=self.tr("Failed to start the merge tool"),
        ))

    def _onFinished(self, exitCode: int, exitStatus: object):
        if self._noMergetool:
            self._emitOutcome(True, self._noMergetoolOutcome())
            return

        stdout = ""
        err = ""
        if self._process is not None:
            stdout = self._process.readAllStandardOutput().data().decode(
                "utf-8", errors="replace")
            err = self._process.readAllStandardError().data().decode(
                "utf-8", errors="replace")

        if exitCode != 0:
            if isNoUsableMergetoolOutput(err + "\n" + stdout):
                self._emitOutcome(True, self._noMergetoolOutcome())
                return

            out = ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message=err.strip() or self.tr("Merge tool failed"),
            )
            self._emitOutcome(True, out)
            return

        self._emit(ResolveEvent(
            kind=ResolveEventKind.FILE_RESOLVED,
            message=self.tr("Resolved {path}").format(path=self._ctx.path),
            path=self._ctx.path,
            method=ResolveMethod.MERGETOOL,
        ))
        out = ResolveOutcome(
            status=ResolveOutcomeStatus.RESOLVED, message=self.tr("Resolved with merge tool"))
        self._emitOutcome(True, out)
