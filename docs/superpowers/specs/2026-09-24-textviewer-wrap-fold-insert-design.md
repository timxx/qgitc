# TextViewer Wrap, Folding and Block Insertion Refactor Design

Date: 2026-09-24
Status: Implemented — every stage committed, full suite green (1485 tests when written)
Scope: qgitc/textviewer.py, qgitc/blockmodel.py, qgitc/textline.py, qgitc/textcursor.py and the
business call sites (patchviewer, diffview, branchcomparewindow, blamesourceviewer, revisionpanel).

This document records the requirement, the settled design and what the code actually looks like, so a
later session can review or rework the viewer without re-deriving it. Read `qgitc/blockmodel.py`
first: it holds the whole coordinate model and is the only Qt-free module of the family.

## Objective

Two requests drove this refactor.

1. Refactor qgitc/textviewer.py so **any line can opt into word wrap**: over-long comment lines (the
   commit message and the author/commit headers) must wrap, while diff content must not — a diff stays
   byte-faithful and keeps horizontal scrolling.
2. Support **folding**, e.g. fold everything that belongs to one file's diff as a single block.
3. Follow-up request: a block must be **insertable at any position**. With "sort files by name" on, the
   viewer used to collect every file and its diff and only insert them into the viewer when the fetch
   had finished, so the user stared at an empty diff and felt the app had stalled. Each file's block
   should land at its sorted position as soon as the file is complete, instead of at the very end.

## Non-Goals

1. No hunk-level folding (the parser does not keep "I am a hunk header" state on a line).
2. No code folding and no blame folding. The capability is generic; the business side decides where to
   use it. Blame and the revision panel keep exactly their old behavior.
3. No wrap for diff content, and `CommitDetailPanel` is deliberately left unwrapped this round.
4. No persistence: fold state is view memory, `clear()` resets it.
5. No line removal. Only appending and insertion are supported; `_maxWidth` (the horizontal scroll
   range) and the geometry both assume the document only grows.

## Confirmed Decisions

These came out of a design Q&A before any code was written; keep them in mind before changing behavior.

| # | Decision |
|---|----------|
| Wrap | Per-line opt-in, decided by the caller or the `TextLine` subclass. Default `NoWrap`, so existing viewers see no change. |
| Layout | Wrap to the viewport width. Wrapped rows ignore horizontal scrolling; `NoWrap` diff lines keep it. |
| Folding | Generic block model: blocks are injected from outside with `beginBlock`/`endBlock`. Nesting exists in the model, but business code registers flat blocks only. |
| Anchor | The block's first line stays visible when folded. A grey `…` chip is painted over that line plus a hover tooltip (line count + block summary). The chip is not part of the text: copying the anchor line yields the raw text. |
| Interaction | Clicking the anchor toggles. The context menu shows the fold entry only on foldable points. Fold all / expand all touch top-level blocks only. `textLineClicked` still fires. |
| State | View memory only, no persistence. |
| find / gotoLine | A target inside a folded block auto-expands it. |
| Copy | `TextCursor` stays fold-unaware: `selectedText`/`selectAll`/copy include folded lines. Folded is not hidden. |
| Scrolling | Every viewer switches to pixel scrolling over a logical-line ↔ pixel map. `firstVisibleLine`, `gotoLine`, `lineNo` and `FileInfo.row` all remain **logical line numbers**. |
| Registration | diffview registers one Comments block plus one block per file. Hunk level, blame and code folding stay capability-only. |
| Insertion | Insertion is **physical**: everything at or after the insertion point is renumbered. One numbering for the whole codebase, no separate "storage line" vs "display line". |
| Sorted mode | The diff content order always matches the file list order. |

## Previous State

1. One logical line was exactly one pixel row: `firstVisibleLine()` returned
   `verticalScrollBar().value()`, `textRowForPos()` divided y by `lineHeight`, and painting stepped by
   `lineHeight`. Wrapped lines would have broken the equality.
2. `TextLine` forced `NoWrap`, laid out exactly one `QTextLayout` line, and `offsetToX`/`offsetForPos`
   only ever looked at `lineAt(0)`.
