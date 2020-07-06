# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QApplication)
from PySide2.QtGui import (
    QFontMetrics,
    QTextOption)
from PySide2.QtCore import (
    QEvent)

from .textline import SourceTextLineBase
from .stylehelper import dpiScaled
from .textviewer import TextViewer

import re


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

        self._panel = None
        self._onePixel = dpiScaled(1)

        self.verticalScrollBar().valueChanged.connect(
            self._onVScrollBarValueChanged)

        settings = QApplication.instance().settings()
        settings.tabSizeChanged.connect(self.delayUpdateSettings)
        settings.showWhitespaceChanged.connect(self.delayUpdateSettings)
        settings.diffViewFontChanged.connect(self.delayUpdateSettings)

    def toTextLine(self, text):
        return SourceTextLine(text, self._font, self._option)

    def setPanel(self, panel):
        if self._panel:
            if panel != self._panel:
                self._panel.removeEventFilter(self)
            else:
                return

        self._panel = panel
        if panel:
            self._updatePanelGeo()
            panel.installEventFilter(self)
        else:
            self.setViewportMargins(0, 0, 0, 0)

    @property
    def panel(self):
        return self._panel

    def reloadSettings(self):
        settings = QApplication.instance().settings()

        self.updateFont(settings.diffViewFont())

        fm = QFontMetrics(self._font)
        tabSize = settings.tabSize()
        tabstopWidth = fm.width(' ') * tabSize

        self._option = QTextOption()
        self._option.setTabStop(tabstopWidth)

        if settings.showWhitespace():
            flags = self._option.flags()
            self._option.setFlags(flags | QTextOption.ShowTabsAndSpaces)

        pattern = settings.bugPattern()
        self._bugPattern = re.compile(pattern) if pattern else None

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

    def _reloadTextLine(self, textLine):
        # reload bugPattern
        super()._reloadTextLine(textLine)

        if isinstance(textLine, SourceTextLineBase):
            textLine.setDefOption(self._option)

        textLine.setFont(self._font)

    def resizeEvent(self, event):
        if event.oldSize().height() != event.size().height():
            self._updatePanelGeo()
        super().resizeEvent(event)

    def eventFilter(self, obj, event):
        if obj == self._panel and event.type() == QEvent.Resize:
            self._updatePanelGeo()
            return True

        return super().eventFilter(obj, event)
