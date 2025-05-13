# -*- coding: utf-8 -*-

import bisect
import logging
import os
import re
import subprocess
from collections import defaultdict
from typing import Dict, List, Union

logger = logging.getLogger(__name__)


class GitProcess():

    GIT_BIN = None

    def __init__(self, repoDir, args, text=None, env=None):
        creationflags = 0
        logger.debug(f"run {args} in {repoDir}")
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        self._process = subprocess.Popen(
            [GitProcess.GIT_BIN] + args,
            cwd=repoDir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            universal_newlines=text,
            env=env)

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
    def fromRawString(cls, string: str):
        if not string or len(string) < 46:
            return None

        name = string[41:]
        if not name.startswith("refs/"):
            return None

        name = name[5:]

        _type = Ref.INVALID
        _name = None

        if name.startswith("heads/"):
            _type = Ref.HEAD
            _name = name[6:]
        elif name.startswith("remotes/") \
                and not name.endswith("HEAD"):
            _type = Ref.REMOTE
            _name = name[8:]
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
    REPO_DIR = None
    REF_MAP = {}
    REV_HEAD = None

    # local uncommitted changes
    LUC_SHA1 = "0000000000000000000000000000000000000000"
    # local changes checked
    LCC_SHA1 = "0000000000000000000000000000000000000001"

    VERSION_MAJOR = 0
    VERSION_MINOR = 0
    VERSION_PATCH = 0

    @staticmethod
    def available():
        return GitProcess.GIT_BIN is not None

    @staticmethod
    def run(args, text=None, repoDir=None):
        return GitProcess(repoDir or Git.REPO_DIR, args, text)

    @staticmethod
    def checkOutput(args, text=None, repoDir=None) -> Union[bytes, str, None]:
        process = Git.run(args, text, repoDir)
        data, error = process.communicate()
        if process.returncode != 0:
            if not text:
                msg = error.decode("utf-8", errors="replace")
            else:
                msg = error
            logger.warning("git %s (%s)(%s)", " ".join(args),
                           msg.rstrip(), repoDir or Git.REPO_DIR)
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
    def commitSummary(sha1, repoDir=None):
        fmt = "%h%x01%s%x01%ad%x01%an%x01%ae"
        args = ["show", "-s",
                "--pretty=format:{0}".format(fmt),
                "--date=short", sha1]

        data = Git.checkOutput(args, repoDir=repoDir)
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
    def commitSubject(sha1, repoDir=None):
        args = ["show", "-s", "--pretty=format:%s", sha1]
        data = Git.checkOutput(args, repoDir=repoDir)

        return data

    @staticmethod
    def commitRawDiff(sha1, files=None, gitArgs=None, repoDir=None):
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

        if files:
            args.append("--")
            args.extend(files)

        data = Git.checkOutput(args, repoDir=repoDir)
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
                "--no-color"]
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
        with open(path, "r", encoding="utf-8") as f:
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
    def hasLocalChanges(cached=False, repoDir=None):
        args = ["diff", "--quiet", "-s"]
        if cached:
            args.append("--cached")
        if Git.versionGE(1, 7, 2):
            args.append("--ignore-submodules=dirty")

        process = GitProcess(repoDir, args)
        process.communicate()

        return process.returncode == 1

    @staticmethod
    def branchDir(branch, repoDir=None):
        """returned the branch directory if it checked out
        otherwise returned an empty string"""

        if not branch or branch.startswith("remotes/"):
            return ""

        # Use the repo dir directly
        # since we are unable to get two detached branch
        if branch.startswith("(HEAD detached"):
            return Git.REPO_DIR

        args = ["worktree", "list"]
        data = Git.checkOutput(args, repoDir=repoDir)
        if not data:
            return ""

        worktree_re = re.compile(
            r"(\S+)\s+[a-f0-9]+\s+(\[(\S+)\]|\(detached HEAD\))$")
        worktrees = data.rstrip(b'\n').decode("utf8").split('\n')

        for wt in worktrees:
            m = worktree_re.fullmatch(wt)
            if not m:
                logger.warning("Oops! Wrong format for worktree: %s", wt)
            elif m.group(3) == branch:
                return m.group(1)

        return ""

    @staticmethod
    def generateDiff(sha1, filePath, repoDir=None):
        data = Git.commitRawDiff(sha1, repoDir=repoDir)
        if not data:
            return False

        with open(filePath, "wb+") as f:
            f.write(data)

        return True

    @staticmethod
    def commitRawPatch(sha1, repoDir=None):
        args = ["format-patch", "-1", "--stdout", sha1]
        return Git.checkOutput(args, repoDir=repoDir)

    @staticmethod
    def generatePatch(sha1, filePath, repoDir=None):
        data = Git.commitRawPatch(sha1, repoDir=repoDir)
        if not data:
            return False

        with open(filePath, "wb+") as f:
            f.write(data)

        return True

    @staticmethod
    def revertCommit(branch, sha1, repoDir=None):
        branchDir = Git.branchDir(branch, repoDir)

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

        process = Git.run(args, True)
        data, _ = process.communicate()
        if process.returncode != 0 or not data:
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

    @staticmethod
    def userName():
        return Git.getConfigValue("user.name", False)

    @staticmethod
    def userEmail():
        return Git.getConfigValue("user.email", False)

    @staticmethod
    def initGit(gitBin: str):
        GitProcess.GIT_BIN = gitBin

        version: bytes = Git.checkOutput(["version"])
        if not version:
            return

        version_parts = version.strip().split()
        if len(version_parts) >= 3:
            version_number = version_parts[2]
            version_components = version_number.split(b'.')
            Git.VERSION_MAJOR = int(version_components[0]) if len(
                version_components) > 0 else 0
            Git.VERSION_MINOR = int(version_components[1]) if len(
                version_components) > 1 else 0
            Git.VERSION_PATCH = int(version_components[2]) if len(
                version_components) > 2 else 0

    @staticmethod
    def versionGE(major: int, minor: int, patch: int):
        if Git.VERSION_MAJOR > major:
            return True
        if Git.VERSION_MAJOR < major:
            return False

        if Git.VERSION_MINOR > minor:
            return True
        if Git.VERSION_MINOR < minor:
            return False

        return Git.VERSION_PATCH >= patch

    @staticmethod
    def restoreStagedFiles(repoDir, files):
        """restore staged files
        return error message if any
        """
        # `restore --staged` is much slower than reset HEAD
        args = ["reset", "HEAD", "--"]
        args.extend(files)
        process = GitProcess(repoDir or Git.REPO_DIR, args)
        _, error = process.communicate()
        if process.returncode != 0 and error is not None:
            return error.decode("utf-8")
        return None

    @staticmethod
    def restoreFiles(repoDir, files, staged=False):
        """restore files
        return error message if any
        """
        if staged:
            error = Git.restoreStagedFiles(repoDir, files)
            if error:
                return error

        args = ["restore", "--"]
        args.extend(files)
        process = GitProcess(repoDir or Git.REPO_DIR, args)
        _, error = process.communicate()
        if process.returncode != 0 and error is not None:
            return error.decode("utf-8")

        return None

    @staticmethod
    def restoreRepoFiles(repoFiles: Dict[str, List[str]], staged=False, branchDir=None):
        for repoDir, files in repoFiles.items():
            fullRepoDir = repoDir or branchDir
            if repoDir and repoDir != ".":
                fullRepoDir = os.path.join(branchDir or Git.REPO_DIR, repoDir)
            error = Git.restoreFiles(
                fullRepoDir or Git.REPO_DIR, files, staged)
            if error:
                return error
        return None

    @staticmethod
    def addFiles(repoDir, files):
        """add files to the index
        return error message if any
        """
        args = ["add", "-f", "--"]
        args.extend(files)
        process = GitProcess(repoDir or Git.REPO_DIR, args)
        _, error = process.communicate()
        if process.returncode != 0 and error is not None:
            return error.decode("utf-8")

        return None

    @staticmethod
    def status(repoDir=None, showUntracked=True, showIgnored=False, nullFormat=True):
        args = ["status", "--porcelain"]
        args.append("--untracked-files={}".format(
            "all" if showUntracked else "no"))
        if showIgnored:
            args.append("--ignored")
        if Git.versionGE(1, 7, 2):
            args.append("--ignore-submodules=dirty")
        if nullFormat:
            args.append("-z")
        data = Git.checkOutput(args, repoDir=repoDir)
        if not data:
            return None

        return data

    @staticmethod
    def commit(message: str, amend: bool = False, repoDir: str = None, date: str = None):
        args = ["commit", "--no-edit"]
        if amend:
            args.append("--amend")
        env = None
        if date:
            args.append("--date={}".format(date))
            env = os.environ.copy()
            env["GIT_COMMITTER_DATE"] = date

        if message:
            args.append("-m")
            args.append(message)
        process = GitProcess(repoDir or Git.REPO_DIR, args, env=env)
        out, error = process.communicate()
        if out is not None:
            out = out.decode("utf-8")
        if error is not None:
            error = error.decode("utf-8")
        return out, error

    @staticmethod
    def activeBranch(repoDir=None):
        args = ["rev-parse", "--abbrev-ref", "HEAD"]
        data = Git.checkOutput(args, repoDir=repoDir)
        if data:
            return data.rstrip(b'\n').decode("utf-8")
        return ""

    @staticmethod
    def commitMessage(sha1, repoDir=None):
        args = ["log", "-1", "--pretty=format:%B", sha1]
        data = Git.checkOutput(args, repoDir=repoDir)
        if data:
            return data.rstrip().decode("utf-8")
        return ""

    @staticmethod
    def isShallowRepo(repoDir=None):
        if Git.versionGE(2, 15, 0):
            args = ["rev-parse", "--is-shallow-repository"]
            data = Git.checkOutput(args, text=True, repoDir=repoDir)
            if data:
                return data.strip() == "true"
            return False
        else:
            # TODO: support worktree?
            shallowFile = os.path.join(
                repoDir or Git.REPO_DIR, ".git", "shallow")
            return os.path.exists(shallowFile)
