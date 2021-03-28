# -*- coding: utf-8 -*-

from PySide2.QtCore import QEvent


class BlameEvent(QEvent):

    Type = QEvent.User + 1

    def __init__(self, filePath, rev=None, lineNo=0):
        super().__init__(QEvent.Type(BlameEvent.Type))
        self.filePath = filePath
        self.rev = rev
        self.lineNo = lineNo


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
