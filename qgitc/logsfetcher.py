# -*- coding: utf-8 -*-

from PySide6.QtCore import (
    Signal
)

from .common import Commit
from .datafetcher import DataFetcher


log_fmt = "%H%x01%B%x01%an <%ae>%x01%ai%x01%cn <%ce>%x01%ci%x01%P"


class LogsFetcher(DataFetcher):

    logsAvailable = Signal(list)

    def __init__(self, parent=None):
        super(LogsFetcher, self).__init__(parent)
        self.separator = b'\0'

    def parse(self, data):
        logs = data.rstrip(self.separator) \
            .decode("utf-8", "replace") \
            .split('\0')
        commits = [Commit.fromRawString(log) for log in logs]
        self.logsAvailable.emit(commits)

    def makeArgs(self, args):
        branch = args[0]
        logArgs = args[1]

        if branch and branch.startswith("(HEAD detached"):
            branch = None

        git_args = ["log", "-z", "--topo-order",
                    "--parents",
                    "--no-color",
                    "--pretty=format:{0}".format(log_fmt)]
        if branch:
            git_args.append(branch)

        if logArgs:
            git_args.extend(logArgs)
        else:
            git_args.append("--boundary")

        return git_args

    def isLoading(self):
        return self.process is not None
