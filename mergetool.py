# -*- coding: utf-8 -*-


class MergeTool:
    Nothing = 0x0
    CanDiff = 0x1
    CanMerge = 0x2
    Both = CanDiff | CanMerge

    def __init__(self, capabilities=Nothing, suffix="", command=""):
        self._caps = capabilities
        self._suffix = suffix
        self._command = command

    @property
    def capabilities(self):
        return self._caps

    @capabilities.setter
    def capabilities(self, capabilities):
        self._caps = capabilities

    @property
    def suffix(self):
        return self._suffix

    @suffix.setter
    def suffix(self, s):
        self._suffix = s

    @property
    def command(self):
        return self._command

    @command.setter
    def command(self, cmd):
        self._command = cmd

    def isValid(self):
        return self.suffix and self.command

    def canDiff(self):
        return (self._caps & self.CanDiff) == self.CanDiff

    def canMerge(self):
        return (self._caps & self.CanMerge) == self.CanMerge
