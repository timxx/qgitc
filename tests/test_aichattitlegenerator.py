# -*- coding: utf-8 -*-

import unittest.mock as mock

from PySide6.QtCore import QObject, Signal

from qgitc.aichattitlegenerator import AiChatTitleGenerator
from qgitc.llm import AiParameters, AiResponse
from tests.base import TestBase


class MockAiModel(QObject):
    responseAvailable = Signal(object)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._should_emit_response = True
        self._response_message = "Test Generated Title"
        self._auto_finish = True

    def queryAsync(self, params):
        if self._should_emit_response:
            response = AiResponse()
            response.message = self._response_message
            self.responseAvailable.emit(response)
        if self._auto_finish:
            self.finished.emit()

    def setResponseMessage(self, message):
        self._response_message = message

    def setAutoFinish(self, auto_finish):
        self._auto_finish = auto_finish

    def requestInterruption(self):
        """Mock method for cancellation"""
        pass


class TestAiChatTitleGenerator(TestBase):

    def setUp(self):
        super().setUp()
        self.generator = AiChatTitleGenerator()
        self.mock_model = MockAiModel()

    def doCreateRepo(self):
        pass

    def test_start_generate_basic(self):
        """Test basic title generation flow"""
        with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
            mock_create.return_value = self.mock_model

            # Track emitted signals
            titles_received = []

            def on_title_ready(history_id, title):
                titles_received.append((history_id, title))

            self.generator.titleReady.connect(on_title_ready)

            # Start generation
            self.generator.startGenerate(
                "test-history-123", "Hello, how are you today?")

            # Verify model was created and query was called
            mock_create.assert_called_once_with(self.generator)

            # Verify title was emitted
            self.assertEqual(len(titles_received), 1)
            self.assertEqual(titles_received[0][0], "test-history-123")
            self.assertEqual(titles_received[0][1], "Test Generated Title")

    def test_response_handling_with_quotes(self):
        """Test response handling strips quotes and whitespace"""
        # Test various quote and whitespace combinations
        test_cases = [
            '"Test Title"',
            "'Test Title'",
            ' "Test Title" ',
            '  Test Title  ',
            '"\'Test Title\'"',
        ]

        for test_response in test_cases:
            with self.subTest(response=test_response):
                with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
                    # Create a fresh generator for each test case
                    generator = AiChatTitleGenerator()

                    mock_model = MockAiModel()
                    mock_model.setResponseMessage(test_response)
                    mock_create.return_value = mock_model

                    titles_received = []

                    def on_title_ready(history_id, title):
                        titles_received.append((history_id, title))

                    generator.titleReady.connect(on_title_ready)
                    generator.startGenerate("test-id", "Test message")

                    # Should clean up to just "Test Title"
                    self.assertEqual(len(titles_received), 1)
                    self.assertEqual(titles_received[0][1], "Test Title")

    def test_response_too_short_ignored(self):
        """Test that very short responses are ignored"""
        with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
            mock_model = MockAiModel()
            mock_model.setResponseMessage("Hi")  # Too short (3 chars or less)
            mock_create.return_value = mock_model

            titles_received = []

            def on_title_ready(history_id, title):
                titles_received.append((history_id, title))

            self.generator.titleReady.connect(on_title_ready)
            self.generator.startGenerate("test-id", "Test message")

            # Should not emit any title
            self.assertEqual(len(titles_received), 0)

    def test_empty_response_ignored(self):
        """Test that empty responses are ignored"""
        with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
            mock_model = MockAiModel()
            mock_model.setResponseMessage("")
            mock_create.return_value = mock_model

            titles_received = []

            def on_title_ready(history_id, title):
                titles_received.append((history_id, title))

            self.generator.titleReady.connect(on_title_ready)
            self.generator.startGenerate("test-id", "Test message")

            # Should not emit any title
            self.assertEqual(len(titles_received), 0)

    def test_cancel_existing_model(self):
        """Test canceling existing model when starting new generation"""
        with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
            first_model = MockAiModel()
            # Don't auto finish so we can check the model
            first_model.setAutoFinish(False)
            second_model = MockAiModel()
            # Don't auto finish the second one either
            second_model.setAutoFinish(False)

            # Mock creating different models for each call
            mock_create.side_effect = [first_model, second_model]

            # Start first generation
            self.generator.startGenerate("first-id", "First message")
            self.assertEqual(self.generator._model, first_model)

            # Start second generation (should cancel first)
            self.generator.startGenerate("second-id", "Second message")
            self.assertEqual(self.generator._model, second_model)

            # Verify both models were created
            self.assertEqual(mock_create.call_count, 2)

    def test_manual_cancel(self):
        """Test manual cancellation"""
        with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
            mock_model = MockAiModel()
            # Don't auto finish so we can check the model
            mock_model.setAutoFinish(False)
            mock_create.return_value = mock_model

            # Start generation
            self.generator.startGenerate("test-id", "Test message")
            self.assertIsNotNone(self.generator._model)

            # Cancel manually
            self.generator.cancel()
            self.assertIsNone(self.generator._model)

    def test_model_finished_cleanup(self):
        """Test that model is cleaned up when finished signal is emitted"""
        with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
            mock_model = MockAiModel()
            mock_model.setAutoFinish(False)  # Don't auto finish initially
            mock_create.return_value = mock_model

            # Start generation
            self.generator.startGenerate("test-id", "Test message")
            self.assertIsNotNone(self.generator._model)

            # Manually emit finished signal
            mock_model.finished.emit()

            # Model should be cleaned up
            self.assertIsNone(self.generator._model)

    def test_long_message_truncation(self):
        """Test that long messages are truncated to 512 characters"""
        with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
            mock_model = MockAiModel()
            captured_params = []

            def capture_query(params):
                captured_params.append(params)
                if mock_model._should_emit_response:
                    response = AiResponse()
                    response.message = "Generated Title"
                    mock_model.responseAvailable.emit(response)
                mock_model.finished.emit()

            mock_model.queryAsync = capture_query
            mock_create.return_value = mock_model

            # Create a very long message
            long_message = "A" * 1000

            self.generator.startGenerate("test-id", long_message)

            # Verify message was truncated
            self.assertEqual(len(captured_params), 1)
            prompt = captured_params[0].prompt
            # Should contain only first 512 characters of the message
            self.assertIn("A" * 512, prompt)
            # Should not contain more than 512 A's consecutively
            self.assertNotIn("A" * 513, prompt)

    def test_ai_parameters_configuration(self):
        """Test that AiParameters are configured correctly"""
        with mock.patch('qgitc.aichattitlegenerator.AiModelProvider.createModel') as mock_create:
            mock_model = MockAiModel()
            captured_params = []

            def capture_query(params):
                captured_params.append(params)
                mock_model.finished.emit()

            mock_model.queryAsync = capture_query
            mock_create.return_value = mock_model

            self.generator.startGenerate("test-id", "Test message")

            # Verify parameters
            self.assertEqual(len(captured_params), 1)
            params = captured_params[0]
            self.assertIsInstance(params, AiParameters)
            self.assertEqual(params.temperature, 0.3)
            self.assertEqual(params.max_tokens, 1024)
            self.assertEqual(params.stream, False)
            # Check that the base prompt template is in the prompt (before formatting)
            self.assertIn("Please write a brief title for the following request", params.prompt)
            self.assertIn("Test message", params.prompt)
