from qgitc.mainwindow import MainWindow
from tests.base import TestBase


class TestAiFilter(TestBase):
    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.window = MainWindow()

    def tearDown(self):
        self.window = None
        super().tearDown()

    def test_ai_filter_placeholder(self):
        """Test that the AI filter placeholder is set correctly"""
        placeholder = self.window.ui.leOpts.placeholderText()
        self.assertIn("@ai", placeholder.lower(),
                      f"Placeholder should mention @ai, but got: {placeholder}")

    def test_ai_query_detection(self):
        """Test that AI queries are detected correctly"""
        self.window.ui.leOpts.setText("@ai show commits from last week")

        # Mock the AI handling to just check if it gets called
        original_handle = self.window._handleAiFilterQuery
        handled = False

        def mock_handle(query):
            nonlocal handled
            handled = True
            self.assertEqual(query, "@ai show commits from last week")

        self.window._handleAiFilterQuery = mock_handle

        # Simulate return press
        self.window._MainWindow__onOptsReturnPressed()

        self.assertTrue(handled, "AI query should have been handled")

        # Restore original method
        self.window._handleAiFilterQuery = original_handle

    def test_regular_filter_still_works(self):
        """Test that regular git log filters still work"""
        self.window.ui.leOpts.setText("--since='1 week ago'")

        # Mock filterOpts to verify it gets called
        calls = []
        original_filter = self.window.filterOpts

        def mock_filter(opts, gitView):
            calls.append((opts, gitView))

        self.window.filterOpts = mock_filter

        # Simulate return press
        self.window._MainWindow__onOptsReturnPressed()

        self.assertGreaterEqual(
            len(calls), 1, "filterOpts should have been called")
        self.assertEqual(calls[0][0], "--since='1 week ago'",
                         f"Expected '--since='1 week ago'', got {calls[0][0]}")

        # Restore original method
        self.window.filterOpts = original_filter
