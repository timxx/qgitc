# -*- coding: utf-8 -*-

from typing import Dict, List, overload

from PySide6.QtCore import QEvent, QObject

from qgitc.common import Commit


class BlameEvent(QEvent):

    Type = QEvent.User + 1

    def __init__(self, filePath, rev=None, lineNo=0, repoDir=None):
        super().__init__(QEvent.Type(BlameEvent.Type))
        self.filePath = filePath
        self.rev = rev
        self.lineNo = lineNo
        self.repoDir = repoDir


class ShowCommitEvent(QEvent):

    Type = QEvent.User + 2

    def __init__(self, sha1):
        super().__init__(QEvent.Type(ShowCommitEvent.Type))
        self.sha1 = sha1


class OpenLinkEvent(QEvent):

    Type = QEvent.User + 3

    def __init__(self, link):
        super().__init__(QEvent.Type(OpenLinkEvent.Type))
        self.link = link


class CopyConflictCommit(QEvent):

    Type = QEvent.User + 4

    def __init__(self, commit):
        super().__init__(QEvent.Type(CopyConflictCommit.Type))
        self.commit = commit


class GitBinChanged(QEvent):

    Type = QEvent.User + 5

    def __init__(self):
        super().__init__(QEvent.Type(GitBinChanged.Type))


class CodeReviewEvent(QEvent):
    Type = QEvent.User + 6

    @overload
    def __init__(self, commit: Commit, args: List[str] = None): ...

    @overload
    def __init__(self, submodules: List[str]): ...

    @overload
    def __init__(self, submoduleFiles: Dict[str, list]): ...

    def __init__(self, *args):
        super().__init__(QEvent.Type(CodeReviewEvent.Type))

        if len(args) == 1 and (isinstance(args[0], list) or isinstance(args[0], dict)):
            self.submodules = args[0]
        else:
            self.submodules = None
            self.commit = args[0]
            self.args = args[1] if len(args) > 1 else None


class RequestCommitEvent(QEvent):
    Type = QEvent.User + 7

    def __init__(self):
        super().__init__(QEvent.Type(RequestCommitEvent.Type))


class LocalChangesCommittedEvent(QEvent):
    Type = QEvent.User + 8

    def __init__(self):
        super().__init__(QEvent.Type(LocalChangesCommittedEvent.Type))


class RequestLoginGithubCopilot(QEvent):
    Type = QEvent.User + 9

    def __init__(self, requestor: QObject, autoClose: bool = True):
        super().__init__(QEvent.Type(RequestLoginGithubCopilot.Type))
        self.requestor = requestor
        self.autoClose = autoClose


class LoginFinished(QEvent):
    Type = QEvent.User + 10

    def __init__(self, isSuccessful: bool):
        super().__init__(QEvent.Type(LoginFinished.Type))
        self.isSuccessful = isSuccessful


class ShowAiAssistantEvent(QEvent):
    Type = QEvent.User + 11

    def __init__(self):
        super().__init__(QEvent.Type(ShowAiAssistantEvent.Type))
