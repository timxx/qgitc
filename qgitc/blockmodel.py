# -*- coding: utf-8 -*-
"""Foldable block model for TextViewer.

Decouples two concerns from drawing:

- block bookkeeping: contiguous line ranges that can be folded, possibly
  nested;
- geometry: mapping between logical line numbers and pixel Y positions,
  where folded (hidden) lines occupy no space and a line may span
  multiple visual rows (word wrap).

Nothing here depends on Qt so the logic stays unit-testable. Line numbers
are logical: folding never changes them.
"""

import bisect

__all__ = ["Block", "BlockModel"]


class Block:
    """A foldable range of logical lines.

    The anchor (startLine) stays visible when folded; lines
    (startLine, endLine] are hidden.
    """

    def __init__(self, startLine, endLine, meta=None, parent=None):
        self.startLine = startLine
        self.endLine = endLine
        self.meta = meta if meta is not None else {}
        self.parent = parent
        self.folded = False
        self.children = []
        if parent is not None:
            parent.children.append(self)

    @property
    def anchorLine(self):
        return self.startLine

    def isTopLevel(self):
        return self.parent is None

    def containsLine(self, lineNo):
        return self.startLine <= lineNo <= self.endLine

    def coversLines(self, lineNo):
        """True if lineNo is hidden when this block is folded."""
        return self.startLine < lineNo <= self.endLine


