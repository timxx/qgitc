# -*- coding: utf-8 -*-


__all__ = ["TextCursor"]


class TextCursor():

    def __init__(self, viewer=None):
        self.clear()
        self._viewer = viewer

    def __eq__(self, other):
        return self._beginLine == other._beginLine and \
            self._beginPos == other._beginPos and \
            self._endLine == other._endLine and \
            self._endPos == other._endPos

    def __lt__(self, other):
        if self.beginLine() < other.beginLine():
            return True
        elif self.beginLine() > other.beginLine():
            return False
        else:
            return self.beginPos() < other.beginPos()

    def clear(self):
        self._beginLine = -1
        self._beginPos = -1
        self._endLine = -1
        self._endPos = -1

    def isValid(self):
        return self._beginLine != -1 and \
            self._endLine != -1 and \
            self._beginPos != -1 and \
            self._endPos != -1

    def hasMultiLines(self):
        if not self.isValid():
            return False

        return self._beginLine != self._endLine

    def hasSelection(self):
        if not self.isValid():
            return False

        if self.hasMultiLines():
            return True
        return self._beginPos != self._endPos

    def within(self, line):
        if not self.hasSelection():
            return False

        if line >= self.beginLine() and line <= self.endLine():
            return True

        return False

    def beginLine(self):
        return min(self._beginLine, self._endLine)

    def endLine(self):
        return max(self._beginLine, self._endLine)

    def beginPos(self):
        if self._beginLine == self._endLine:
            return min(self._beginPos, self._endPos)
        elif self._beginLine < self._endLine:
            return self._beginPos
        else:
            return self._endPos

    def endPos(self):
        if self._beginLine == self._endLine:
            return max(self._beginPos, self._endPos)
        elif self._beginLine < self._endLine:
            return self._endPos
        else:
            return self._beginPos

    def moveTo(self, line, pos):
        self._beginLine = line
        self._beginPos = pos
        self._endLine = line
        self._endPos = pos

    def selectTo(self, line, pos):
        self._endLine = line
        self._endPos = pos

    def selectedText(self):
        if not self._viewer or not self.hasSelection():
            return None

        beginLine = self.beginLine()
        beginPos = self.beginPos()
        endLine = self.endLine()
        endPos = self.endPos()

        # only one line
        if beginLine == endLine:
            textLine = self._viewer.textLineAt(beginLine)
            text = textLine.text()[beginPos:endPos]
        else:
            # first line
            textLine = self._viewer.textLineAt(beginLine)
            text = textLine.text()[beginPos:]
            text += ('\r\n' if textLine.hasCR() else '\n')

            # middle lines
            for i in range(beginLine + 1, endLine):
                textLine = self._viewer.textLineAt(i)
                text += textLine.text()
                text += ('\r\n' if textLine.hasCR() else '\n')

            # last line
            textLine = self._viewer.textLineAt(endLine)
            text += textLine.text()[:endPos]

        return text

    def selectPreviousChar(self):
        if not self._viewer.hasTextLines():
            return

        if self._endPos == 0:
            if self._endLine > 0:
                self._endLine -= 1
                text = self._viewer.textLineAt(self._endLine).text()
                self._endPos = len(text)
        else:
            self._endPos -= 1

    def selectNextChar(self):
        if not self._viewer.hasTextLines():
            return

        text = self._viewer.textLineAt(self._endLine).text()
        if len(text) == 0 or self._endPos == len(text):
            if (self._endLine + 1) < self._viewer.textLineCount():
                self._endLine += 1
                self._endPos = 0
        else:
            self._endPos += 1

    def selectNextLine(self):
        if not self._viewer.hasTextLines():
            return

        if (self._endLine + 1) < self._viewer.textLineCount():
            self._endLine += 1
        else:
            self._endPos = len(self._viewer.textLineAt(self._endLine).text())

    def selectPreviousLine(self):
        if not self._viewer.hasTextLines():
            return

        if self._endLine > 0:
            self._endLine -= 1
        else:
            self._endPos = 0