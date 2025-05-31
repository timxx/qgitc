# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QLabel

from qgitc.applicationbase import ApplicationBase


class ColoredLabel(QLabel):

    def __init__(self, colorSchema: str, parent=None):
        super().__init__(parent)
        self._colorSchema: str = colorSchema
        self._updatePalette()

    def _updatePalette(self):
        palette = self.palette()
        role = self.foregroundRole()
        if self._colorSchema:
            color = getattr(ApplicationBase.instance(
            ).colorSchema(), self._colorSchema)
        else:
            # Fallback to default color schema
            color = ApplicationBase.instance().palette().color(role)
        palette.setColor(role, color)
        self.setPalette(palette)

    def setColorSchema(self, colorSchema: str):
        if self._colorSchema != colorSchema:
            self._colorSchema = colorSchema
            self._updatePalette()

    def event(self, evt):
        if evt.type() == QEvent.PaletteChange:
            self._updatePalette()
        return super().event(evt)
