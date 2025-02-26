# -*- coding: utf-8 -*-

from PySide6.QtCore import Signal

from .datafetcher import DataFetcher
from .diffutils import *
from .gitutils import Git


class DiffFetcher(DataFetcher):

    diffAvailable = Signal(list, dict)

    def __init__(self, parent=None):
        super(DiffFetcher, self).__init__(parent)
        self._isDiffContent = False
        self._row = 0
        self._firstPatch = True
        self._repoDir = None
        self.repoDirBytes = None

    def parse(self, data):
        lineItems = []
        fileItems = {}

        if data[-1] == ord(self.separator):
            data = data[:-1]

        lines = data.split(self.separator)
        for line in lines:
            match = diff_re.search(line)
            if match:
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
                fileItems[fullFileA.decode(diff_encoding)] = self._row
                # renames, keep new file name only
                if fileB and fileB != fileA:
                    fullFileB = self.makeFilePath(fileB)
                    lineItems.append((DiffType.File, fullFileB))
                    fileItems[fullFileB.decode(diff_encoding)] = self._row
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
                fileItems[submodule.decode(diff_encoding)] = self._row
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
            elif line.startswith(b"--- ") or line.startswith(b"+++ "):
                continue
            elif not line:  # ignore the empty info line
                continue
            else:
                itemType = DiffType.FileInfo

            if itemType != DiffType.Diff:
                line = line.rstrip(b'\r')
            lineItems.append((itemType, line))
            self._row += 1

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
            self.repoDirBytes = self.repoDir.replace("\\", "/").encode("utf-8") + b"/"
        else:
            self.repoDirBytes = None

    def makeFilePath(self, file):
        if not self.repoDirBytes:
            return file
        return self.repoDirBytes + file
