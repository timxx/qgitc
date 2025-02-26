# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent


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

    def __init__(self, commit, args=None):
        super().__init__(QEvent.Type(CodeReviewEvent.Type))
        self.commit = commit
        self.args = args