3. There was no folding or line hiding anywhere in the `TextViewer` family. The only precedent in the
   repo is `QTextBlock.setVisible` in aichatbot's `QTextEdit`, which is unrelated.
4. Diff content was append-only, and the sorted path buffered everything: `DiffView.__onDiffAvailable`
   only filled `_pendingDiffs`, and `_flushPendingDiffs()` rendered all files once the fetch ended.

## Architecture (as built)

### Module responsibilities

* `qgitc/blockmodel.py` — pure data, no Qt: foldable blocks (line ranges, nesting, fold state) plus
  per-line heights and prefix-sum geometry. This is where the coordinate model lives.
* `qgitc/textline.py` — per-line wrap opt-in, multi visual row layout, visual row helpers
  (`visualLineCount`, `rowWidth`, `rowAtOffset`) and per-row offset mapping.
* `qgitc/textcursor.py` — logical line cursor, plus `shiftLines(index, count)` so a selection follows
  inserted lines.
* `qgitc/textviewer.py` — geometry use, painting, hit testing, find/selection, the fold API, insertion
  and scrollbar bookkeeping.
* `qgitc/patchviewer.py` — file sections become blocks (streaming append path and `insertFileSection`),
  and the comments region opts into wrap.
* `qgitc/diffview.py` — sorted incremental insertion and `FileListModel.insertFile`.

### Numbering and geometry rules

1. There is exactly one numbering: a logical line number indexes the viewer's line store. Inserting
   lines renumbers the tail, and every consumer of a line number follows (see the checklist below).
2. Height of a line: `lineHeight` normally, `visualLineCount() * lineHeight` for a wrapped line, and 0
   for a line hidden by a folded block.
3. `BlockModel._tops` is a prefix sum over those heights. When there are no height overrides and no
   folded block, `_isPlain()` takes an O(1) arithmetic fast path instead of building the array.
4. y ↔ line: `textRowForPos()` asks the model (`lineAt(scrollValue + y)`), `lineTop(lineNo)` gives the
   pixel top of a line, and `contentOffset()` exposes the fractional offset of the top line so
   followers (the revision panel, line rects) paint on the same pixel grid.
5. A wrapped line is laid out to `wrapWidth()` = viewport width − `gutterWidth()` and is drawn from
   `gutterWidth()` with no horizontal offset, so a wrapped row never drifts when scrolling sideways.

### Public API surface

Data layer (`BlockModel`, `Block`):

| API | Meaning |
|---|---|
| `setLineCount(count)` / `lineCount()` | Line count; `setLineCount` drops height overrides that fell out of range. |
| `setLineHeight(lineNo, height)` / `lineHeight(lineNo)` | Height override for wrapped lines; `lineHeight` returns 0 for a hidden line. |
| `lineTop(lineNo)` / `lineBottom(lineNo)` / `lineAt(y)` | Pixel mapping. `lineAt` skips hidden plateaus and clamps out of range. |
| `contentHeight()` | Total pixel height. |
| `addBlock(startLine, endLine, meta=None, parent=None)` | Register a block. The anchor (`startLine`) stays visible when folded. |
| `insertLines(at, count)` | Splice lines in before `at`: later block ranges and height overrides move down, a block the lines land inside grows. |
| `blockAtAnchor(lineNo)` / `foldedBlockCovering(lineNo)` | Lookup helpers. |
| `isLineVisible/isLineHidden(lineNo)`, `setFolded`, `toggleFold`, `foldAll`, `expandAll` | Fold state. |
| `blocks()`, `clearBlocks()`, `clear()` | Introspection and reset. `blocks()` is in **registration order**, not line order. |

View layer (`TextViewer`), the parts that matter to callers:

