# -*- coding: utf-8 -*-

from qgitc.common import Commit


class CommitSource:

    def __init__(self, parent=None):
        pass

    def findCommitIndex(self, sha1: str, begin=0, findNext=True) -> int:
        raise NotImplemented

    def getCommit(self, index: int) -> Commit:
        raise NotImplemented

    def getCount(self) -> int:
        raise NotImplemented
