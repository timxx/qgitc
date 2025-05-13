# -*- coding: utf-8 -*-

import bisect
import os
from typing import List

from PySide6.QtCore import SIGNAL, QObject, QProcess, Signal

from qgitc.commitsource import CommitSource
from qgitc.common import (
    FIND_CANCELED,
    FIND_NOTFOUND,
    FIND_REGEXP,
    Commit,
    FindField,
    FindParameter,
    filterSubmoduleByPath,
    toSubmodulePath,
)
from qgitc.gitutils import Git, GitProcess


class FindWorker(QObject):

    resultAvailable = Signal(list)
    finished = Signal(int, int)

    def __init__(self, submodule: str, parent=None):
        super().__init__(parent)
        self._submodule = submodule
        self._process: QProcess = None
        self._result = []
        self._dataFragment = None

    def cancel(self):
        if not self._process:
            return

        QObject.disconnect(self._process,
                           SIGNAL("readyReadStandardOutput()"),
                           self._onDataAvailable)
        QObject.disconnect(self._process,
                           SIGNAL("finished(int, QProcess::ExitStatus)"),
                           self._onFinished)
        self._process.kill()

    def find(self, sha1s: List[str], param: FindParameter, filterPath: List[str] = None):
        assert len(sha1s) > 0

        args = ["diff-tree", "-r", "-s", "-m", "--stdin"]
        if param.field == FindField.AddOrDel:
            args.append("-S" + param.pattern)
            if param.flag == FIND_REGEXP:
                args.append("--pickaxe-regex")
        else:
            assert param.field == FindField.Changes
            args.append("-G" + param.pattern)

        if filterPath:
            args.append("--")

            if self._submodule and self._submodule != ".":
                for path in filterPath:
                    args.append(toSubmodulePath(self._submodule, path))
            else:
                args.extend(filterPath)

        if not self._submodule or self._submodule == ".":
            cwd = Git.REPO_DIR
        else:
            cwd = os.path.join(Git.REPO_DIR, self._submodule)

        self._process = QProcess(self)
        self._process.setWorkingDirectory(cwd)
        self._process.readyReadStandardOutput.connect(self._onDataAvailable)
        self._process.finished.connect(self._onFinished)

        self._process.start(GitProcess.GIT_BIN, args)

        data = "\n".join(sha1s).encode("utf-8")
        self._process.write(data + b"\n")
        self._process.closeWriteChannel()

    def _onDataAvailable(self):
        data = self._process.readAllStandardOutput()
        self._parseData(data.data())

    def _onFinished(self, exitCode, exitStatus):
        self.finished.emit(exitCode, exitStatus)
        self._process = None

    def _parseData(self, data: bytes):
        if self._dataFragment:
            fullData = self._dataFragment
            fullData += data
            self._dataFragment = None
        else:
            fullData = data

        # full sha1 length + newline
        if len(fullData) < 41:
            self._dataFragment = fullData
            return

        parts = fullData.rstrip(b'\n').split(b'\n')
        if len(parts[-1]) < 40:
            self._dataFragment = parts[-1]
            parts.pop()

        if parts:
            self.resultAvailable.emit([p.decode("utf-8") for p in parts])


class DiffFinder(QObject):

    resultAvailable = Signal()
    findFinished = Signal(int)

    def __init__(self, source: CommitSource, parent=None):
        super().__init__(parent)
        self._finders: List[FindWorker] = []
        self._source = source
        self._result = []
        self._param: FindParameter = None
        self._filterPath: List[str] = None
        self._submodules: List[str] = None
        self._sha1IndexMap = {}

    def updateParameters(self, param: FindParameter, filterPath: List[str], submodules: List[str]):
        """True if the parameters are updated, False otherwise."""
        if self._param == param and \
                self._filterPath == filterPath and \
                self._submodules == submodules:
            # always update the range
            self._param = param
            return False

        self._param = param
        self._filterPath = filterPath
        self._submodules = submodules
        self.clearResult()

        return True

    def findAsync(self):
        self.cancel()

        moduleSha1s = self._dispatchCommits()
        if not moduleSha1s:
            return False

        # TODO: limit the number of finders running at the same time
        for submodule, sha1s in moduleSha1s.items():
            finder = FindWorker(submodule, self)
            finder.resultAvailable.connect(
                self._onResultAvailable)
            finder.finished.connect(
                self._onFindFinished)
            self._finders.append(finder)
            finder.find(sha1s, self._param, self._filterPath)

        return True

    def cancel(self):
        for finder in self._finders:
            finder.cancel()
        self._finders.clear()

    def reset(self):
        self.cancel()
        self.clearResult()
        self._param = None
        self._filterPath = None
        self._submodules = None

    def clearResult(self):
        self._result.clear()
        self._sha1IndexMap.clear()

    def isRunning(self):
        return len(self._finders) > 0

    @property
    def findResult(self):
        return self._result

    def nextResult(self):
        if not self._param.range or not self._result:
            return FIND_NOTFOUND

        x = self._param.range.start
        if self._param.range.start > self._param.range.stop:
            index = bisect.bisect_left(self._result, x)
            if index < len(self._result) and self._result[index] <= x:
                return self._result[index]
            if index - 1 >= 0 and self._result[index - 1] <= x:
                return self._result[index - 1]
        else:
            index = bisect.bisect_right(self._result, x)
            if index - 1 >= 0 and self._result[index - 1] >= x:
                return self._result[index - 1]
            if index < len(self._result):
                return self._result[index]

        return FIND_NOTFOUND

    def _onResultAvailable(self, result: List[str]):
        for sha1 in result:
            index = self._sha1IndexMap[sha1]
            bisect.insort(self._result, index)
        self.resultAvailable.emit()

    def _onFindFinished(self, exitCode, exitStatus):
        finder: FindWorker = self.sender()
        self._finders.remove(finder)
        if self._finders:
            return

        if exitCode != 0 and exitStatus != QProcess.NormalExit:
            self.findFinished.emit(FIND_CANCELED)
        elif not self._result:
            self.findFinished.emit(FIND_NOTFOUND)

    def _dispatchCommits(self):
        moduleSha1s = {}

        submodules = filterSubmoduleByPath(self._submodules, self._filterPath)

        def _consumeCommit(commit: Commit):
            if not submodules:
                moduleSha1s.setdefault(None, []).append(commit.sha1)
                return

            for submodule in submodules:
                if commit.repoDir == submodule:
                    moduleSha1s.setdefault(commit.repoDir, []).append(commit.sha1)

        def _dispatch(rg: range):
            for i in rg:
                commit = self._source.getCommit(i)
                self._sha1IndexMap[commit.sha1] = i
                _consumeCommit(commit)
                    
                for subCommit in commit.subCommits:
                    self._sha1IndexMap[subCommit.sha1] = i
                    _consumeCommit(subCommit)

        # find the target range first
        _dispatch(self._param.range)

        if self._param.range.start > self._param.range.stop:
            begin = self._param.range.start + 1
            end = self._source.getCount()
        else:
            begin = 0
            end = self._param.range.start

        # then the rest
        _dispatch(range(begin, end))

        return moduleSha1s