| API | Meaning |
|---|---|
| `appendLine/appendLines/appendTextLine` | Append at the end (unchanged semantics). |
| `insertLines(index, lines)` | Insert raw lines before logical line `index`; renumbers and shifts everything after (see the checklist). |
| `beginBlock(meta=None)` / `endBlock()` | Block anchored at the next appended line; an unclosed block is closed by the next `beginBlock`, by `endBlock`, or dropped by `clear()`. Use this when a section's end is not known yet. |
| `addBlock(startLine, endLine, meta=None)` | Register a block over lines that already exist. Use this when the boundaries are known up front. |
| `canFoldAt(lineNo)`, `toggleFoldAt`, `foldAllBlocks`, `expandAllBlocks`, `expandBlocksCovering(lineNo)` | Fold interaction; `foldTipForLine(lineNo)` builds the tooltip and uses `meta["title"]` as a summary when present. |
| `wrapWidth()` / `gutterWidth()` | Where wrapped lines lay out to; the gutter is reserved only once a block exists. |
| `firstVisibleLine()`, `textRowForPos(pos)`, `contentOffset()`, `gotoLine`, `ensureLineVisible` | Pixel-aware, logical-line based. |

Business layer:

| API | Meaning |
|---|---|
| `PatchViewer.isFileMarker(item)` | True for the `DiffType.File` tuple that opens a file's section. |
| `PatchViewer.insertFileSection(position, items)` | Insert one complete file section and register its block around it. |
| `PatchViewer.endReading()` | Closes the still-open file section before the base class re-runs a live find. |
| `FileListModel.insertFile(row, file, info)` / `fileInfos()` | Insert a file entry at a row; enumerate the `FileInfo` objects to shift their `row`. |
| `DiffView._flushSortedFile()` | Insert the file that was being split at its sorted position (no-op when sorting is off). |

### Behaviour contracts (pinned by tests, do not regress)

1. Folding never changes line numbers and never changes what a selection or `copy` sees: folded lines
   are part of `selectedText`.
2. `find`/`gotoLine`/file-list clicks unfold whatever hides the target.
3. The anchor line of a folded block stays visible and keeps its own row; only lines after it collapse.
4. The fold affordance does not leak painter state, and the chip is drawn, never inserted into text.
5. The gutter is reserved only while at least one block exists, and the `…` chip is drawn only on the
   anchor of a folded block.
6. In sorted mode the viewer order equals the file list order, and every `FileInfo.row` equals the
   viewer line of that file's `DiffType.File` marker.
7. Viewers that do not register blocks and do not opt lines into wrap behave exactly as before
   (blame, revision panel).

## Insertion Design

### Why physical renumbering

The alternative was to keep storage order and permute blocks in the geometry layer. That was rejected:
every index-based consumer — the cursor, the find results, `_highlightLines`, `TextLine.lineNo` and
`FileInfo.row` — would have to know about two numberings, and selection rects spanning reordered
regions would need display-aware min/max. Physical renumbering keeps one rule and only costs a shift
(see "Cost" below).

### Checklist — everything that indexes lines must move

`TextViewer._shiftLineNumbers(index, count)`, in one place:

1. every key of `_textLines` at or after `index`, plus the `TextLine.setLineNo()` of those objects;
2. `_wrappedLineNos` (the opt-in wrap set);
3. `_cursor` and every `TextCursor` in `_highlightFind` (via `TextCursor.shiftLines`);
4. `_highlightLines` (used by the revision panel);
5. `_openBlockStart` (a block still being streamed);
6. `_contextLine`, `_convertIndex`, `_findIndex`, `_findCurPageRange`.

Plus, outside the viewer:

7. `BlockModel.insertLines` moves block ranges and height overrides, and grows a block the lines land
   inside;
8. `DiffView` updates `FileInfo.row` for every file after the insertion point.

`_textLines` is still a dict keyed by line number (not a list): insertion only happens while the diff
is streaming, when few lines have been built, so re-keying is cheap. If insertion ever has to happen
against a fully built document, revisit this (a list or a chunked store would be the next move).

### Cost

Insertion happens during streaming, and `_onConvertEvent` deliberately does not advance while
`_inReading` (it waits for more lines), so the tail is almost entirely unconverted raw items: splicing
is a `list` memmove plus renumbering the handful of built `TextLine` objects. Do not assume the same
cheapness after `endReading()`.

### Conversion sweep

The sweep (`_onConvertEvent`) walks the document and is what accounts `_maxWidth` (horizontal scroll
range) and drives `_adjustScrollbars`. An insertion behind the sweep point would never be walked, so
`insertLines` rewinds `_convertIndex` to the insertion point. To keep that cheap, the sweep re-scans
already built lines **in bulk** (capped by `_MAX_RESCAN_PER_EVENT = 500` per event) and still builds at
most one new `TextLine` per event, preserving the original "never block the event loop" property.

