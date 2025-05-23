# -*- coding: utf-8 -*-

import cProfile
import io
import logging
import os
import pstats
import re
from datetime import datetime
from typing import List

import chardet

from qgitc.gitutils import Git

html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
}


str_split = str.split
str_strip = str.strip


logger = logging.getLogger("qgitc")


sha1_re = re.compile("(?<![a-zA-Z0-9_])[a-f0-9]{4,40}(?![a-zA-Z0-9_])")


class Commit():

    __slots__ = ("sha1", "comments", "author", "authorDate",
                 "committer", "committerDate", "committerDateTime",
                 "parents", "children", "repoDir", "subCommits")

    def __init__(self, sha1="", comments="",
                 author="", authorDate="",
                 committer="", committerDate="",
                 parents=[]):

        self.sha1 = sha1
        self.comments = comments
        self.author = author
        self.authorDate = authorDate
        self.committer = committer
        self.committerDate = committerDate
        self.committerDateTime: datetime = None
        self.parents: List[str] = parents
        self.children: List[Commit] = None
        self.repoDir: str = None
        self.subCommits: List[Commit] = []

    def __str__(self):
        return "Commit: {0}\n"  \
               "Author: {1} {2}\n"  \
               "Committer: {3} {4}\n\n"    \
               "{5}".format(self.sha1,
                            self.author, self.authorDate,
                            self.committer, self.committerDate,
                            self.comments)

    @classmethod
    def fromRawString(cls, string: str):
        parts = str_split(string, "\x01")
        if len(parts) != 7:
            return None

        sha1 = parts[0]
        comments = str_strip(parts[1], "\n")
        author = parts[2]
        authorDate = parts[3]
        committer = parts[4]
        committerDate = parts[5]
        parents = [x for x in str_split(parts[6], " ") if x]

        return cls(sha1, comments, author, authorDate,
                   committer, committerDate, parents)

    def isValid(self):
        return len(self.sha1) > 0


class MyProfile():

    def __init__(self):
        self.pr = cProfile.Profile()
        self.pr.enable()

    def __del__(self):
        self.pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(self.pr, stream=s).sort_stats("cumulative")
        ps.print_stats()
        print(s.getvalue())


class MyLineProfile():
    def __init__(self, func):
        from line_profiler import LineProfiler
        self.pr = LineProfiler(func)
        self.pr.enable_by_count()

    def __del__(self):
        self.pr.disable_by_count()
        self.pr.print_stats()


class FindField():

    AddOrDel = 0
    Changes = 1
    Comments = 2
    # for highlight only
    All = 0xff

    @staticmethod
    def isDiff(field):
        return field == FindField.AddOrDel or \
            field == FindField.Changes


class FindParameter():

    def __init__(self, range: range, pattern: str, field: FindField, flag):
        self.range = range
        self.pattern = pattern
        self.field = field
        self.flag = flag

    def __eq__(self, other):
        if not other:
            return False

        if self.field != other.field:
            return False
        if self.flag != other.flag:
            return False
        if self.pattern != other.pattern:
            return False
        # ignore range compare
        return True


# refer to find type combobox
FIND_EXTACT = 0
FIND_IGNORECASE = 1
FIND_REGEXP = 2

FIND_NOTFOUND = -1
FIND_CANCELED = -2


def htmlEscape(text):
    return "".join(html_escape_table.get(c, c) for c in text)


def _fix_data(data, encoding):
    if data[0] == 0x00 and encoding == "utf-16le":
        data = data[1:]
    elif data[-1] == 0x00 and encoding == "utf-16be":
        data = data[:-1]

    return data


def decodeFileData(data, preferEncoding="utf-8"):
    if not data:
        return data.decode("utf-8"), "utf-8"

    try:
        data = _fix_data(data, preferEncoding)
        return data.decode(preferEncoding), preferEncoding
    except UnicodeDecodeError:
        pass

    encodings = ["utf-8", "gb18030", "utf16"]
    if preferEncoding in encodings:
        encodings.remove(preferEncoding)

    # try the prefer encodings first
    for e in encodings:
        try:
            data = _fix_data(data, e)
            return data.decode(e), e
        except UnicodeDecodeError:
            pass

    # try the buggy chardet
    encoding = chardet.detect(data)["encoding"]
    if encoding and encoding not in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            pass

    # the last chance
    logger.warning(b"Warning: can't decode '%s'" % data)
    return data.decode(preferEncoding, "replace"), None


def appDirPath():
    # qApp.applicationDirPath not works as expected
    path = os.path.realpath(__file__)
    return os.path.dirname(path)


def dataDirPath():
    return appDirPath() + "/data"


def isXfce4():
    keys = ["XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP"]
    for key in keys:
        if key in os.environ:
            v = os.environ[key]
            if v:
                return v == "XFCE"

    return False


