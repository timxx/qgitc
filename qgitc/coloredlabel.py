# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QLabel


class ColoredLabel(QLabel):

    def __init__(self, colorSchema: str, parent=None):
        super().__init__(parent)
        self._colorSchema: str = colorSchema
        self._updatePalette()

    def _updatePalette(self):
        palette = self.palette()
        role = self.foregroundRole()
        color = getattr(qApp.colorSchema(), self._colorSchema)
        palette.setColor(role, color)
        self.setPalette(palette)

    def event(self, evt):
        if evt.type() == QEvent.PaletteChange:
            self._updatePalette()
        return super().event(evt)
