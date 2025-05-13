# -*- coding: utf-8 -*-

from typing import Dict, List

from PySide6.QtCore import Signal

from qgitc.common import toSubmodulePath
from qgitc.datafetcher import DataFetcher
from qgitc.diffutils import *
from qgitc.gitutils import Git


class DiffFetcher(DataFetcher):

    diffAvailable = Signal(list, dict)

    def __init__(self, parent=None):
        super(DiffFetcher, self).__init__(parent)
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
        super(DiffFetcher, self).cancel()

    def makeArgs(self, args):
        sha1: str = args[0]
        filePaths: List[str] = args[1]
        gitArgs = args[2]

        git_args = ["-c", "core.quotePath=false"]

        if sha1 == Git.LCC_SHA1:
            git_args.extend(["diff-index", "--cached", "HEAD"])
        elif sha1 == Git.LUC_SHA1:
            git_args.extend(["diff-files"])
        elif sha1 == None:  # untracked files
            assert len(filePaths) == 1
            git_args.extend(["diff", "-p", "--no-index", "/dev/null"])
        else:
            git_args.extend(["diff-tree", "-r", "--root", sha1])

        if sha1 is not None:
            git_args.extend(["-p", "--textconv", "--submodule",
                             "-C", "--cc", "--no-commit-id", "-U3"])

        if gitArgs:
            git_args.extend(gitArgs)

        if filePaths:
            git_args.append("--")
            if self._repoDir and self._repoDir != ".":
                for path in filePaths:
                    git_args.append(toSubmodulePath(self._repoDir, path))
            else:
                git_args.extend(filePaths)

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
