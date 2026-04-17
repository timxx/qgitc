# -*- coding: utf-8 -*-

import unittest
from typing import Iterator

from PySide6.QtCore import QElapsedTimer
from PySide6.QtTest import QSignalSpy

from qgitc.agent.agent_loop import AgentLoop, QueryParams
from qgitc.agent.permissions import PermissionEngine
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ToolCallDelta,
)
from qgitc.agent.skills.registry import SkillRegistry
from qgitc.agent.skills.types import SkillDefinition
from qgitc.agent.tool import Tool, ToolResult
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.tools.skill import SkillTool
from qgitc.agent.types import TextBlock, ToolResultBlock, UserMessage
from tests.base import TestBase


def wait_for(app, condition, timeout=5000):
    timer = QElapsedTimer()
    timer.start()
    while not condition() and timer.elapsed() < timeout:
        app.processEvents()


class SequenceProvider(ModelProvider):

    def __init__(self):
        self._call_count = 0

    def stream(self, messages, tools=None, model=None, max_tokens=4096):
        # type: (...) -> Iterator
        self._call_count += 1
        if self._call_count == 1:
            yield ToolCallDelta(id="skill_1", name="Skill", arguments_delta='{"skill":"review"}')
            yield MessageComplete(stop_reason="tool_use")
        elif self._call_count == 2:
            yield ToolCallDelta(
                id="cmd_1",
                name="run_command",
                arguments_delta='{"command":"echo hi"}',
            )
            yield MessageComplete(stop_reason="tool_use")
        else:
            yield ContentDelta(text="done")
            yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        return 10

class InspectSkillInjectionProvider(ModelProvider):

    def __init__(self):
        self._call_count = 0
        self.saw_queued_prompt = False
        self.saw_status_tool_result = False

    def stream(self, messages, tools=None, model=None, max_tokens=4096):
        # type: (...) -> Iterator
        self._call_count += 1
        if self._call_count == 1:
            yield ToolCallDelta(id="skill_1", name="Skill", arguments_delta='{"skill":"review"}')
            yield MessageComplete(stop_reason="tool_use")
            return

        for msg in messages:
            if isinstance(msg, UserMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and "Use this checklist" in block.text:
                        self.saw_queued_prompt = True
                    if isinstance(block, ToolResultBlock) and "Successfully loaded skill" in block.content:
                        self.saw_status_tool_result = True

        yield ContentDelta(text="done")
        yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        return 10


class DummyRunCommandTool(Tool):
    name = "run_command"
    description = "Dummy command tool"

    def execute(self, input_data, context):
        return ToolResult(content="command executed")

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
            },
            "required": ["command"],
        }


class TestAgentLoopSkills(TestBase):

    def setUp(self):
        super().setUp()

        self.provider = SequenceProvider()
        self.registry = ToolRegistry()
        self.registry.register(SkillTool())
        self.registry.register(DummyRunCommandTool())

        self.skill_registry = SkillRegistry()
        self.skill_registry.register(SkillDefinition(
            name="review",
            description="Review code changes",
            content="Use this checklist",
            allowed_tools=["read_file"],
        ))

        self.loop = AgentLoop(
            tool_registry=self.registry,
            permission_engine=PermissionEngine(),
            system_prompt="Base prompt"
        )

        self.params = QueryParams(
            provider=self.provider,
            skill_registry=self.skill_registry,
        )

    def tearDown(self):
        self.loop.abort()
        self.loop.wait(3000)
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_skill_allowlist_blocks_disallowed_tool(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)
        result_spy = QSignalSpy(self.loop.toolCallResult)

        self.loop.submit("Do review", self.params)
        wait_for(self.app, lambda: finished_spy.count() > 0)

        self.assertGreaterEqual(result_spy.count(), 2)
        found_block = False
        for i in range(result_spy.count()):
            call_id = result_spy.at(i)[0]
            content = result_spy.at(i)[2]
            is_error = result_spy.at(i)[3]
            if call_id == "cmd_1":
                found_block = True
                self.assertTrue(is_error)
                self.assertIn("not allowed", content)

        self.assertTrue(found_block)

    def test_skill_prompt_is_injected_and_tool_result_is_status(self):
        self.provider = InspectSkillInjectionProvider()
        self.loop = AgentLoop(
            tool_registry=self.registry,
            permission_engine=PermissionEngine(),
            system_prompt="Base prompt"
        )
        self._connect_loop_signals()

        params = QueryParams(
            provider=self.provider,
            skill_registry=self.skill_registry,
        )

        finished_spy = QSignalSpy(self.loop.agentFinished)
        self.loop.submit("Do review", params)
        wait_for(self.app, lambda: finished_spy.count() > 0)

        self.assertTrue(self.provider.saw_queued_prompt)
        self.assertTrue(self.provider.saw_status_tool_result)

    def _connect_loop_signals(self):
        self.loop.textDelta.connect(lambda _x: None)
        self.loop.reasoningDelta.connect(lambda _x: None)
        self.loop.toolCallStart.connect(lambda _a, _b, _c: None)
        self.loop.toolCallResult.connect(lambda _a, _b, _c, _d: None)
        self.loop.turnComplete.connect(lambda _x: None)
        self.loop.permissionRequired.connect(lambda _a, _b, _c: None)
        self.loop.errorOccurred.connect(lambda _x: None)