### Scroll anchoring

Inserting above the visible area would push what the user is reading downwards. `insertLines` keeps the
scroll value in place instead: when the insertion point is at or above the first visible line and the
scrollbar is not at the top, the value is bumped by the inserted pixel height.

## Sorted Mode (diffview)

1. `DiffView.__onDiffAvailable` keeps splitting the stream on `DiffType.File` into
   `_splitFile/_splitInfo/_splitLines` — a file's diff can span several `parse()` calls and
   continuation chunks carry no marker.
2. A file is complete when **the next marker or the end of the fetch** arrives. At that moment
   `_flushSortedFile()` asks `__sortedInsertionPoint(fileName)` for the file list row and the viewer
   line, calls `FileListModel.insertFile`, sets `info.row`, calls
   `PatchViewer.insertFileSection(lineNo, items)` and finally moves every later `FileInfo.row` down by
   the inserted line count.
3. The last file of a fetch therefore still waits for the end — that is the price of not being able to
   tell a continuation chunk from a new file, and it is why the improvement is "files appear one by one"
   rather than "immediately".
4. `__sortedInsertionPoint` compares names case-insensitively against file list rows from 1 on. Row 0 is
   the commit's `"Comments"` pseudo row (see `DiffView.__isCommentItem` and
   `mainwindowcontextprovider`): it must never take part in the comparison and never move.
5. With sorting off nothing is held back: `__addToFileListView` plus `viewer.appendLines` still render
   each block as it arrives, and `_flushSortedFile()` is a no-op because no split state accumulates.

## Commit Series

The refactor is a chain of small commits; this is the map if you need to bisect or replay it.

| Commit | Subject | Files |
|---|---|---|
| `de0bb64f` | feat: add foldable block model with line-to-pixel mapping | blockmodel, test_blockmodel |
| `058be79a` | feat: support opt-in word wrap on text lines | textline, test_textline_wrap |
| `108403f9` | feat: add plain-path geometry to block model | blockmodel, test_blockmodel |
| `a5ee85f3` | feat: switch text viewer to pixel-based vertical scrolling | textviewer, test_textviewer_layout |
| `ef93772f` | feat: wire word wrap width and heights in the text viewer | textline, textviewer, test_textviewer_layout |
| `1db4a613` | feat: add generic foldable blocks to the text viewer | blockmodel, textline, textviewer, test_textviewer_fold |
| `cdea7f8d` | fix: route remaining scroll consumers through line geometry | textviewer, patchviewer, revisionpanel, blamesourceviewer, tests |
| `3ed91dea` | feat: wrap the patch viewer comments region | patchviewer, test_patchviewer |
| `b37e86ed` | feat: fold each file section in the patch viewer | patchviewer, diffview, branchcomparewindow, textviewer, tests |
| `6248a89d` | fix: take the blame line rect from line geometry | blamesourceviewer, test_scroll_consumers |
| `d0e5cea1` | fix: stop the fold glyph from recolouring later lines | textviewer, test_textviewer_fold |
| `7f016c49` | feat: let the block model splice lines in place | blockmodel, test_blockmodel |
| `01ff23c3` | feat: insert lines at a position in the text viewer | textviewer, textcursor, test_textviewer_insert |
| `d25374b1` | fix: keep the scroll range and rewind cheap after an insertion | textviewer, tests |
| `8d20cc4f` | feat: register fold blocks for already added lines | textviewer, patchviewer, tests |
| `f4529f2c` | feat: insert sorted diff sections as they arrive | diffview, test_diffview |

## Pitfalls Found (and fixed)

Worth rereading before touching painting or the sweep.

1. **Painter state leak.** The fold glyph did `painter.setPen(whitespace colour)` and never restored it.
   `QTextLayout.draw` then used that pen for every following line **without an explicit format**, which
   in the patch view is exactly the diff context lines: they turned dim grey, and a partial repaint
   (selecting a line) repainted them correctly, so the refreshed region no longer matched its
   surroundings. Fix: `painter.save()`/`restore()` around the fold affordance.
