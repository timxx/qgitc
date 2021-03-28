# -*- coding: utf-8 -*-

from collections import defaultdict

import subprocess
import os
import bisect
import re

from .common import log_fmt


class GitProcess():

    GIT_BIN = None

    def __init__(self, repoDir, args, text=None):
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self._process = subprocess.Popen(
            [GitProcess.GIT_BIN] + args,
            cwd=repoDir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            universal_newlines=text)

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
    REPO_TOP_DIR = os.getcwd()
    REF_MAP = {}
    REV_HEAD = None

    # local uncommitted changes
    LUC_SHA1 = "0000000000000000000000000000000000000000"
    # local changes checked
    LCC_SHA1 = "0000000000000000000000000000000000000001"

    @staticmethod
    def available():
        return GitProcess.GIT_BIN is not None

    @staticmethod
    def run(args, text=None):
        return GitProcess(Git.REPO_DIR, args, text)

    @staticmethod
    def checkOutput(args, text=None):
        process = Git.run(args, text)
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
    def abbrevCommit(sha1):
        args = ["show", "-s", "--pretty=format:%h", sha1]
        data = Git.checkOutput(args)
        if not data:
            return sha1[:7]
        return data.rstrip().decode("utf-8")

    @staticmethod
    def commitSubject(sha1):
        args = ["show", "-s", "--pretty=format:%s", sha1]
        data = Git.checkOutput(args)

        return data

    @staticmethod
    def commitRawDiff(sha1, filePath=None, gitArgs=None):
        if sha1 == Git.LCC_SHA1:
            args = ["diff-index", "--cached", "HEAD"]
        elif sha1 == Git.LUC_SHA1:
            args = ["diff-files"]
        else:
            args = ["diff-tree", "-r", "--root", sha1]

        args.extend(["-p", "--textconv", "--submodule",
                     "-C", "--cc", "--no-commit-id", "-U3"])

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
    def externalDiff(branchDir, commit, path=None, tool=None):
        args = ["difftool", "--no-prompt"]
        if commit.sha1 == Git.LUC_SHA1:
            pass
        elif commit.sha1 == Git.LCC_SHA1:
            args.append("--cached")
        else:
            args.append("{0}^..{0}".format(commit.sha1))

        if tool:
            args.append("--tool={}".format(tool))

        if path:
            args.append("--")
            args.append(path)

        cwd = branchDir if branchDir else Git.REPO_DIR
        process = GitProcess(cwd, args)

    @staticmethod
    def conflictFiles():
        args = ["diff", "--name-only",
                "--diff-filter=U",
                "-no-color"]
        data = Git.checkOutput(args)
        if not data:
            return None
        return data.rstrip(b'\n').decode("utf-8").split('\n')

    @staticmethod
    def gitDir():
        args = ["rev-parse", "--git-dir"]
        data = Git.checkOutput(args)
        if not data:
            return None

        return data.rstrip(b'\n').decode("utf-8")

    @staticmethod
    def gitPath(name):
        dir = Git.gitDir()
        if not dir:
            return None
        if dir[-1] != '/' and dir[-1] != '\\':
            dir += '/'

        return dir + name

    @staticmethod
    def mergeBranchName():
        """return the current merge branch name"""
        # TODO: is there a better way?
        path = Git.gitPath("MERGE_MSG")
        if not os.path.exists(path):
            return None

        name = None
        with open(path, "r") as f:
            line = f.readline()
            m = re.match("Merge.* '(.*)'.*", line)
            if m:
                name = m.group(1)

        # likely a sha1
        if name and re.match("[a-f0-9]{7,40}", name):
            data = Git.checkOutput(["branch", "--remotes",
                                    "--contains", name])
            if data:
                data = data.rstrip(b'\n')
                if data:
                    # might have more than one branch
                    name = data.decode("utf-8").split('\n')[0].strip()

        return name

    @staticmethod
    def resolveBy(ours, path):
        args = ["checkout",
                "--ours" if ours else "--theirs",
                path]
        process = Git.run(args)
        process.communicate()
        if process.returncode != 0:
            return False

        args = ["add", path]
        process = Git.run(args)
        process.communicate()
        return True if process.returncode == 0 else False

    @staticmethod
    def undoMerge(path):
        """undo a merge on the @path"""
        if not path:
            return False

        args = ["checkout", "-m", path]
        process = Git.run(args)
        process.communicate()

        return process.returncode == 0

    @staticmethod
    def hasLocalChanges(branch, cached=False):
        # A remote branch should never have local changes
        if branch.startswith("remotes/"):
            return False

        dir = Git.branchDir(branch)
        # only branch checked out can have local changes
        if not dir:
            return False

        args = ["diff", "--quiet"]
        if cached:
            args.append("--cached")

        process = GitProcess(dir, args)
        process.communicate()

        return process.returncode == 1

    @staticmethod
    def branchDir(branch):
        """returned the branch directory if it checked out
        otherwise returned an empty string"""

        if not branch or branch.startswith("remotes/"):
            return ""

        # Use the repo dir directly
        # since we are unable to get two detached branch
        if branch.startswith("(HEAD detached"):
            return Git.REPO_DIR

        args = ["worktree", "list"]
        data = Git.checkOutput(args)
        if not data:
            return ""

        worktree_re = re.compile(
            r"(\S+)\s+[a-f0-9]+\s+(\[(\S+)\]|\(detached HEAD\))$")
        worktrees = data.rstrip(b'\n').decode("utf8").split('\n')

        for wt in worktrees:
            m = worktree_re.fullmatch(wt)
            if not m:
                print("Oops! Wrong format for worktree:", wt)
            elif m.group(3) == branch:
                return m.group(1)

        return ""

    @staticmethod
    def generateDiff(sha1, filePath):
        data = Git.commitRawDiff(sha1)
        if not data:
            return False

        with open(filePath, "wb+") as f:
            f.write(data)

        return True

    @staticmethod
    def generatePatch(sha1, filePath):
        args = ["format-patch", "-1", "--stdout", sha1]

        data = Git.checkOutput(args)
        if not data:
            return False

        with open(filePath, "wb+") as f:
            f.write(data)

        return True

    @staticmethod
    def revertCommit(branch, sha1):
        branchDir = Git.branchDir(branch)

        args = ["revert", "--no-edit", sha1]
        process = GitProcess(branchDir, args)
        _, error = process.communicate()
        if process.returncode != 0 and error is not None:
            error = error.decode("utf-8")

        return process.returncode, error

    @staticmethod
    def resetCommitTo(branch, sha1, method):
        branchDir = Git.branchDir(branch)
        args = ["reset", "--" + method, sha1]
        process = GitProcess(branchDir, args)
        _, error = process.communicate()
        if process.returncode != 0 and error is not None:
            error = error.decode("utf-8")

        return process.returncode, error

    @staticmethod
    def repoUrl():
        args = ["config", "remote.origin.url"]
        data = Git.checkOutput(args)
        if data:
            return data.rstrip(b'\n').decode("utf-8")
        return ""

    @staticmethod
    def runWithError(args):
        process = Git.run(args)
        _, error = process.communicate()
        if process.returncode != 0 and error is not None:
            error = error.decode("utf-8")

        return process.returncode, error

    @staticmethod
    def setConfigValue(key, value, isGlobal=True):
        if not key:
            return 0, None

        args = ["config"]
        if isGlobal:
            args.append("--global")
        args.append(key)
        if value:
            args.append(value)
        else:
            args.insert(1, "--unset")

        return Git.runWithError(args)

    @staticmethod
    def removeSection(section, isGlobal=True):
        if not section:
            return 0, None

        args = ["config"]
        if isGlobal:
            args.append("--global")

        args.append("--remove-section")
        args.append(section)

        return Git.runWithError(args)

    @staticmethod
    def setDiffTool(name, cmd, isGlobal=True):
        if not name:
            return 0, None

        if not cmd:
            Git.removeSection("difftool.%s" % name)
            # treat as OK
            return 0, None

        key = "difftool.%s.cmd" % name
        return Git.setConfigValue(key, cmd, isGlobal)

    @staticmethod
    def setMergeTool(name, cmd, isGlobal=True):
        if not name:
            return 0, None

        if not cmd:
            Git.removeSection("mergetool.%s" % name)
            return 0, None

        key = "mergetool.%s.cmd" % name
        ret, error = Git.setConfigValue(key, cmd, isGlobal)
        if ret != 0:
            return ret, error

        key = "mergetool.%s.trustExitCode" % name
        return Git.setConfigValue(key, "true", isGlobal)

    @staticmethod
    def getConfigValue(key, isGlobal=True):
        if not key:
            return ""

        args = ["config", "--get", key]
        if isGlobal:
            args.insert(1, "--global")

        data = Git.checkOutput(args, True)
        if data is None:
            return ""

        return data.rstrip("\n")

    @staticmethod
    def diffToolCmd(name, isGlobal=True):
        if not name:
            return ""

        return Git.getConfigValue("difftool.%s.cmd" % name)

    @staticmethod
    def mergeToolCmd(name, isGlobal=True):
        if not name:
            return ""

        return Git.getConfigValue("mergetool.%s.cmd" % name)
