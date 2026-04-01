# -*- coding: utf-8 -*-
"""Performance tests for TextLine with very long text lines.

Reproduces the UI-freeze issue caused by email_re catastrophic backtracking
and QTextLayout overhead on 100k+ char lines (e.g. minified JS in diffs).
"""
import time
from unittest.mock import patch

from qgitc.textline import (
    _MAX_DISPLAY_CHARS,
    _MAX_LINK_SCAN_LEN,
    _TRUNCATED_SUFFIX,
    Link,
    TextLine,
)
from tests.base import TestBase

# Threshold: any single-line operation must complete within this time budget
_SINGLE_LINE_MAX_MS = 100


class TestTextLinePerformance(TestBase):
    """Verify that long-line operations complete quickly enough for a responsive UI."""

    def doCreateRepo(self):
        pass

    def _time_ms(self, fn):
        start = time.perf_counter()
        result = fn()
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, result

    # ------------------------------------------------------------------
    # findLinks – the main danger zone (catastrophic regex backtracking)
    # ------------------------------------------------------------------

    def test_findLinks_long_ascii_no_links(self):
        """findLinks on a 100k ASCII-only line with no links must be fast."""
        long_text = "a" * 100000

        patterns = []
        for linkType, pattern in TextLine.builtinPatterns().items():
            patterns.append((linkType, pattern, None))

        elapsed, links = self._time_ms(
            lambda: TextLine.findLinks(long_text, patterns))
        self.assertEqual([], links, "No links expected in pure ASCII line")
        self.assertLess(elapsed, _SINGLE_LINE_MAX_MS,
                        f"findLinks took {elapsed:.0f}ms on 100k ASCII line (limit {_SINGLE_LINE_MAX_MS}ms)")

    def test_findLinks_long_line_with_email_chars(self):
        """findLinks on a line that looks like potential email fodder must be fast."""
        # Pattern known to cause catastrophic backtracking: long run of word-chars before @
        long_text = "x" * 50000 + "@" + "y" * 50000

        patterns = []
        for linkType, pattern in TextLine.builtinPatterns().items():
            patterns.append((linkType, pattern, None))

        elapsed, links = self._time_ms(
            lambda: TextLine.findLinks(long_text, patterns))
        self.assertLess(elapsed, _SINGLE_LINE_MAX_MS,
                        f"findLinks took {elapsed:.0f}ms on 100k line with @ (limit {_SINGLE_LINE_MAX_MS}ms)")

    def test_findLinks_skips_long_lines(self):
        """findLinks returns empty for lines exceeding _MAX_LINK_SCAN_LEN."""
        long_text = "a" * (_MAX_LINK_SCAN_LEN + 1)
        patterns = [(Link.Sha1, TextLine.builtinPatterns()[Link.Sha1], None)]
        links = TextLine.findLinks(long_text, patterns)
        self.assertEqual([], links)

    def test_findLinks_still_works_below_limit(self):
        """findLinks still detects SHA1, email and URL within the scan limit."""
        text = "fix abc1234 in foo@bar.com, see https://example.com/ticket"
        self.assertLess(len(text), _MAX_LINK_SCAN_LEN)

        patterns = []
        for linkType, pattern in TextLine.builtinPatterns().items():
            patterns.append((linkType, pattern, None))

        links = TextLine.findLinks(text, patterns)
        types = {link.type for link in links}
        self.assertIn(Link.Sha1, types)
        self.assertIn(Link.Email, types)
        self.assertIn(Link.Url, types)

    # ------------------------------------------------------------------
    # TextLine construction + ensureLayout on very long text
    # ------------------------------------------------------------------

    def test_textline_creation_long_line(self):
        """Creating a TextLine for a 100k char line must complete quickly."""
        long_text = "a" * 100000
        font = self.app.font()

        elapsed, tl = self._time_ms(lambda: TextLine(long_text, font))
        self.assertLess(elapsed, _SINGLE_LINE_MAX_MS,
                        f"TextLine() took {elapsed:.0f}ms on 100k line")
        # text() still returns the full text
        self.assertEqual(len(tl.text()), 100000)

    def test_textline_ensure_layout_long_line(self):
        """ensureLayout on a 100k char line must complete quickly."""
        long_text = "a" * 100000
        font = self.app.font()
        tl = TextLine(long_text, font)

        elapsed, _ = self._time_ms(lambda: tl.ensureLayout())
        self.assertLess(elapsed, _SINGLE_LINE_MAX_MS,
                        f"ensureLayout took {elapsed:.0f}ms on 100k line")

    def test_textline_layout_uses_truncated_text(self):
        """QTextLayout only holds up to _MAX_DISPLAY_CHARS chars for long lines."""
        long_text = "a" * (_MAX_DISPLAY_CHARS + 5000)
        font = self.app.font()
        tl = TextLine(long_text, font)
        tl.ensureLayout()

        layout_text = tl._layout.text()
        self.assertTrue(layout_text.endswith(_TRUNCATED_SUFFIX))
        self.assertEqual(len(layout_text),
                         _MAX_DISPLAY_CHARS + len(_TRUNCATED_SUFFIX))
        self.assertEqual(
            layout_text[:_MAX_DISPLAY_CHARS], long_text[:_MAX_DISPLAY_CHARS])
        # Original text is preserved
        self.assertEqual(len(tl.text()), _MAX_DISPLAY_CHARS + 5000)

    def test_textline_truncation_suffix_is_translatable(self):
        """Truncation suffix should go through Qt translation."""
        long_text = "a" * (_MAX_DISPLAY_CHARS + 100)
        font = self.app.font()

        with patch("qgitc.textline.QCoreApplication.translate", return_value=" [translated]"):
            tl = TextLine(long_text, font)
            tl.ensureLayout()

        self.assertTrue(tl._layout.text().endswith(" [translated]"))

    def test_textline_short_line_uses_full_text(self):
        """Short lines are unaffected: layout text equals full text."""
        text = "hello world"
        font = self.app.font()
        tl = TextLine(text, font)
        tl.ensureLayout()
        self.assertEqual(tl._layout.text(), text)

    # ------------------------------------------------------------------
    # mapToUtf16 bounds with truncated layout
    # ------------------------------------------------------------------

    def test_mapToUtf16_capped_at_display_len(self):
        """mapToUtf16 caps positions beyond displayLen instead of warning."""
        long_text = "abc" * 5000  # 15000 chars, all BMP
        font = self.app.font()
        tl = TextLine(long_text, font)

        # Position within display range
        pos_in = _MAX_DISPLAY_CHARS // 2
        self.assertEqual(tl.mapToUtf16(pos_in), pos_in)

        # Position beyond display range is silently capped
        pos_out = _MAX_DISPLAY_CHARS + 500
        self.assertEqual(tl.mapToUtf16(pos_out), _MAX_DISPLAY_CHARS)