2. **The viewport can be resized without the scroll area being resized.** The scroll range was only ever
   refreshed by the per-line sweep, which masked this. Now the viewer installs an event filter on its
   viewport and re-adjusts on `QEvent.Resize`. Note that Qt defers resize events for hidden widgets, so
   tests that assert on the range must `show()` the viewer.
3. **A rewinding sweep used to cost one event-loop turn per already built line.** Batch the re-scan
   (`_MAX_RESCAN_PER_EVENT`), keep building at most one new line per event.
4. **`blocks()` is in registration order, not line order.** After an insertion they differ: index blocks
   by `blockAtAnchor(lineNo)`, never by position in the list.
5. **File list row 0 is the "Comments" pseudo row.** `__isCommentItem` and `mainwindowcontextprovider`
   rely on it; keep it out of comparisons and never move it.
6. **`_lines[n] is None` means "this line is already built"** (the built object lives in `_textLines[n]`).
   Splicing must keep that invariant, and `_lines` is deliberately dropped (`None`) once everything is
   built, so insertion has to re-create the raw slots first.
7. **The folded-content chip is painted, not stored.** Nothing about folding may leak into `text()` or
   the clipboard.

## Test Map and Verification

| Area | Tests |
|---|---|
| Geometry, blocks, insertion at the model level | tests/test_blockmodel.py |
| Wrap on a single line | tests/test_textline_wrap.py |
| Viewer append/click/double-click/select/find, async find | tests/test_textviewer.py |
| Pixel scrolling, wrap geometry, `show()`-based range | tests/test_textviewer_layout.py |
| Fold registration, gutter, chip, click, menu, tooltip, copy | tests/test_textviewer_fold.py |
| `insertLines` semantics and the state checklist | tests/test_textviewer_insert.py |
| Comments wrap, file blocks, `insertFileSection`, context menu | tests/test_patchviewer.py |
| Unsorted/unsorted-cleared/sorted incremental flows, Comments block | tests/test_diffview.py |
| Blame line rect and revision panel pixel grid | tests/test_scroll_consumers.py |

```
python -m unittest discover -s tests -p "test_*.py" -v
python -m isort <changed files> && python -m py_compile <changed files>
```

## Left Out On Purpose / Follow-ups

1. Hunk-level folding and code folding: the model supports nesting, but registering nested blocks and
   teaching the business side what a hunk is were out of scope.
2. Blame and code folding: they need the main viewer and the revision panel to stay line-for-line, so
   enable them together with the panel geometry (see below).
3. `RevisionPanel.paintEvent` still steps by `self._viewer.lineHeight` per line and paints its own
   lines. That is exact today (blame wraps nothing) but must move to the viewer's geometry before blame
   ever wraps or folds.
4. `BlameSourceViewer._lineRect` now asks the model, so it is ready for wrapped blame lines.
5. `_maxWidth` only grows; there is no line removal, and a removal path would need a full recompute.
6. `CommitDetailPanel` (commit header plus message) does not wrap yet; the same `setWrap(True)` recipe
   applies when it is wanted.

## How To Extend

To make another viewer wrap or fold:

1. Wrap a line kind: call `setWrap(True)` on those `TextLine` instances (in the line subclass, or where
   the viewer builds them, as `PatchViewer.addSummaryTextLine` does). The viewer supplies the width and
   keeps the height in the model — do not lay out or measure anything by hand.
2. Register blocks around appended content with `beginBlock(meta)`/`endBlock()` when the end is unknown
   while streaming, or with `addBlock(startLine, endLine, meta)` when it is known up front. Put a
   `"title"` in `meta` if the tooltip should name the block.
3. For insertion, call `insertLines(index, items)`, or `addBlock` after it. Then keep any **external**
   line-indexed state in sync yourself — the in-viewer part is handled by `_shiftLineNumbers`, and
   `FileInfo.row` in diffview is the current example of the external kind.
4. Everything else is inherited: geometry, gutter, chip, tooltip, context menu entries, fold all /
   expand all, find and goto auto-expand, and copying folded lines.
5. Do nothing at all if the viewer should stay as it was: no wrap opt-in and no blocks means the old
   behavior, pixel scrolling included.
