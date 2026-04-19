# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.permission_presets import createPermissionEngine
from qgitc.agent.permissions import PermissionAllow, PermissionAsk
from qgitc.agent.tool import Tool, ToolContext, ToolResult


class ReadOnlyTool(Tool):
    name = "git_status"
    description = "test read-only tool"

    def isReadOnly(self):
        return True

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def inputSchema(self):
        return {"type": "object", "properties": {}}


class WriteTool(Tool):
    name = "git_commit"
    description = "test write tool"

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def inputSchema(self):
        return {"type": "object", "properties": {}}


class DangerousTool(Tool):
    name = "run_command"
    description = "test dangerous tool"

    def isDestructive(self):
        return True

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def inputSchema(self):
        return {"type": "object", "properties": {}}


class TestDefaultPreset(unittest.TestCase):

    def setUp(self):
        self.engine = createPermissionEngine(0)

    def test_read_only_allowed(self):
        result = self.engine.check(ReadOnlyTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_write_asks(self):
        result = self.engine.check(WriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)

    def test_dangerous_asks(self):
        result = self.engine.check(DangerousTool(), {})
        self.assertIsInstance(result, PermissionAsk)


class TestAggressivePreset(unittest.TestCase):

    def setUp(self):
        self.engine = createPermissionEngine(1)

    def test_read_only_allowed(self):
        result = self.engine.check(ReadOnlyTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_write_allowed(self):
        result = self.engine.check(WriteTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_dangerous_asks(self):
        result = self.engine.check(DangerousTool(), {})
        self.assertIsInstance(result, PermissionAsk)


class TestSafePreset(unittest.TestCase):

    def setUp(self):
        self.engine = createPermissionEngine(2)

    def test_read_only_asks(self):
        result = self.engine.check(ReadOnlyTool(), {})
        self.assertIsInstance(result, PermissionAsk)

    def test_write_asks(self):
        result = self.engine.check(WriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)

    def test_dangerous_asks(self):
        result = self.engine.check(DangerousTool(), {})
        self.assertIsInstance(result, PermissionAsk)


class TestAllAutoPreset(unittest.TestCase):

    def setUp(self):
        self.engine = createPermissionEngine(3)

    def test_read_only_allowed(self):
        result = self.engine.check(ReadOnlyTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_write_allowed(self):
        result = self.engine.check(WriteTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_dangerous_allowed(self):
        result = self.engine.check(DangerousTool(), {})
        self.assertIsInstance(result, PermissionAllow)


class TestUnknownStrategy(unittest.TestCase):

    def test_fallback(self):
        engine = createPermissionEngine(99)
        result = engine.check(WriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)


if __name__ == "__main__":
    unittest.main()
