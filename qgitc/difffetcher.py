# -*- coding: utf-8 -*-

from typing import Dict
from PySide6.QtCore import Signal, QThread, QObject, QEventLoop

from .datafetcher import DataFetcher
from .diffutils import *
from .gitutils import Git


class DiffFetcherImpl(DataFetcher):

    diffAvailable = Signal(list, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._isDiffContent = False
        self._row = 0
        self._firstPatch = True
        self._repoDir = None
        self.repoDirBytes = None

    def parse(self, data: bytes):
        lineItems = []
        fileItems: Dict[str, FileInfo] = {}

        if data[-1] == ord(self.separator):
            data = data[:-1]

        lines = data.split(self.separator)
        fullFileAStr = None
        fullFileBStr = None
        fileState = FileState.Normal

        def _updateFileState():
            nonlocal fullFileAStr, fullFileBStr, fileState
            if fileState != FileState.Normal and fileItems:
                if fullFileAStr and fullFileAStr in fileItems:
                    fileItems[fullFileAStr].state = fileState
                if fullFileBStr and fullFileBStr in fileItems:
                    fileItems[fullFileBStr].state = fileState
            fullFileAStr = None
            fullFileBStr = None
            fileState = FileState.Normal

        for line in lines:
            match = diff_re.search(line)
            if match:
                # maybe renamed only
                _updateFileState()
                if match.group(4):  # diff --cc
                    fileA = match.group(4)
                    fileB = None
                else:
                    fileA = match.group(2)
                    fileB = match.group(3)

                if not self._firstPatch:
                    lineItems.append((DiffType.Diff, b''))
                    self._row += 1
                self._firstPatch = False

                fullFileA = self.makeFilePath(fileA)
                fullFileAStr = fullFileA.decode(diff_encoding)
                fileItems[fullFileAStr] = FileInfo(self._row)
                # renames, keep new file name only
                if fileB and fileB != fileA:
                    fullFileB = self.makeFilePath(fileB)
                    lineItems.append((DiffType.File, fullFileB))
                    fullFileBStr = fullFileB.decode(diff_encoding)
                    fileItems[fullFileBStr] = FileInfo(self._row)
                else:
                    lineItems.append((DiffType.File, fullFileA))

                self._row += 1
                self._isDiffContent = False

                continue

            match = submodule_re.match(line)
            if match:
                if not self._firstPatch:
                    lineItems.append((DiffType.Diff, b''))
                    self._row += 1
                self._firstPatch = False

                submodule = match.group(1)
                lineItems.append((DiffType.File, submodule))
                fileItems[submodule.decode(
                    diff_encoding)] = FileInfo(self._row)
                self._row += 1

                lineItems.append((DiffType.FileInfo, line))
                self._row += 1

                self._isDiffContent = True
                continue

            if self._isDiffContent:
                itemType = DiffType.Diff
            elif diff_begin_bre.search(line):
                self._isDiffContent = True
                itemType = DiffType.Diff
                _updateFileState()
            elif line.startswith(b"--- ") or line.startswith(b"+++ "):
                continue
            elif not line:  # ignore the empty info line
                continue
            else:
                itemType = DiffType.FileInfo
                if line.startswith(b"new file mode "):
                    fileState = FileState.Added
                elif line.startswith(b"deleted file mode "):
                    fileState = FileState.Deleted
                elif line.startswith(b"rename "):
                    fileState = FileState.Renamed
                elif line.startswith(b"index "):
                    if fileState == FileState.Renamed:
                        fileState = FileState.RenamedModified
                    elif fileState == FileState.Normal:
                        fileState = FileState.Modified

            if itemType != DiffType.Diff:
                line = line.rstrip(b'\r')
            lineItems.append((itemType, line))
            self._row += 1

        # maybe no diff (added blank file)
        _updateFileState()

        if lineItems:
            self.diffAvailable.emit(lineItems, fileItems)

    def resetRow(self, row):
        self._row = row
        self._isDiffContent = False
        self._firstPatch = True

    def cancel(self):
        self._isDiffContent = False
        super().cancel()

    def makeArgs(self, args):
        sha1 = args[0]
        filePath = args[1]
        gitArgs = args[2]

        git_args = ["-c", "core.quotePath=false"]

        if sha1 == Git.LCC_SHA1:
            git_args.extend(["diff-index", "--cached", "HEAD"])
        elif sha1 == Git.LUC_SHA1:
            git_args.extend(["diff-files"])
        else:
            git_args.extend(["diff-tree", "-r", "--root", sha1])

        git_args.extend(["-p", "--textconv", "--submodule",
                         "-C", "--cc", "--no-commit-id", "-U3"])

        if gitArgs:
            git_args.extend(gitArgs)

        if filePath:
            git_args.append("--")
            git_args.extend(filePath)

        return git_args

    @property
    def repoDir(self):
        return self._repoDir

    @repoDir.setter
    def repoDir(self, repoDir):
        self._repoDir = repoDir
        if repoDir:
            self.repoDirBytes = self.repoDir.replace(
                "\\", "/").encode("utf-8") + b"/"
        else:
            self.repoDirBytes = None

    def makeFilePath(self, file):
        if not self.repoDirBytes:
            return file
        return self.repoDirBytes + file


class DiffFetcherThread(QThread):

    diffAvailable = Signal(list, dict)
    fetchFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cwd = None
        self.repoDir = None
        self.row = 0
        self.args = tuple()
        self.errorData = b''

    def fetch(self, cwd, repoDir, row, *args):
        self.cwd = cwd
        self.repoDir = repoDir
        self.row = row
        self.args = args
        self.start()

    def run(self):
        eventLoop = QEventLoop()

        fetcher = DiffFetcherImpl()
        fetcher.cwd = self.cwd
        fetcher.repoDir = self.repoDir
        fetcher.resetRow(self.row)
        fetcher.diffAvailable.connect(self.diffAvailable)
        fetcher.fetchFinished.connect(self.fetchFinished)
        fetcher.fetchFinished.connect(eventLoop.quit)
        if self.isInterruptionRequested():
            return
        fetcher.fetch(*self.args)

        eventLoop.exec()

    def cancel(self):
        self.requestInterruption()

    def _onFetchFinished(self, exitCode):
        fetcher = self.sender()
        self.errorData = fetcher.errorData
        self.fetchFinished.emit(exitCode)


class DiffFetcher(QObject):
    diffAvailable = Signal(list, dict)
    fetchFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: DiffFetcherThread = None
        self._errorData = b''
        self.cwd = None
        self.repoDir = None
        self.row = 0

    def resetRow(self, row: int):
        self.row = row

    @property
    def errorData(self):
        return self._errorData

    def fetch(self, *args):
        self.cancel()
        self._errorData = b''
        self._thread = DiffFetcherThread(self)
        self._thread.diffAvailable.connect(self.diffAvailable)
        self._thread.fetchFinished.connect(self.fetchFinished)
        self._thread.fetch(self.cwd, self.repoDir, self.row, *args)

    def cancel(self):
        if self._thread:
            self._thread.disconnect(self)
            self._thread.cancel()
            self._thread = None
