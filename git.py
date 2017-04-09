# -*- coding: utf-8 -*-

import subprocess
import os

from common import log_fmt


class GitProcess():

    def __init__(self, repoDir, args):
        self._process = subprocess.Popen(
            ["git"] + args,
            cwd=repoDir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

    @property
    def process(self):
        return self._process

    @property
    def returncode(self):
        return self._process.returncode

    def communicate(self):
        return self._process.communicate()


class Git():
    REPO_DIR = os.getcwd()

    @staticmethod
    def run(args):
        return GitProcess(Git.REPO_DIR, args)

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
    def branches():
        args = ["branch", "-a"]
        process = Git.run(args)
        data = process.communicate()[0]
        if process.returncode != 0:
            return None

        return data.decode("utf-8").split('\n')

    @staticmethod
    def branchLogs(branch, pattern=None):
        args = ["log", "-z",
                "--pretty=format:{0}".format(log_fmt),
                branch]
        if pattern:
            args.append(pattern)

        process = Git.run(args)
        data = process.communicate()[0]
        if process.returncode != 0:
            return None

        return data.decode("utf-8", "replace").split('\0')

    @staticmethod
    def commitSummary(sha1):
        fmt = "%h%x01%s%x01%ad%x01%an%x01%ae"
        args = ["show", "-s",
                "--pretty=format:{0}".format(fmt),
                "--date=short", sha1]

        process = Git.run(args)
        data = process.communicate()[0]
        if process.returncode != 0:
            return None
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

        process = Git.run(args)
        data = process.communicate()[0]
        if process.returncode != 0:
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

        process = Git.run(args)
        data = process.communicate()[0]
        if process.returncode != 0:
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
