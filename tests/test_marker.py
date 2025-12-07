import unittest

from qgitc.logview import Marker, MarkType


class TestMarker(unittest.TestCase):
    """Test the improved Marker functionality"""

    def setUp(self):
        """Create a fresh Marker for each test"""
        self.marker = Marker()

    def test_mark_single_commit(self):
        """Test marking a single commit"""
        self.marker.mark(5, 5)
        self.assertTrue(self.marker.isMarked(5))
        self.assertFalse(self.marker.isMarked(4))
        self.assertFalse(self.marker.isMarked(6))

    def test_mark_range(self):
        """Test marking a range of commits"""
        self.marker.mark(10, 20)
        self.assertTrue(self.marker.isMarked(10))
        self.assertTrue(self.marker.isMarked(15))
        self.assertTrue(self.marker.isMarked(20))
        self.assertFalse(self.marker.isMarked(9))
        self.assertFalse(self.marker.isMarked(21))

    def test_mark_with_types(self):
        """Test marking with different mark types"""
        self.marker.mark(0, 0, MarkType.PICKED)
        self.marker.mark(1, 1, MarkType.FAILED)
        self.marker.mark(2, 2, MarkType.NORMAL)

        self.assertEqual(self.marker.getMarkType(0), MarkType.PICKED)
        self.assertEqual(self.marker.getMarkType(1), MarkType.FAILED)
        self.assertEqual(self.marker.getMarkType(2), MarkType.NORMAL)

    def test_toggle_mark(self):
        """Test toggling marks on and off"""
        # Initially unmarked
        self.assertFalse(self.marker.isMarked(5))

        # Toggle on
        result = self.marker.toggle(5)
        self.assertTrue(result)
        self.assertTrue(self.marker.isMarked(5))

        # Toggle off
        result = self.marker.toggle(5)
        self.assertFalse(result)
        self.assertFalse(self.marker.isMarked(5))

    def test_unmark_single_from_range(self):
        """Test unmarking a single commit from a larger range"""
        self.marker.mark(10, 20)
        self.marker.unmark(15)

        # 15 should be unmarked
        self.assertFalse(self.marker.isMarked(15))

        # Neighbors should still be marked
        self.assertTrue(self.marker.isMarked(14))
        self.assertTrue(self.marker.isMarked(16))

        # Range endpoints should be marked
        self.assertTrue(self.marker.isMarked(10))
        self.assertTrue(self.marker.isMarked(20))

    def test_unmark_at_beginning_of_range(self):
        """Test unmarking at the start of a range"""
        self.marker.mark(10, 20)
        self.marker.unmark(10)

        self.assertFalse(self.marker.isMarked(10))
        self.assertTrue(self.marker.isMarked(11))
        self.assertTrue(self.marker.isMarked(20))

    def test_unmark_at_end_of_range(self):
        """Test unmarking at the end of a range"""
        self.marker.mark(10, 20)
        self.marker.unmark(20)

        self.assertTrue(self.marker.isMarked(10))
        self.assertTrue(self.marker.isMarked(19))
        self.assertFalse(self.marker.isMarked(20))

    def test_unmark_range(self):
        """Test unmarking a range of commits"""
        self.marker.mark(10, 30)
        self.marker.unmark(15, 25)

        # Middle section should be unmarked
        for i in range(15, 26):
            self.assertFalse(self.marker.isMarked(i))

        # Beginning and end should still be marked
        self.assertTrue(self.marker.isMarked(10))
        self.assertTrue(self.marker.isMarked(14))
        self.assertTrue(self.marker.isMarked(26))
        self.assertTrue(self.marker.isMarked(30))

    def test_unmark_entire_range(self):
        """Test unmarking an entire range"""
        self.marker.mark(10, 20)
        self.marker.unmark(10, 20)

        for i in range(10, 21):
            self.assertFalse(self.marker.isMarked(i))

    def test_unmark_overlapping_multiple_ranges(self):
        """Test unmarking across multiple ranges"""
        self.marker.mark(10, 20)
        self.marker.mark(30, 40)
        self.marker.unmark(15, 35)

        # First range partially unmarked
        self.assertTrue(self.marker.isMarked(10))
        self.assertTrue(self.marker.isMarked(14))
        self.assertFalse(self.marker.isMarked(15))
        self.assertFalse(self.marker.isMarked(20))

        # Gap should be unmarked
        self.assertFalse(self.marker.isMarked(25))

        # Second range partially unmarked
        self.assertFalse(self.marker.isMarked(30))
        self.assertFalse(self.marker.isMarked(35))
        self.assertTrue(self.marker.isMarked(36))
        self.assertTrue(self.marker.isMarked(40))

    def test_count_marked_empty(self):
        """Test counting with no marks"""
        self.assertEqual(self.marker.countMarked(), 0)

    def test_count_marked_single(self):
        """Test counting a single mark"""
        self.marker.mark(5, 5)
        self.assertEqual(self.marker.countMarked(), 1)

    def test_count_marked_range(self):
        """Test counting a range of marks"""
        self.marker.mark(10, 20)  # 11 commits (10-20 inclusive)
        self.assertEqual(self.marker.countMarked(), 11)

    def test_count_marked_multiple_ranges(self):
        """Test counting multiple ranges"""
        self.marker.mark(10, 15)  # 6 commits
        self.marker.mark(20, 25)  # 6 commits
        self.marker.mark(30, 30)  # 1 commit
        self.assertEqual(self.marker.countMarked(), 13)

    def test_count_marked_after_unmark(self):
        """Test counting after unmarking"""
        self.marker.mark(10, 20)  # 11 commits
        self.marker.unmark(15, 18)  # Remove 4 commits
        self.assertEqual(self.marker.countMarked(), 7)

    def test_get_marked_indices_empty(self):
        """Test getting marked indices when empty"""
        indices = self.marker.getMarkedIndices()
        self.assertEqual(indices, [])

    def test_get_marked_indices_single(self):
        """Test getting marked indices for a single commit"""
        self.marker.mark(5, 5)
        indices = self.marker.getMarkedIndices()
        self.assertEqual(indices, [5])

    def test_get_marked_indices_range(self):
        """Test getting marked indices for a range"""
        self.marker.mark(10, 15)
        indices = self.marker.getMarkedIndices()
        self.assertEqual(indices, [10, 11, 12, 13, 14, 15])

    def test_get_marked_indices_multiple_ranges(self):
        """Test getting marked indices for multiple ranges"""
        self.marker.mark(5, 7)
        self.marker.mark(10, 12)
        indices = self.marker.getMarkedIndices()
        # Should be sorted
        self.assertEqual(indices, [5, 6, 7, 10, 11, 12])

    def test_get_marked_indices_after_unmark(self):
        """Test getting marked indices after unmarking"""
        self.marker.mark(10, 20)
        self.marker.unmark(15)
        indices = self.marker.getMarkedIndices()
        # 15 should be missing
        expected = list(range(10, 15)) + list(range(16, 21))
        self.assertEqual(indices, expected)

    def test_binary_search_efficiency(self):
        """Test that binary search works correctly with many ranges"""
        # Create many non-overlapping ranges
        for i in range(0, 100, 10):
            self.marker.mark(i, i + 5)

        # Test lookups
        self.assertTrue(self.marker.isMarked(0))
        self.assertTrue(self.marker.isMarked(25))
        self.assertTrue(self.marker.isMarked(95))

        self.assertFalse(self.marker.isMarked(6))
        self.assertFalse(self.marker.isMarked(29))
        self.assertFalse(self.marker.isMarked(99))

    def test_overlapping_marks_removed(self):
        """Test that overlapping marks are properly handled"""
        self.marker.mark(10, 20)
        self.marker.mark(15, 25)  # Should merge/replace

        # All indices from 15-25 should be marked
        for i in range(15, 26):
            self.assertTrue(self.marker.isMarked(i))

        # 10-14 should be unmarked (old range was replaced)
        for i in range(10, 15):
            self.assertFalse(self.marker.isMarked(i))

    def test_clear_all(self):
        """Test clearing all marks"""
        self.marker.mark(10, 20)
        self.marker.mark(30, 40)
        self.marker.clear()

        self.assertFalse(self.marker.hasMark())
        self.assertEqual(self.marker.countMarked(), 0)
        self.assertEqual(self.marker.getMarkedIndices(), [])

    def test_clear_by_type(self):
        """Test clearing marks by type"""
        self.marker.mark(10, 15, MarkType.NORMAL)
        self.marker.mark(20, 25, MarkType.PICKED)
        self.marker.mark(30, 35, MarkType.FAILED)

        self.marker.clearType(MarkType.PICKED)

        # NORMAL and FAILED should remain
        self.assertTrue(self.marker.isMarked(10))
        self.assertTrue(self.marker.isMarked(30))

        # PICKED should be gone
        self.assertFalse(self.marker.isMarked(20))

    def test_has_mark(self):
        """Test hasMark method"""
        self.assertFalse(self.marker.hasMark())

        self.marker.mark(5, 5)
        self.assertTrue(self.marker.hasMark())

        self.marker.clear()
        self.assertFalse(self.marker.hasMark())

    def test_begin_end_compatibility(self):
        """Test begin() and end() methods for backward compatibility"""
        # Empty marker
        self.assertEqual(self.marker.begin(), -1)
        self.assertEqual(self.marker.end(), -1)

        # Single range
        self.marker.mark(10, 20)
        self.assertEqual(self.marker.begin(), 10)
        self.assertEqual(self.marker.end(), 20)

        # Multiple ranges - should return overall min/max
        self.marker.mark(30, 40)
        self.assertEqual(self.marker.begin(), 10)
        self.assertEqual(self.marker.end(), 40)

    def test_reverse_range_normalization(self):
        """Test that ranges are normalized even when begin > end"""
        self.marker.mark(20, 10)  # Reversed
        self.marker.unmark(18, 12)  # Reversed

        # Should work correctly
        self.assertTrue(self.marker.isMarked(10))
        self.assertTrue(self.marker.isMarked(11))
        self.assertFalse(self.marker.isMarked(15))
        self.assertTrue(self.marker.isMarked(19))
        self.assertTrue(self.marker.isMarked(20))
