# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QPainter
from PySide6.QtCore import QPoint

class ToggleImageButton(QPushButton):

    def __init__(self, imageOff, imageOn, parent=None):
        super().__init__(parent)
        self._onImage = imageOn
        self._offImage = imageOff
        self.setCheckable(True)

    def setOnImage(self, image):
        self._onImage = image
        self.update()

    def setOffImage(self, image):
        self._offImage = image
        self.update()

    def paintEvent(self, event):
        image = self._onImage if self.isChecked() else self._offImage
        if image is None or image.isNull():
            return
        painter = QPainter(self)
        painter.drawImage(QPoint(0, 0), image)
