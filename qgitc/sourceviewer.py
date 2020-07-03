# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QWidget,
    QApplication)
from PySide2.QtGui import (
    QFontMetrics,
    QTextOption)
from PySide2.QtCore import (
    Qt)

from .textline import SourceTextLineBase
from .stylehelper import dpiScaled
from .textviewer import TextViewer


__all__ = ["SourceViewer"]


class SourceTextLine(SourceTextLineBase):

    def __init__(self, text, font, option):
        super().__init__(text, font, option)

    def rehighlight(self):
        formats = self._commonHighlightFormats()
        if formats:
            self._layout.setAdditionalFormats(formats)


class SourceViewer(TextViewer):

    def __init__(self, parent=None):
        super().__init__(parent)

        settings = qApp.settings()
        self.updateFont(settings.diffViewFont())

        fm = QFontMetrics(self._font)
        tabstopWidth = fm.width(' ') * settings.tabSize()
        self._option.setTabStop(tabstopWidth)

        if settings.showWhitespace():
            flags = self._option.flags()
            self._option.setFlags(flags | QTextOption.ShowTabsAndSpaces)

        self._panel = None
        self._onePixel = dpiScaled(1)

        self.verticalScrollBar().valueChanged.connect(
            self._onVScrollBarValueChanged)

    def toTextLine(self, text):
        return SourceTextLine(text, self._font, self._option)

    def setPanel(self, panel):
        self._panel = panel
        if panel:
            self._updatePanelGeo()
        else:
            self.setViewportMargins(0, 0, 0, 0)

    @property
    def panel(self):
        return self._panel

    def _onVScrollBarValueChanged(self, value):
        if self._panel:
            self._panel.update()

    def _updatePanelGeo(self):
        if self._panel:
            rc = self.rect()
            width = self._panel.width()
            self.setViewportMargins(width + self._onePixel, 0, 0, 0)
            self._panel.setGeometry(rc.left() + self._onePixel,
                                    rc.top() + self._onePixel,
                                    width,
                                    self.viewport().height())

    def resizeEvent(self, event):
        if event.oldSize().height() != event.size().height():
            self._updatePanelGeo()
        super().resizeEvent(event)
