# -*- coding: utf-8 -*-

from datetime import datetime

from PySide6.QtCore import Signal

from qgitc.blameline import BlameLine
from qgitc.common import logger
from qgitc.datafetcher import DataFetcher


def _timeStr(data):
    dt = datetime.fromtimestamp(float(data))
    return "%d-%02d-%02d %02d:%02d:%02d" % (
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second)


def _decode(data: bytes):
    return data.decode("utf-8")


class BlameFetcher(DataFetcher):

    dataAvailable = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curLine = BlameLine()

    def parse(self, data: bytes):
        results = []
        # TODO: support utf16 32 split...
        lines = data.rstrip(self.separator).split(self.separator)
        for line in lines:
            if line[0] == 9:  # \t
                self._curLine.text = line[1:]
                results.append(self._curLine)
                self._curLine = BlameLine()
            elif line[0] == 97 and line[1] == 117:  # author
                if line[6] == 32:  # "author "
                    self._curLine.author = _decode(line[7:])
                elif line[7] == 109:  # "author-mail "
                    self._curLine.authorMail = _decode(line[12:])
                elif line[8] == 105:  # "author-time "
                    self._curLine.authorTime = _timeStr(line[12:])
                elif line[8] == 122:  # "author-tz "
                    assert (self._curLine.authorTime is not None)
                    self._curLine.authorTime += _decode(line[9:])
                else:
                    logger.warning("Invalid line: %s", line)
            elif line[0] == 99 and line[1] == 111:  # committer
                if line[9] == 32:  # "committer "
                    self._curLine.committer = _decode(line[10:])
                elif line[10] == 109:  # "committer-mail "
                    self._curLine.committerMail = _decode(line[15:])
                elif line[11] == 105:  # "committer-time "
                    self._curLine.committerTime = _timeStr(line[15:])
                elif line[11] == 122:  # "committer-tz "
                    assert (self._curLine.committerTime is not None)
                    self._curLine.committerTime += _decode(line[12:])
                else:
                    logger.warning("Invalid line: %s", line)
            elif line[0] == 115:  # "summary "
                pass  # useless
            elif line[0] == 112:  # "previous "
                parts = line.split(b' ')
                self._curLine.previous = _decode(parts[1])
                self._curLine.prevFileName = _decode(parts[2])
            elif line[0] == 102 and line[1] == 105:  # "filename "
                self._curLine.filename = _decode(line[9:])
            elif line[0] == 98 and line[1] == 111:  # boundary
                pass
            else:
                parts = line.split(b' ')
                if len(parts) < 3 or len(parts) > 4:
                    logger.warning("Invalid line: %s", line)
                else:
                    self._curLine.sha1 = _decode(parts[0])
                    self._curLine.oldLineNo = int(parts[1])
                    self._curLine.newLineNo = int(parts[2])
                    if len(parts) == 4:
                        self._curLine.groupLines = int(parts[3])

        if results:
            self.dataAvailable.emit(results)

    def makeArgs(self, args):
        file = args[0]
        rev = args[1]

        blameArgs = ["blame", "--porcelain", "--", file]
        if rev:
            blameArgs.insert(1, rev)

        return blameArgs

    def reset(self):
        super().reset()
        self._curLine = BlameLine()
