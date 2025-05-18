# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent
from PySide6.QtGui import QFontMetrics, QTextOption
from PySide6.QtWidgets import QApplication

from qgitc.textline import SourceTextLineBase
from qgitc.textviewer import TextViewer

__all__ = ["SourceViewer"]


class SourceTextLine(SourceTextLineBase):

    def __init__(self, text, font, option):
        super().__init__(text, font, option)

    def rehighlight(self):
        formats = self._commonHighlightFormats()
        if formats:
            self._layout.setFormats(formats)


class SourceViewer(TextViewer):

    def __init__(self, parent=None):
        self._margin = 0
        self._blockEventFilter = False
        self._panel = None

        super().__init__(parent)

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
            self.setViewportMargins(
                self._margin, self._margin, self._margin, self._margin)

    @property
    def panel(self):
        return self._panel

    def reloadSettings(self):
        settings = QApplication.instance().settings()

        self.updateFont(settings.diffViewFont())

        fm = QFontMetrics(self._font)
        tabSize = settings.tabSize()
        tabstopWidth = fm.horizontalAdvance(' ') * tabSize

        self._option = QTextOption()
        self._option.setTabStopDistance(tabstopWidth)

        if settings.showWhitespace():
            flags = self._option.flags()
            self._option.setFlags(flags | QTextOption.ShowTabsAndSpaces)

        self._bugPatterns = TextViewer.reloadBugPattern()

    def _onVScrollBarValueChanged(self, value):
        if self._panel:
            self._panel.update()

    def _updatePanelGeo(self):
        if self._panel:
            rc = self.rect()
            width = self._panel.width()
            self.setViewportMargins(
                width + 1, self._margin, self._margin, self._margin)
            self._panel.setGeometry(rc.left() + 1,
                                    rc.top() + 1,
                                    width,
                                    self.viewport().height() + self._margin * 2)

    def _reloadTextLine(self, textLine):
        # reload bugPattern
        super()._reloadTextLine(textLine)

        if isinstance(textLine, SourceTextLineBase):
            textLine.setDefOption(self._option)

        textLine.setFont(self._font)

    def resizeEvent(self, event):
        if event.oldSize().height() != event.size().height():
            self._blockEventFilter = True
            self._updatePanelGeo()
            self._blockEventFilter = False
        super().resizeEvent(event)

    def eventFilter(self, obj, event):
        if not self._blockEventFilter and \
                obj == self._panel and \
                event.type() == QEvent.Resize:
            self._updatePanelGeo()
            return True

        return super().eventFilter(obj, event)

    def setTextMargins(self, margin):
        self._margin = margin
        return super().setTextMargins(margin)