class BlockModel:
    """Owns blocks plus the logical-line <-> pixel-Y mapping.

    Heights: every logical line has a height (defaultHeight unless
    overridden for word-wrapped lines); hidden lines have height 0.
    Prefix sums are rebuilt lazily on any mutation.
    """

    def __init__(self, defaultHeight=1):
        self._defaultHeight = defaultHeight
        self._lineCount = 0
        self._lineHeights = {}  # lineNo -> height when visible
        self._blocks = []
        self._dirty = True
        self._tops = []  # prefix sum: _tops[i] = Y of line i

    # -- lines ------------------------------------------------------------

    @property
    def defaultHeight(self):
        return self._defaultHeight

    def setDefaultHeight(self, height):
        self._defaultHeight = height
        self._dirty = True

    def setLineCount(self, count):
        self._lineCount = count
        # drop height overrides that fell out of range
        for lineNo in list(self._lineHeights):
            if lineNo >= count:
                del self._lineHeights[lineNo]
        self._dirty = True

    def lineCount(self):
        return self._lineCount

    def insertLines(self, at, count):
        """Splice `count` lines in before line `at`.

        Block ranges and height overrides at or after the insertion point
        move down; a block the lines land inside simply grows. An
        out-of-range `at` clamps to the end.
        """
        if count <= 0:
            return
        at = max(0, min(at, self._lineCount))

        for block in self._blocks:
            if block.startLine >= at:
                block.startLine += count
                block.endLine += count
            elif block.endLine >= at:
                block.endLine += count

        if self._lineHeights:
            self._lineHeights = {
                (lineNo + count if lineNo >= at else lineNo): height
                for lineNo, height in self._lineHeights.items()}

        self._lineCount += count
        self._dirty = True

    def setLineHeight(self, lineNo, height):
        """Override the visible height of one line (word wrap)."""
        if height == self._defaultHeight:
            self._lineHeights.pop(lineNo, None)
        else:
            self._lineHeights[lineNo] = height
        self._dirty = True

    def lineHeight(self, lineNo):
        """Visible height of the line; 0 when hidden by a folded block."""
        if not self.isLineVisible(lineNo):
            return 0
        return self._lineHeights.get(lineNo, self._defaultHeight)

    def isLineHidden(self, lineNo):
        for block in self._blocks:
            if block.folded and block.coversLines(lineNo):
                # a line is visible again only if some folded ancestor
                # of the covering block does not cover it -- folded
                # blocks hide unconditionally, so one hit is enough
                return True
        return False

    def isLineVisible(self, lineNo):
        return not self.isLineHidden(lineNo)

    def _isPlain(self):
        """No height overrides and nothing folded: O(1) arithmetic."""
        if self._lineHeights:
            return False
        for block in self._blocks:
            if block.folded:
                return False
        return True

    # -- blocks -----------------------------------------------------------

    def blocks(self):
        return list(self._blocks)

    def addBlock(self, startLine, endLine, meta=None, parent=None):
        if endLine < startLine:
            raise ValueError(
                "endLine {} before startLine {}".format(endLine, startLine))
        block = Block(startLine, endLine, meta=meta, parent=parent)
        self._blocks.append(block)
        self._dirty = True
        return block

    def blockAtAnchor(self, lineNo):
        """Innermost block whose anchor is lineNo, or None."""
        found = None
        for block in self._blocks:
            if block.startLine != lineNo:
                continue
            if found is None:
                found = block
            else:
                # deeper in the tree wins
                other = block if block.parent is not None else None
                cur = found if found.parent is not None else None
                if other is not None and (cur is None
                                          or other.parent is cur):
                    found = block
        return found

    def foldedBlockCovering(self, lineNo):
        """Innermost (last registered) folded block hiding lineNo."""
        for block in reversed(self._blocks):
            if block.folded and block.coversLines(lineNo):
                return block
        return None

    def setFolded(self, block, folded):
        block.folded = bool(folded)
        self._dirty = True

    def toggleFold(self, lineNo):
        """Toggle the block anchored at lineNo; None if not an anchor."""
        block = self.blockAtAnchor(lineNo)
        if block is None:
            return None
        self.setFolded(block, not block.folded)
        return block

    def foldAll(self):
        for block in self._blocks:
            if block.isTopLevel():
                self.setFolded(block, True)

    def expandAll(self):
        for block in self._blocks:
            if block.isTopLevel():
                self.setFolded(block, False)

    def clearBlocks(self):
        self._blocks.clear()
        self._dirty = True

    def clear(self):
        self._blocks.clear()
        self._lineHeights.clear()
        self._lineCount = 0
        self._dirty = True

    # -- geometry ---------------------------------------------------------

    def _rebuild(self):
        if not self._dirty:
            return
        if self._isPlain():
            # degenerate case: keep tops empty, geometry falls back to
            # i * defaultHeight without allocating prefix arrays
            self._tops = []
            self._dirty = False
            return

        hidden = [False] * self._lineCount
        for block in self._blocks:
            if not block.folded:
                continue
            for i in range(block.startLine + 1, min(
                    block.endLine, self._lineCount - 1) + 1):
                hidden[i] = True

        tops = [0] * (self._lineCount + 1)
        for i in range(self._lineCount):
            height = 0 if hidden[i] else self._lineHeights.get(
                i, self._defaultHeight)
            tops[i + 1] = tops[i] + height
        self._tops = tops
        self._dirty = False

    def _usesPrefix(self):
        return bool(self._tops)

    def contentHeight(self):
        self._rebuild()
        if not self._usesPrefix():
            return self._lineCount * self._defaultHeight
        return self._tops[-1]

    def lineTop(self, lineNo):
        """Pixel Y of the line top; hidden lines report their position."""
        self._rebuild()
        if self._lineCount == 0:
            return 0
        lineNo = max(0, min(lineNo, self._lineCount - 1))
        if not self._usesPrefix():
            return lineNo * self._defaultHeight
        return self._tops[lineNo]

    def lineBottom(self, lineNo):
        """Pixel Y of the line bottom; 0-height for hidden lines."""
        return self.lineTop(lineNo) + self.lineHeight(lineNo)

    def lineAt(self, y):
        """Logical line occupying pixel Y (hidden lines are skipped).

        Out-of-range Y clamps to the first/last line.
        """
        self._rebuild()
        if self._lineCount == 0:
            return -1
        if y <= 0:
            return 0
        if not self._usesPrefix():
            return max(0, min(y // self._defaultHeight,
                              self._lineCount - 1))
        # tops is non-decreasing; find rightmost line whose top <= y
        idx = bisect.bisect_right(self._tops, y) - 1
        idx = max(0, min(idx, self._lineCount - 1))
        # a plateau of equal tops ends on a folded-away line: step to
        # the first visible line
        while idx + 1 < self._lineCount and self.isLineHidden(idx):
            idx += 1
        if self.isLineHidden(idx):
            while idx > 0 and self.isLineHidden(idx):
                idx -= 1
        return idx
