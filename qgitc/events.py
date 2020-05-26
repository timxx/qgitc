# -*- coding: utf-8 -*-

from PySide2.QtCore import QEvent


class BlameEvent(QEvent):

    Type = QEvent.User + 1

    def __init__(self, filePath, sha1=None):
        super().__init__(QEvent.Type(BlameEvent.Type))
        self.filePath = filePath
        self.sha1 = sha1
