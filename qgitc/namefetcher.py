# -*- coding: utf-8 -*-

from PySide6.QtCore import Signal

from qgitc.datafetcher import DataFetcher


class NameFetcher(DataFetcher):

    dataAvailable = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._isSha1 = True
        self._curSha1 = None

    def parse(self, data: bytes):
        result = []
        for line in data.splitlines():
            if not line:
                continue
            if self._isSha1:
                self._curSha1 = line.decode("utf-8")
                self._isSha1 = False
                assert len(self._curSha1) == 40
            else:
                assert self._curSha1 is not None
                result.append((self._curSha1, line.decode("utf-8")))
                self._isSha1 = True
                self._curSha1 = None

        if result:
            self.dataAvailable.emit(result)

    def makeArgs(self, args):
        file = args[0]

        git_args = ["log", "--name-only",
                    "--pretty=format:%H", "--follow", "--", file]
        return git_args

    def reset(self):
        super().reset()
        self._isSha1 = True
        self._curSha1 = None
