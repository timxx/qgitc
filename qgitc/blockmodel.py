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
        self._foldedBlocks = []  # the subset that is folded, in fold order
        self._dirty = True
        self._tops = []  # prefix sum: _tops[i] = Y of line i
        self._indexDirty = True
        self._anchorLines = []  # sorted anchor lines of every block
        self._innermostByAnchor = {}  # anchor -> innermost nested block
        self._topByAnchor = {}  # anchor -> top-level section starting there

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
        self._invalidate()

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
        """True when a folded block covers lineNo.

        Only folded blocks can hide anything, so the few that are folded
        are walked instead of every block: lineHeight/lineBottom sit in
        the paint loop, and a document can carry one block per file.
        """
        for block in self._foldedBlocks:
            if block.coversLines(lineNo):
                # a line is visible again only if some folded ancestor
                # of the covering block does not cover it -- folded
                # blocks hide unconditionally, so one hit is enough
                return True
        return False

    def isLineVisible(self, lineNo):
        return not self.isLineHidden(lineNo)

    def _isPlain(self):
        """No height overrides and nothing folded: O(1) arithmetic."""
        return not self._lineHeights and not self._foldedBlocks

    # -- blocks -----------------------------------------------------------

    def _invalidate(self):
        """A structural change: the geometry and the block index are stale."""
        self._dirty = True
        self._indexDirty = True

    def _rebuildIndex(self):
        """Index the blocks by their anchor line.

        The geometry, the paint loop and the file list sync all map a
        line to a block, and a document carries one block per file, so
        scanning every block per line was the hot path. Two indexes come
        out of one pass:

        - `_innermostByAnchor`: the block that owns the fold control on
          an anchor line (the deepest, matching the old linear scan);
        - `_topByAnchor`: the enclosing top-level section, if any, so a
          line inside nested ranges still resolves to its section.
        """
        if not self._indexDirty:
            return
        self._indexDirty = False

        innermost = {}
        topLevel = {}
        anchors = []
        for block in self._blocks:
            if block.isTopLevel():
                if block.startLine not in topLevel:
                    anchors.append(block.startLine)
                topLevel[block.startLine] = block
                continue

            if block.startLine not in innermost:
                anchors.append(block.startLine)
                innermost[block.startLine] = block
                continue
            # deeper in the tree wins, exactly as the linear scan did
            found = innermost[block.startLine]
            other = block if block.parent is not None else None
            cur = found if found.parent is not None else None
            if other is not None and (cur is None or other.parent is cur):
                innermost[block.startLine] = block

        self._innermostByAnchor = innermost
        self._topByAnchor = topLevel
        self._anchorLines = sorted(anchors)

    def blocks(self):
        return list(self._blocks)

    def addBlock(self, startLine, endLine, meta=None, parent=None):
        if endLine < startLine:
            raise ValueError(
                "endLine {} before startLine {}".format(endLine, startLine))
        block = Block(startLine, endLine, meta=meta, parent=parent)
        self._blocks.append(block)
        self._invalidate()
        return block

    def blockAtAnchor(self, lineNo):
        """Innermost block whose anchor is lineNo, or None."""
        self._rebuildIndex()
        found = self._innermostByAnchor.get(lineNo)
        if found is not None:
            return found
        return self._topByAnchor.get(lineNo)

    def blockAtLine(self, lineNo):
        """The top-level section that owns lineNo, or None.

        Sections start in order, so bisecting the anchors jumps straight
        to the last one at or before lineNo; only a line a shorter
        overlapping section does not reach walks one step further back.
        Anchors carrying only nested blocks are skipped, since the
        section they belong to starts earlier. A line in a gap -- after a
        section ends and before the next one starts -- belongs to none.

        Nested ranges are reached through `blockAtAnchor`.
        """
        self._rebuildIndex()
        lines = self._anchorLines
        if not lines:
            return None

        idx = bisect.bisect_right(lines, lineNo) - 1
        while idx >= 0:
            block = self._topByAnchor.get(lines[idx])
            if block is not None and block.containsLine(lineNo):
                return block
            idx -= 1
        return None

    def foldedBlockCovering(self, lineNo):
        """The last folded block that hides lineNo, or None.

        Callers unfold in a loop, so which covering block is reported
        first only decides the order the folds open in.
        """
        for block in reversed(self._foldedBlocks):
            if block.coversLines(lineNo):
                return block
        return None

    def setFolded(self, block, folded):
        folded = bool(folded)
        if folded == block.folded:
            return
        block.folded = folded
        if folded:
            self._foldedBlocks.append(block)
        else:
            self._foldedBlocks.remove(block)
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
        self._foldedBlocks.clear()
        self._invalidate()

    def clear(self):
        self._blocks.clear()
        self._foldedBlocks.clear()
        self._lineHeights.clear()
        self._lineCount = 0
        self._invalidate()

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
        for block in self._foldedBlocks:
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
