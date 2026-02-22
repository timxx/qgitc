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

        # Mock the AI chat widget's queryAgent method
        chatWidget = self.window._aiChat.chatWidget()
        original_query = chatWidget.queryAgent
        handled = False
        captured_args = {}

        def mock_query(prompt, contextText=None, sysPrompt=None, toolNames=None):
            nonlocal handled, captured_args
            handled = True
            captured_args = {
                'prompt': prompt,
                'contextText': contextText,
                'sysPrompt': sysPrompt,
                'toolNames': toolNames
            }

        chatWidget.queryAgent = mock_query

        # Simulate return press
        self.window._MainWindow__onOptsReturnPressed()

        self.assertTrue(handled, "AI query should have been handled")
        self.assertEqual(captured_args['prompt'], "show commits from last week",
                         f"Expected 'show commits from last week', got {captured_args['prompt']}")
        self.assertIsNotNone(
            captured_args['sysPrompt'], "System prompt should be provided")
        self.assertEqual(captured_args['toolNames'], ["ui_apply_log_filter"],
                         f"Expected ['ui_apply_log_filter'], got {captured_args['toolNames']}")

        # Restore original method
        chatWidget.queryAgent = original_query

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
