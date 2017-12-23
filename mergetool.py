# -*- coding: utf-8 -*-


class MergeTool:

    def __init__(self, enabled=False, suffix="", command=""):
        self._enabled = enabled
        self._suffix = suffix
        self._command = command

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, b):
        self._enabled = b

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
