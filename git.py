# -*- coding: utf-8 -*-

from collections import defaultdict

import subprocess
import os
import bisect

from common import log_fmt


class GitProcess():

    def __init__(self, repoDir, args):
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self._process = subprocess.Popen(
            ["git"] + args,
            cwd=repoDir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo)

    @property
    def process(self):
        return self._process

    @property
    def returncode(self):
        return self._process.returncode

    def communicate(self):
        return self._process.communicate()


class Ref():
    INVALID = -1
    TAG = 0
    HEAD = 1
    REMOTE = 2

    def __init__(self, type, name):
        self._type = type
        self._name = name

    def __str__(self):
        string = "type: {0}\n".format(self._type)
        string += "name: {0}".format(self._name)

        return string

    def __lt__(self, other):
        return self._type < other._type

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, type):
        self._type = type

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @classmethod
    def fromRawString(cls, string):
        if not string or len(string) < 46:
            return None

        sha1 = string[0:40]
        name = string[41:]

        if not name.startswith("refs/"):
            return None

        name = name[5:]

        _type = Ref.INVALID
        _name = None

        if name.startswith("heads/"):
            _type = Ref.HEAD
            _name = name[6:]
        elif name.startswith("remotes") \
                and not name.endswith("HEAD"):
            _type = Ref.REMOTE
            _name = name
        elif name.startswith("tags/"):
            _type = Ref.TAG
            if name.endswith("^{}"):
                _name = name[5:-3]
            else:
                _name = name[5:]
        else:
            return None

        return cls(_type, _name)


class Git():
    REPO_DIR = os.getcwd()
    REF_MAP = {}
    REV_HEAD = None

    @staticmethod
    def run(args):
        return GitProcess(Git.REPO_DIR, args)

    @staticmethod
    def checkOutput(args):
        process = Git.run(args)
        data = process.communicate()[0]
        if process.returncode != 0:
            return None

        return data

    @staticmethod
    def repoTopLevelDir(directory):
        """get top level repo directory
        if @directory is not a repository, None returned"""

        if not os.path.isdir(directory):
            return None
        if not os.path.exists(directory):
            return None

        args = ["rev-parse", "--show-toplevel"]
        process = GitProcess(directory, args)
        realDir = process.communicate()[0]
        if process.returncode != 0:
            return None

        return realDir.decode("utf-8").replace("\n", "")

    @staticmethod
    def refs():
        args = ["show-ref", "-d"]
        data = Git.checkOutput(args)
        if not data:
            return None
        lines = data.decode("utf-8").split('\n')
        refMap = defaultdict(list)

        for line in lines:
            ref = Ref.fromRawString(line)
            if not ref:
                continue

            sha1 = line[0:40]
            bisect.insort(refMap[sha1], ref)

        return refMap

    @staticmethod
    def revHead():
        args = ["rev-parse", "HEAD"]
        data = Git.checkOutput(args)
        if not data:
            return None

        return data.decode("utf-8").rstrip('\n')

    @staticmethod
    def branches():
        args = ["branch", "-a"]
        data = Git.checkOutput(args)
        if not data:
            return None

        return data.decode("utf-8").split('\n')

    @staticmethod
    def branchLogs(branch, pattern=None):
        args = ["log", "-z", "--topo-order",
                "--parents", "--boundary",
                "--no-color",
                "--pretty=format:{0}".format(log_fmt),
                branch]
        if pattern:
            args.append(pattern)

        data = Git.checkOutput(args)
        if not data:
            return None

        return data.decode("utf-8", "replace").split('\0')

    @staticmethod
    def commitSummary(sha1):
        fmt = "%h%x01%s%x01%ad%x01%an%x01%ae"
        args = ["show", "-s",
                "--pretty=format:{0}".format(fmt),
                "--date=short", sha1]

        data = Git.checkOutput(args)
        if not data:
            return None

        parts = data.decode("utf-8").split("\x01")

        return {"sha1": parts[0],
                "subject": parts[1],
                "date": parts[2],
                "author": parts[3],
                "email": parts[4]}

    @staticmethod
    def commitFiles(sha1):
        args = ["diff-tree", "--no-commit-id",
                "--name-only", "--root", "-r",
                "-z", "-C", "--cc",
                "--submodule", sha1]

        data = Git.checkOutput(args)
        if not data:
            return None

        return data.decode("utf-8")

    @staticmethod
    def commitRawDiff(sha1, filePath=None, gitArgs=None):
        args = ["diff-tree", "-r", "-p",
                "--textconv", "--submodule",
                "-C", "--cc", "--no-commit-id",
                "-U3", "--root", sha1]

        if gitArgs:
            args.extend(gitArgs)

        if filePath:
            args.append("--")
            args.append(filePath)

        data = Git.checkOutput(args)
        if not data:
            return None

        return data

    @staticmethod
    def externalDiff(commit, path=None):
        args = ["difftool",
                "{0}^..{0}".format(commit.sha1)]

        if path:
            args.append("--")
            args.append(path)

        process = Git.run(args)
