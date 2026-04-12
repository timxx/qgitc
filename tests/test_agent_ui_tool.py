# -*- coding: utf-8 -*-

import unittest

from PySide6.QtCore import QElapsedTimer, QTimer

from qgitc.agent.tool import ToolContext
from qgitc.agent.ui_tool import UiTool, UiToolDispatcher
from tests.base import TestBase


def _make_context():
    return ToolContext(
        working_directory=".",
        abort_requested=lambda: False,
    )


class TestUiTool(TestBase):

    def doCreateRepo(self):
        pass

    def test_tool_properties(self):
        tool = UiTool(
            name="ui_test",
            description="Test UI tool",
            schema={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        self.assertEqual(tool.name, "ui_test")
        self.assertEqual(tool.description, "Test UI tool")
        self.assertTrue(tool.is_read_only())
        self.assertFalse(tool.is_destructive())

    def test_openai_schema(self):
        tool = UiTool(
            name="ui_test",
            description="A test tool",
            schema={"type": "object", "properties": {}},
        )
        schema = tool.openai_schema()
        self.assertEqual(schema["function"]["name"], "ui_test")
        self.assertEqual(schema["function"]["description"], "A test tool")

    def test_execute_dispatches_to_main_thread(self):
        dispatcher = UiToolDispatcher()

        def mock_handler(tool_name, params):
            return True, "executed ok"

        dispatcher.set_handler(mock_handler)

        tool = UiTool(
            name="ui_test",
            description="test",
            schema={"type": "object", "properties": {}},
            dispatcher=dispatcher,
        )

        result = [None]

        def run_tool():
            result[0] = tool.execute({"x": "1"}, _make_context())

        QTimer.singleShot(0, run_tool)

        timer = QElapsedTimer()
        timer.start()
        while result[0] is None and timer.elapsed() < 3000:
            self.app.processEvents()

        self.assertIsNotNone(result[0])
        self.assertFalse(result[0].is_error)
        self.assertEqual(result[0].content, "executed ok")

    def test_execute_error_result(self):
        dispatcher = UiToolDispatcher()

        def mock_handler(tool_name, params):
            return False, "something went wrong"

        dispatcher.set_handler(mock_handler)

        tool = UiTool(
            name="ui_test",
            description="test",
            schema={"type": "object", "properties": {}},
            dispatcher=dispatcher,
        )

        result = [None]

        def run_tool():
            result[0] = tool.execute({"x": "1"}, _make_context())

        QTimer.singleShot(0, run_tool)

        timer = QElapsedTimer()
        timer.start()
        while result[0] is None and timer.elapsed() < 3000:
            self.app.processEvents()

        self.assertIsNotNone(result[0])
        self.assertTrue(result[0].is_error)
        self.assertEqual(result[0].content, "something went wrong")

    def test_no_dispatcher(self):
        tool = UiTool(
            name="ui_test",
            description="test",
            schema={"type": "object", "properties": {}},
        )
        result = tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("not available", result.content)


if __name__ == "__main__":
    unittest.main()
