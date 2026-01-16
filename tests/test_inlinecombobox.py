# -*- coding: utf-8 -*-

import sys
import unittest

from PySide6.QtCore import Qt

from qgitc.inlinecombobox import InlineComboBox
from tests.base import TestBase


class TestInlineComboBox(TestBase):
    """Test suite for InlineComboBox widget"""

    def setUp(self):
        """Set up test fixtures"""
        super().setUp()
        self.combo = InlineComboBox()

    def tearDown(self):
        """Clean up after each test"""
        if self.combo:
            self.combo.deleteLater()
            self.combo = None
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_initial_state(self):
        """Test initial state of empty combobox"""
        self.assertEqual(self.combo.count(), 0)
        self.assertEqual(self.combo.currentIndex(), -1)
        self.assertEqual(self.combo.currentText(), "")
        self.assertIsNone(self.combo.currentData())

    def test_add_item_text_only(self):
        """Test adding items with text only"""
        self.combo.addItem("Item 1")
        self.combo.addItem("Item 2")
        self.combo.addItem("Item 3")

        self.assertEqual(self.combo.count(), 3)
        self.assertEqual(self.combo.currentIndex(), 0)
        self.assertEqual(self.combo.currentText(), "Item 1")

    def test_add_item_with_user_data(self):
        """Test adding items with user data"""
        obj1 = {"id": 1}
        obj2 = {"id": 2}
        obj3 = {"id": 3}

        self.combo.addItem("First", obj1)
        self.combo.addItem("Second", obj2)
        self.combo.addItem("Third", obj3)

        self.assertEqual(self.combo.count(), 3)
        self.assertEqual(self.combo.currentData(), obj1)

    def test_set_current_index(self):
        """Test setting current index"""
        self.combo.addItem("Item 1", "data1")
        self.combo.addItem("Item 2", "data2")
        self.combo.addItem("Item 3", "data3")

        # Test valid index
        self.combo.setCurrentIndex(1)
        self.assertEqual(self.combo.currentIndex(), 1)
        self.assertEqual(self.combo.currentText(), "Item 2")
        self.assertEqual(self.combo.currentData(), "data2")

        # Test another valid index
        self.combo.setCurrentIndex(2)
        self.assertEqual(self.combo.currentIndex(), 2)
        self.assertEqual(self.combo.currentText(), "Item 3")
        self.assertEqual(self.combo.currentData(), "data3")

    def test_set_current_index_invalid(self):
        """Test setting invalid index doesn't change state"""
        self.combo.addItem("Item 1")
        self.combo.addItem("Item 2")

        # Try invalid indices
        self.combo.setCurrentIndex(-1)
        self.assertEqual(self.combo.currentIndex(), 0)

        self.combo.setCurrentIndex(10)
        self.assertEqual(self.combo.currentIndex(), 0)

    def test_current_index_changed_signal(self):
        """Test that currentIndexChanged signal is emitted"""
        self.combo.addItem("Item 1")
        self.combo.addItem("Item 2")

        signal_received = []

        def on_index_changed(index):
            signal_received.append(index)

        self.combo.currentIndexChanged.connect(on_index_changed)

        self.combo.setCurrentIndex(1)
        self.assertEqual(signal_received, [1])

        # Setting same index shouldn't emit signal
        self.combo.setCurrentIndex(1)
        self.assertEqual(signal_received, [1])

    def test_item_text(self):
        """Test itemText method"""
        self.combo.addItem("First")
        self.combo.addItem("Second")
        self.combo.addItem("Third")

        self.assertEqual(self.combo.itemText(0), "First")
        self.assertEqual(self.combo.itemText(1), "Second")
        self.assertEqual(self.combo.itemText(2), "Third")
        self.assertEqual(self.combo.itemText(-1), "")
        self.assertEqual(self.combo.itemText(10), "")

    def test_item_data(self):
        """Test itemData method"""
        data1 = {"value": 1}
        data2 = {"value": 2}
        data3 = None

        self.combo.addItem("First", data1)
        self.combo.addItem("Second", data2)
        self.combo.addItem("Third", data3)

        self.assertEqual(self.combo.itemData(0), data1)
        self.assertEqual(self.combo.itemData(1), data2)
        self.assertIsNone(self.combo.itemData(2))
        self.assertIsNone(self.combo.itemData(-1))
        self.assertIsNone(self.combo.itemData(10))

    def test_set_current_text(self):
        """Test setCurrentText method"""
        self.combo.addItem("Apple")
        self.combo.addItem("Banana")
        self.combo.addItem("Cherry")

        self.combo.setCurrentText("Banana")
        self.assertEqual(self.combo.currentIndex(), 1)
        self.assertEqual(self.combo.currentText(), "Banana")

        # Non-existent text should not change selection
        self.combo.setCurrentText("Orange")
        self.assertEqual(self.combo.currentIndex(), 1)

    def test_find_data(self):
        """Test findData method"""
        obj1 = {"id": 1}
        obj2 = {"id": 2}
        obj3 = {"id": 3}

        self.combo.addItem("First", obj1)
        self.combo.addItem("Second", obj2)
        self.combo.addItem("Third", obj3)

        self.assertEqual(self.combo.findData(obj1), 0)
        self.assertEqual(self.combo.findData(obj2), 1)
        self.assertEqual(self.combo.findData(obj3), 2)

        # Non-existent data
        obj_missing = {"id": 99}
        self.assertEqual(self.combo.findData(obj_missing), -1)

    def test_find_data_with_none(self):
        """Test findData with None values"""
        self.combo.addItem("First", None)
        self.combo.addItem("Second", "data")
        self.combo.addItem("Third", None)

        # findData uses identity check (is), so it should find first None
        index = self.combo.findData(None)
        self.assertIn(index, [0, 2])  # Could match either None

    def test_clear(self):
        """Test clear method"""
        self.combo.addItem("Item 1")
        self.combo.addItem("Item 2")
        self.combo.addItem("Item 3")

        self.assertEqual(self.combo.count(), 3)

        self.combo.clear()

        self.assertEqual(self.combo.count(), 0)
        self.assertEqual(self.combo.currentIndex(), -1)
        self.assertEqual(self.combo.currentText(), "")
        self.assertIsNone(self.combo.currentData())

    def test_unicode_text(self):
        """Test handling of Unicode text including emoji"""
        self.combo.addItem("💬 Chat")
        self.combo.addItem("📝 Code Review")
        self.combo.addItem("🔧 Agent")

        self.assertEqual(self.combo.count(), 3)
        self.assertEqual(self.combo.currentText(), "💬 Chat")
        self.assertEqual(self.combo.itemText(1), "📝 Code Review")

    def test_size_hint(self):
        """Test sizeHint returns reasonable values"""
        self.combo.addItem("Test")

        size = self.combo.sizeHint()
        self.assertGreater(size.width(), 0)
        self.assertGreater(size.height(), 0)

        # Longer text should result in wider size hint
        self.combo.addItem("Much Longer Text Here")
        self.combo.setCurrentIndex(1)

        larger_size = self.combo.sizeHint()
        self.assertGreater(larger_size.width(), size.width())

    def test_minimum_size_hint(self):
        """Test minimumSizeHint returns reasonable values"""
        self.combo.addItem("Test")

        min_size = self.combo.minimumSizeHint()
        self.assertGreater(min_size.width(), 0)
        self.assertGreater(min_size.height(), 0)

        # Minimum size should be smaller than regular size hint
        size = self.combo.sizeHint()
        self.assertLessEqual(min_size.width(), size.width())

    def test_enabled_state(self):
        """Test enabled/disabled state"""
        self.combo.addItem("Item 1")
        self.combo.addItem("Item 2")

        self.assertTrue(self.combo.isEnabled())

        self.combo.setEnabled(False)
        self.assertFalse(self.combo.isEnabled())

        self.combo.setEnabled(True)
        self.assertTrue(self.combo.isEnabled())

    def test_focus_policy(self):
        """Test focus policy is set correctly"""
        self.assertEqual(self.combo.focusPolicy(), Qt.StrongFocus)

    def test_mouse_cursor(self):
        """Test mouse cursor is set to pointing hand"""
        self.assertEqual(self.combo.cursor().shape(), Qt.PointingHandCursor)

    def test_multiple_data_objects(self):
        """Test using different object types as user data"""
        # Test with different types
        data_types = [
            ("String", "string_data"),
            ("Integer", 42),
            ("Float", 3.14),
            ("List", [1, 2, 3]),
            ("Dict", {"key": "value"}),
            ("None", None),
        ]

        for text, data in data_types:
            self.combo.addItem(text, data)

        for i, (text, data) in enumerate(data_types):
            self.assertEqual(self.combo.itemData(i), data)
            if data is not None:  # Skip None for findData (ambiguous)
                self.assertEqual(self.combo.findData(data), i)

    def test_empty_text(self):
        """Test handling of empty text"""
        self.combo.addItem("")
        self.combo.addItem("Normal Text")

        self.assertEqual(self.combo.count(), 2)
        self.assertEqual(self.combo.currentText(), "")

        self.combo.setCurrentIndex(1)
        self.assertEqual(self.combo.currentText(), "Normal Text")