def attachConsole():
    if os.name != "nt":
        return

    import ctypes
    import sys

    import psutil

    STD_OUTPUT_HANDLE = -11
    std_out_handle = ctypes.windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    if std_out_handle > 0:
        return

    try:
        # first parent must be qgitc itself
        p = psutil.Process(os.getppid()).parent()
        if ctypes.windll.kernel32.AttachConsole(p.pid):
            conout = open('CONOUT$', 'w')
            sys.stdout = conout
            sys.stderr = conout
            sys.stdin = open("CONIN$", "r")
    except:
        pass


def fileRealCommit(filePath: str, commit: Commit):
    if not commit.repoDir:
        return commit
    if filePath.startswith(commit.repoDir.replace("\\", "/")):
        return commit
    for subCommit in commit.subCommits:
        if filePath.startswith(subCommit.repoDir.replace("\\", "/")):
            return subCommit
    # filePath isn't in any subCommit
    if commit.repoDir == ".":
        return commit
    assert False, "No commit found for file: " + filePath


def fullRepoDir(repoDir: str, branchDir: str = None):
    if not repoDir or repoDir == ".":
        return branchDir or Git.REPO_DIR
    return os.path.join(branchDir or Git.REPO_DIR, repoDir)


def commitRepoDir(commit: Commit):
    return fullRepoDir(commit.repoDir)


def _isArgNeedValue(arg: str):
    if arg.find('=') != -1:
        return False
    if len(arg) == 2 and arg[1] == '-':
        return False
    known_args = [
        "--decorate-refs", "--decorate-refs-exclude",
        "--max-count", "--skip", "--since", "--after", "--until", "--before",
        "--author", "--committer", "--grep-reflog", "--grep",
        "--min-parents", "--max-parents", "--glob", "--exclude",
        "--format", "--encoding", "--date"
        # "--branches", "--tags", "--remotes"
    ]
    return arg in known_args


def isRevisionRange(arg: str):
    if arg.startswith("origin") or arg.startswith("HEAD"):
        return True
    if ".." in arg or "^" in arg or "~" in arg:
        return True
    if arg.startswith("refs/"):
        return True
    m = sha1_re.match(arg)
    if m:
        return True
    return False


def extractFilePaths(args: List[str]):
    paths = []
    if not args:
        return paths

    for arg in reversed(args):
        if arg.startswith("-"):
            if paths and _isArgNeedValue(arg):
                del paths[0]
            break
        paths.insert(0, arg)

    new_paths = []
    for path in paths:
        if not isRevisionRange(path):
            new_paths.append(path)

    return new_paths


def _selectSubmodule(submodules: List[str], path: str):
    assert submodules and path

    for submodule in submodules:
        normalized = os.path.normpath(os.path.normcase(submodule))
        if path.startswith(normalized):
            return submodule
    return None


def _pathStartsWith(path: str, prefix: str):
    path = os.path.normcase(path)
    prefix = os.path.normcase(prefix)
    return path.startswith(prefix)


def toSubmodulePath(submodule: str, path: str):
    if not submodule or submodule == ".":
        return path

    repoDir = os.path.normpath(Git.REPO_DIR)
    normalized_path = os.path.normpath(path)
    if _pathStartsWith(normalized_path, repoDir):
        normalized_path = normalized_path[len(repoDir)+1:]

    normalized_submodule = os.path.normpath(submodule)
    if _pathStartsWith(normalized_path, normalized_submodule):
        return normalized_path[len(submodule) + 1:]
    return path


def filterSubmoduleByPath(submodules: List[str], paths: List[str]):
    if not paths or not submodules:
        return submodules

    result = []
    repoDir = os.path.normpath(os.path.normcase(Git.REPO_DIR))
    for path in paths:
        normalized = os.path.normpath(os.path.normcase(path))
        if normalized.startswith(repoDir):
            normalized = normalized[len(repoDir)+1:]
        submodule = _selectSubmodule(submodules, normalized)
        if submodule:
            result.append(submodule)
        elif not os.path.isabs(path):
            # the path can be in specific submodule, or in the main repo
            # we can't determine it, so return all submodules
            return submodules
        elif "." in submodules:
            # treat it as in the main repo
            result.append(".")
    return result


def makeRepoName(repoDir: str):
    index = repoDir.rfind(os.sep)
    # submodule returns '/' on windows
    if index == -1 and os.sep == '\\':
        index = repoDir.rfind('/')
    if index != -1:
        repoDir = repoDir[index + 1:]
    if repoDir == ".":
        repoDir = "<main>"
    return repoDir

def _findInlineSpan(text: str, currentPos: int, c: str):
    i = currentPos
    # found a backtick
    length = 0
    pos = i

    if i != 0 and text[i - 1] == '\\':
        return currentPos, None

    # keep moving forward in backtick sequence;
    while pos < len(text) and text[pos] == c:
        length += 1
        pos += 1

    seq = text[i:i+length]
    start = i
    i += length
    next = text.find(seq, i)
    if next == -1:
        return currentPos, None

    if next + length < len(text) and text[next + length] == c:
        return currentPos, None

    return next + length, (start, next - start + length)


def findInlineSpans(text: str):
    i = 0
    while i < len(text):
        currentChar = text[i]
        if currentChar == '`':
            i, span = _findInlineSpan(text, i, currentChar)
            if span:
                yield span
        i += 1
