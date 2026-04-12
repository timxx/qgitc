# Agent Loop Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old tool orchestration system (AgentToolMachine, AgentToolExecutor, strategies) with the new AgentLoop-based architecture for all chat modes.

**Architecture:** Bridge-and-swap approach. First build bridge layers (message conversion, permission presets, UI tool wrappers, tool registration). Then swap AiChatWidget to use AgentLoop. Then simplify AiModelBase. Then refactor ResolveConflictJob. Then remove old modules.

**Tech Stack:** Python 3, PySide6 (Qt), qgitc agent framework

---

## File Map

**New files to create:**
- `qgitc/agent/message_convert.py` — Two-way conversion between agent Message types and history dict format
- `qgitc/agent/permission_presets.py` — Factory functions mapping strategy ints to PermissionEngine
- `qgitc/agent/ui_tool.py` — UiTool wrapper + UiToolDispatcher for cross-thread UI tool execution
- `qgitc/agent/tool_registration.py` — Function to register all built-in tools into a ToolRegistry
- `tests/test_agent_message_convert.py` — Tests for message conversion
- `tests/test_agent_permission_presets.py` — Tests for permission presets
- `tests/test_agent_ui_tool.py` — Tests for UI tool wrapper
- `tests/test_agent_tool_registration.py` — Tests for tool registration

**Existing files to modify:**
- `qgitc/agent/__init__.py` — Export new modules
- `qgitc/agent/agent_loop.py` — Add `set_messages()` and `set_system_prompt()` methods
- `qgitc/aichatwidget.py` — Replace old orchestration with AgentLoop integration
- `qgitc/aichathistorystore.py` — Add `updateFromMessages()` method
- `qgitc/aichatcontextprovider.py` — Change `uiTools()` return type from `AgentTool` to `Tool`
- `qgitc/mainwindowcontextprovider.py` — Convert UI tools to new `Tool` subclasses
- `qgitc/commitcontextprovider.py` — Same
- `qgitc/aichatbot.py` — Update ToolType import source
- `qgitc/aitoolconfirmation.py` — Add ToolType constants or import from new location

**Files to delete (cleanup phase):**
- `qgitc/agenttools.py`
- `qgitc/agenttoolexecutor.py`
- `qgitc/agentmachine.py`
- `qgitc/uitoolexecutor.py`

---

## Phase 1: Bridge Layers

### Task 1: Add message conversion utilities

**Files:**
- Create: `qgitc/agent/message_convert.py`
- Create: `tests/test_agent_message_convert.py`

- [ ] **Step 1: Write failing tests for messages_to_history_dicts**

Create `tests/test_agent_message_convert.py`:

```python
# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.types import (
    AssistantMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from qgitc.agent.message_convert import (
    history_dicts_to_messages,
    messages_to_history_dicts,
)


class TestMessagesToHistoryDicts(unittest.TestCase):

    def test_user_text_message(self):
        msgs = [UserMessage(content=[TextBlock(text="Hello")])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(len(dicts), 1)
        self.assertEqual(dicts[0]["role"], "user")
        self.assertEqual(dicts[0]["content"], "Hello")
        self.assertIsNone(dicts[0].get("tool_calls"))

    def test_assistant_text_message(self):
        msgs = [AssistantMessage(content=[TextBlock(text="Hi there")])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["role"], "assistant")
        self.assertEqual(dicts[0]["content"], "Hi there")

    def test_assistant_with_reasoning(self):
        msgs = [AssistantMessage(content=[
            ThinkingBlock(thinking="Let me think..."),
            TextBlock(text="Answer"),
        ])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["content"], "Answer")
        self.assertEqual(dicts[0]["reasoning"], "Let me think...")

    def test_assistant_tool_call(self):
        msgs = [AssistantMessage(content=[
            TextBlock(text="I'll check"),
            ToolUseBlock(id="call_1", name="git_status", input={"untracked": True}),
        ])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["content"], "I'll check")
        tc = dicts[0]["tool_calls"]
        self.assertIsInstance(tc, list)
        self.assertEqual(len(tc), 1)
        self.assertEqual(tc[0]["id"], "call_1")
        self.assertEqual(tc[0]["function"]["name"], "git_status")

    def test_tool_result_message(self):
        """Tool results are UserMessages containing ToolResultBlocks."""
        msgs = [UserMessage(content=[
            ToolResultBlock(tool_use_id="call_1", content="output", is_error=False),
        ])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["role"], "tool")
        self.assertEqual(dicts[0]["content"], "output")
        self.assertEqual(dicts[0]["tool_calls"], {"tool_call_id": "call_1"})

    def test_system_message(self):
        msgs = [SystemMessage(subtype="system", content="You are helpful")]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["role"], "system")
        self.assertEqual(dicts[0]["content"], "You are helpful")

    def test_multiple_tool_results_expand(self):
        """A UserMessage with 2 ToolResultBlocks becomes 2 dicts."""
        msgs = [UserMessage(content=[
            ToolResultBlock(tool_use_id="c1", content="out1"),
            ToolResultBlock(tool_use_id="c2", content="out2"),
        ])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(len(dicts), 2)
        self.assertEqual(dicts[0]["role"], "tool")
        self.assertEqual(dicts[0]["tool_calls"], {"tool_call_id": "c1"})
        self.assertEqual(dicts[1]["tool_calls"], {"tool_call_id": "c2"})


class TestHistoryDictsToMessages(unittest.TestCase):

    def test_user_message(self):
        dicts = [{"role": "user", "content": "Hello"}]
        msgs = history_dicts_to_messages(dicts)
        self.assertEqual(len(msgs), 1)
        self.assertIsInstance(msgs[0], UserMessage)
        self.assertEqual(msgs[0].content[0].text, "Hello")

    def test_assistant_message(self):
        dicts = [{"role": "assistant", "content": "Hi there"}]
        msgs = history_dicts_to_messages(dicts)
        self.assertIsInstance(msgs[0], AssistantMessage)
        self.assertEqual(msgs[0].content[0].text, "Hi there")

    def test_assistant_with_reasoning(self):
        dicts = [{"role": "assistant", "content": "Answer", "reasoning": "Let me think..."}]
        msgs = history_dicts_to_messages(dicts)
        self.assertIsInstance(msgs[0], AssistantMessage)
        blocks = msgs[0].content
        thinking_blocks = [b for b in blocks if isinstance(b, ThinkingBlock)]
        text_blocks = [b for b in blocks if isinstance(b, TextBlock)]
        self.assertEqual(len(thinking_blocks), 1)
        self.assertEqual(thinking_blocks[0].thinking, "Let me think...")
        self.assertEqual(text_blocks[0].text, "Answer")

    def test_assistant_with_tool_calls(self):
        dicts = [{
            "role": "assistant",
            "content": "Checking",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "git_status", "arguments": '{"untracked": true}'},
            }],
        }]
        msgs = history_dicts_to_messages(dicts)
        blocks = msgs[0].content
        text_blocks = [b for b in blocks if isinstance(b, TextBlock)]
        tool_blocks = [b for b in blocks if isinstance(b, ToolUseBlock)]
        self.assertEqual(text_blocks[0].text, "Checking")
        self.assertEqual(tool_blocks[0].id, "call_1")
        self.assertEqual(tool_blocks[0].name, "git_status")
        self.assertEqual(tool_blocks[0].input, {"untracked": True})

    def test_tool_result(self):
        dicts = [{
            "role": "tool",
            "content": "output text",
            "tool_calls": {"tool_call_id": "call_1"},
        }]
        msgs = history_dicts_to_messages(dicts)
        self.assertIsInstance(msgs[0], UserMessage)
        self.assertIsInstance(msgs[0].content[0], ToolResultBlock)
        self.assertEqual(msgs[0].content[0].tool_use_id, "call_1")
        self.assertEqual(msgs[0].content[0].content, "output text")

    def test_system_message(self):
        dicts = [{"role": "system", "content": "You are helpful"}]
        msgs = history_dicts_to_messages(dicts)
        self.assertIsInstance(msgs[0], SystemMessage)
        self.assertEqual(msgs[0].content, "You are helpful")

    def test_roundtrip(self):
        """Convert messages -> dicts -> messages and verify structure preserved."""
        original = [
            UserMessage(content=[TextBlock(text="Hello")]),
            AssistantMessage(content=[
                ThinkingBlock(thinking="Hmm"),
                TextBlock(text="Answer"),
                ToolUseBlock(id="c1", name="git_status", input={}),
            ]),
            UserMessage(content=[
                ToolResultBlock(tool_use_id="c1", content="clean"),
            ]),
            AssistantMessage(content=[TextBlock(text="All good")]),
        ]
        dicts = messages_to_history_dicts(original)
        restored = history_dicts_to_messages(dicts)
        dicts2 = messages_to_history_dicts(restored)
        self.assertEqual(dicts, dicts2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_message_convert.py -v`
Expected: ImportError — `message_convert` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `qgitc/agent/message_convert.py`:

```python
# -*- coding: utf-8 -*-

import json
from typing import Any, Dict, List

from qgitc.agent.types import (
    AssistantMessage,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


def messages_to_history_dicts(messages):
    # type: (List[Message]) -> List[Dict[str, Any]]
    """Convert agent Message list to the history store dict format.

    Each dict has: role, content, reasoning, description, tool_calls, reasoning_data.
    A UserMessage containing multiple ToolResultBlocks is expanded into
    one dict per result (matching the old per-tool-call history format).
    """
    result = []  # type: List[Dict[str, Any]]

    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({
                "role": "system",
                "content": msg.content,
            })

        elif isinstance(msg, UserMessage):
            tool_results = [b for b in msg.content if isinstance(b, ToolResultBlock)]
            if tool_results:
                # Expand each ToolResultBlock into its own tool-role dict.
                for tr in tool_results:
                    result.append({
                        "role": "tool",
                        "content": tr.content,
                        "description": None,
                        "tool_calls": {"tool_call_id": tr.tool_use_id},
                    })
            else:
                text = _extract_text(msg.content)
                result.append({
                    "role": "user",
                    "content": text,
                })

        elif isinstance(msg, AssistantMessage):
            text = _extract_text(msg.content)
            reasoning = _extract_reasoning(msg.content)
            tool_calls = _extract_tool_calls(msg.content)
            entry = {
                "role": "assistant",
                "content": text,
            }  # type: Dict[str, Any]
            if reasoning:
                entry["reasoning"] = reasoning
            if tool_calls:
                entry["tool_calls"] = tool_calls
            result.append(entry)

    return result


def history_dicts_to_messages(dicts):
    # type: (List[Dict[str, Any]]) -> List[Message]
    """Convert history store dicts back to agent Message list.

    Consecutive tool-role dicts are merged into a single UserMessage
    containing ToolResultBlocks.
    """
    messages = []  # type: List[Message]
    i = 0
    while i < len(dicts):
        d = dicts[i]
        role = d.get("role", "user")

        if role == "system":
            messages.append(SystemMessage(
                subtype="system",
                content=d.get("content") or "",
            ))
            i += 1

        elif role == "user":
            content = []
            text = d.get("content") or ""
            if text:
                content.append(TextBlock(text=text))
            messages.append(UserMessage(content=content))
            i += 1

        elif role == "assistant":
            content = []
            reasoning = d.get("reasoning")
            if reasoning:
                content.append(ThinkingBlock(thinking=reasoning))
            text = d.get("content") or ""
            if text:
                content.append(TextBlock(text=text))
            tool_calls = d.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    func = tc.get("function") or {}
                    args_raw = func.get("arguments", "{}")
                    if isinstance(args_raw, str):
                        try:
                            args = json.loads(args_raw)
                        except (json.JSONDecodeError, ValueError):
                            args = {}
                    else:
                        args = args_raw if isinstance(args_raw, dict) else {}
                    content.append(ToolUseBlock(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        input=args,
                    ))
            messages.append(AssistantMessage(content=content))
            i += 1

        elif role == "tool":
            # Collect consecutive tool results into one UserMessage.
            tool_results = []
            while i < len(dicts) and dicts[i].get("role") == "tool":
                td = dicts[i]
                tc_data = td.get("tool_calls")
                if isinstance(tc_data, dict):
                    tc_id = tc_data.get("tool_call_id", "")
                elif isinstance(tc_data, str):
                    tc_id = tc_data
                else:
                    tc_id = ""
                tool_results.append(ToolResultBlock(
                    tool_use_id=tc_id,
                    content=td.get("content") or "",
                    is_error=False,
                ))
                i += 1
            messages.append(UserMessage(content=tool_results))

        else:
            i += 1

    return messages


def _extract_text(content):
    # type: (list) -> str
    parts = []
    for block in content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
    return "".join(parts)


def _extract_reasoning(content):
    # type: (list) -> str
    parts = []
    for block in content:
        if isinstance(block, ThinkingBlock):
            parts.append(block.thinking)
    return "".join(parts) if parts else None


def _extract_tool_calls(content):
    # type: (list) -> list
    calls = []
    for block in content:
        if isinstance(block, ToolUseBlock):
            calls.append({
                "id": block.id,
                "type": "function",
                "function": {
                    "name": block.name,
                    "arguments": json.dumps(block.input, ensure_ascii=False),
                },
            })
    return calls if calls else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_message_convert.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/message_convert.py tests/test_agent_message_convert.py
git commit -m "Add message conversion between agent types and history dicts"
git push
```

---

### Task 2: Add permission presets

**Files:**
- Create: `qgitc/agent/permission_presets.py`
- Create: `tests/test_agent_permission_presets.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agent_permission_presets.py`:

```python
# -*- coding: utf-8 -*-

import unittest
from typing import Any, Dict

from qgitc.agent.permissions import PermissionAllow, PermissionAsk
from qgitc.agent.permission_presets import create_permission_engine
from qgitc.agent.tool import Tool, ToolContext, ToolResult


class ReadOnlyTool(Tool):
    name = "git_status"
    description = "test read-only tool"

    def is_read_only(self):
        return True

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class WriteTool(Tool):
    name = "git_commit"
    description = "test write tool"

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class DangerousTool(Tool):
    name = "run_command"
    description = "test dangerous tool"

    def is_destructive(self):
        return True

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class TestDefaultPreset(unittest.TestCase):
    """Strategy 0: auto-run read-only, ask for rest."""

    def setUp(self):
        self.engine = create_permission_engine(0)

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
    """Strategy 1: auto-run read-only + write, ask for destructive."""

    def setUp(self):
        self.engine = create_permission_engine(1)

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
    """Strategy 2: ask for everything."""

    def setUp(self):
        self.engine = create_permission_engine(2)

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
    """Strategy 3: auto-run everything."""

    def setUp(self):
        self.engine = create_permission_engine(3)

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
    """Unknown strategy values should fall back to default."""

    def test_fallback(self):
        engine = create_permission_engine(99)
        result = engine.check(WriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_permission_presets.py -v`
Expected: ImportError — `permission_presets` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `qgitc/agent/permission_presets.py`:

```python
# -*- coding: utf-8 -*-

from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionBehavior,
    PermissionEngine,
    PermissionRule,
)


def create_permission_engine(strategy_value):
    # type: (int) -> PermissionEngine
    """Create a PermissionEngine from a strategy setting value.

    Strategy values:
        0 (Default)    - Allow read-only tools automatically, ask for rest
        1 (Aggressive) - Allow read-only + non-destructive, ask for destructive
        2 (Safe)       - Ask for all tools
        3 (AllAuto)    - Allow all tools automatically
    """
    if strategy_value == 1:
        return _aggressive_engine()
    if strategy_value == 2:
        return _safe_engine()
    if strategy_value == 3:
        return _all_auto_engine()
    return _default_engine()


def _default_engine():
    # type: () -> PermissionEngine
    """Read-only tools auto-allowed (via PermissionEngine default behavior),
    everything else asks."""
    return PermissionEngine()


def _aggressive_engine():
    # type: () -> PermissionEngine
    """Allow all tools EXCEPT destructive ones.

    We use a wildcard allow rule for everything, then
    PermissionEngine.check() handles the rest:
    - Deny rules are checked first (none here)
    - Allow rules are checked next (wildcard matches all)
    - But we want destructive tools to still ask, so we don't use a
      blanket allow. Instead we rely on the fact that
      PermissionEngine allows read-only tools by default, and we add
      allow rules for non-destructive, non-read-only tools.

    Approach: We use a wildcard allow rule. PermissionEngine checks deny
    first, then allow. Since destructive tools should ask, we add no allow
    rule and instead override check behavior.

    Simpler: just allow "*" and the engine will allow everything.
    Then for destructive: we can't distinguish in rules alone.

    Best approach: Use PermissionEngine subclass or a custom check.
    Actually: PermissionEngine._rule_matches checks tool_name with fnmatch.
    We can allow "*" for all, but then destructive tools get allowed too.

    So: Create allow rules for all known non-destructive tool names?
    No - too brittle. Better to create a simple subclass.
    """
    # Wildcard allow rule matches everything. Destructive tools need asking.
    # Since PermissionEngine checks deny before allow, we can't express
    # "allow non-destructive" with simple rules.
    # Use the _AggressivePermissionEngine that overrides check().
    return _AggressivePermissionEngine()


class _AggressivePermissionEngine(PermissionEngine):
    """Allow read-only and non-destructive tools; ask for destructive."""

    def __init__(self):
        super().__init__()

    def check(self, tool, input_data):
        if tool.is_read_only():
            return PermissionAllow()
        if not tool.is_destructive():
            return PermissionAllow()
        return PermissionAsk()


class _SafePermissionEngine(PermissionEngine):
    """Ask for all tools regardless of type."""

    def __init__(self):
        super().__init__()

    def check(self, tool, input_data):
        return PermissionAsk()


class _AllAutoPermissionEngine(PermissionEngine):
    """Allow all tools automatically."""

    def __init__(self):
        super().__init__()

    def check(self, tool, input_data):
        return PermissionAllow()


def _safe_engine():
    # type: () -> PermissionEngine
    return _SafePermissionEngine()


def _all_auto_engine():
    # type: () -> PermissionEngine
    return _AllAutoPermissionEngine()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_permission_presets.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/permission_presets.py tests/test_agent_permission_presets.py
git commit -m "Add permission presets mapping strategy settings to PermissionEngine"
git push
```

---

### Task 3: Add tool registration function

**Files:**
- Create: `qgitc/agent/tool_registration.py`
- Create: `tests/test_agent_tool_registration.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agent_tool_registration.py`:

```python
# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.tool_registration import register_builtin_tools
from qgitc.agent.tool_registry import ToolRegistry


class TestToolRegistration(unittest.TestCase):

    def test_register_builtin_tools(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)
        tools = registry.list_tools()
        self.assertGreater(len(tools), 0)

    def test_known_tools_registered(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)
        expected_names = [
            "git_status", "git_log", "git_diff", "git_diff_range",
            "git_diff_staged", "git_diff_unstaged",
            "git_show", "git_show_file", "git_show_index_file",
            "git_blame", "git_current_branch", "git_branch",
            "git_checkout", "git_cherry_pick", "git_commit", "git_add",
            "grep_search", "read_file", "read_external_file",
            "create_file", "apply_patch", "run_command",
        ]
        for name in expected_names:
            tool = registry.get(name)
            self.assertIsNotNone(tool, f"Tool '{name}' not registered")

    def test_schemas_generated(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)
        schemas = registry.get_tool_schemas()
        self.assertEqual(len(schemas), len(registry.list_tools()))
        for schema in schemas:
            self.assertIn("function", schema)
            self.assertIn("name", schema["function"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_tool_registration.py -v`
Expected: ImportError — `tool_registration` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `qgitc/agent/tool_registration.py`:

```python
# -*- coding: utf-8 -*-

from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.tools.apply_patch import ApplyPatchTool
from qgitc.agent.tools.create_file import CreateFileTool
from qgitc.agent.tools.git_add import GitAddTool
from qgitc.agent.tools.git_blame import GitBlameTool
from qgitc.agent.tools.git_branch import GitBranchTool
from qgitc.agent.tools.git_checkout import GitCheckoutTool
from qgitc.agent.tools.git_cherry_pick import GitCherryPickTool
from qgitc.agent.tools.git_commit import GitCommitTool
from qgitc.agent.tools.git_current_branch import GitCurrentBranchTool
from qgitc.agent.tools.git_diff import GitDiffTool
from qgitc.agent.tools.git_diff_range import GitDiffRangeTool
from qgitc.agent.tools.git_diff_staged import GitDiffStagedTool
from qgitc.agent.tools.git_diff_unstaged import GitDiffUnstagedTool
from qgitc.agent.tools.git_log import GitLogTool
from qgitc.agent.tools.git_show import GitShowTool
from qgitc.agent.tools.git_show_file import GitShowFileTool
from qgitc.agent.tools.git_show_index_file import GitShowIndexFileTool
from qgitc.agent.tools.git_status import GitStatusTool
from qgitc.agent.tools.grep_search import GrepSearchTool
from qgitc.agent.tools.read_external_file import ReadExternalFileTool
from qgitc.agent.tools.read_file import ReadFileTool
from qgitc.agent.tools.run_command import RunCommandTool


_BUILTIN_TOOLS = [
    GitStatusTool,
    GitLogTool,
    GitDiffTool,
    GitDiffRangeTool,
    GitDiffStagedTool,
    GitDiffUnstagedTool,
    GitShowTool,
    GitShowFileTool,
    GitShowIndexFileTool,
    GitBlameTool,
    GitCurrentBranchTool,
    GitBranchTool,
    GitCheckoutTool,
    GitCherryPickTool,
    GitCommitTool,
    GitAddTool,
    GrepSearchTool,
    ReadFileTool,
    ReadExternalFileTool,
    CreateFileTool,
    ApplyPatchTool,
    RunCommandTool,
]


def register_builtin_tools(registry):
    # type: (ToolRegistry) -> None
    """Register all built-in agent tools into the given registry."""
    for tool_cls in _BUILTIN_TOOLS:
        registry.register(tool_cls())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_tool_registration.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/tool_registration.py tests/test_agent_tool_registration.py
git commit -m "Add tool registration function for built-in agent tools"
git push
```

---

### Task 4: Add UI tool wrapper

**Files:**
- Create: `qgitc/agent/ui_tool.py`
- Create: `tests/test_agent_ui_tool.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agent_ui_tool.py`:

```python
# -*- coding: utf-8 -*-

import sys
import unittest
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QTimer

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
        self.assertFalse(tool.is_read_only())
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
        """Tool execution dispatches to main thread and returns result."""
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

        # Execute in a timer to simulate being called from background thread.
        # In real usage, AgentLoop calls this from its thread.
        # For testing, we run it directly since we can pump the event loop.
        result = [None]

        def run_tool():
            result[0] = tool.execute({"x": "1"}, _make_context())

        # Schedule execution and pump event loop
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_ui_tool.py -v`
Expected: ImportError — `ui_tool` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `qgitc/agent/ui_tool.py`:

```python
# -*- coding: utf-8 -*-

import logging
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import QMutex, QObject, QWaitCondition, Signal, Slot

from qgitc.agent.tool import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class UiToolDispatcher(QObject):
    """Lives on the main thread. Receives tool execution requests from
    background threads and dispatches them to a handler function."""

    _executeRequested = Signal(str, str, dict)  # request_id, tool_name, params

    def __init__(self, parent=None):
        # type: (Optional[QObject]) -> None
        super().__init__(parent)
        self._handler = None  # type: Optional[Callable]
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._results = {}  # type: Dict[str, Tuple[bool, str]]
        self._executeRequested.connect(self._onExecute)

    def set_handler(self, handler):
        # type: (Callable[[str, Dict[str, Any]], Tuple[bool, str]]) -> None
        """Set the handler called on the main thread.

        handler(tool_name, params) -> (ok, output)
        """
        self._handler = handler

    @Slot(str, str, dict)
    def _onExecute(self, request_id, tool_name, params):
        # type: (str, str, dict) -> None
        """Called on main thread via signal-slot connection."""
        ok, output = False, "No handler set"
        if self._handler is not None:
            try:
                ok, output = self._handler(tool_name, params)
            except Exception as e:
                logger.exception("UI tool handler error: %s", tool_name)
                ok, output = False, str(e)

        self._mutex.lock()
        self._results[request_id] = (ok, output)
        self._cond.wakeAll()
        self._mutex.unlock()

    def dispatch_and_wait(self, request_id, tool_name, params):
        # type: (str, str, dict) -> Tuple[bool, str]
        """Called from background thread. Dispatches to main thread and
        blocks until the result is available."""
        self._executeRequested.emit(request_id, tool_name, params)

        self._mutex.lock()
        while request_id not in self._results:
            self._cond.wait(self._mutex)
        result = self._results.pop(request_id)
        self._mutex.unlock()
        return result


class UiTool(Tool):
    """Wraps a context-provider UI tool for use in AgentLoop.

    Execution dispatches to the main thread via UiToolDispatcher.
    """

    def __init__(self, name, description, schema, dispatcher=None):
        # type: (str, str, Dict[str, Any], Optional[UiToolDispatcher]) -> None
        self.name = name
        self.description = description
        self._schema = schema
        self._dispatcher = dispatcher
        self._next_id = 0

    def set_dispatcher(self, dispatcher):
        # type: (UiToolDispatcher) -> None
        self._dispatcher = dispatcher

    def is_read_only(self):
        # type: () -> bool
        # UI tools are typically read-only (they affect UI state, not files).
        return True

    def execute(self, input_data, context):
        # type: (Dict[str, Any], ToolContext) -> ToolResult
        if self._dispatcher is None:
            return ToolResult(
                content="UI tool dispatcher not available",
                is_error=True,
            )
        self._next_id += 1
        request_id = "{}_{}".format(self.name, self._next_id)
        ok, output = self._dispatcher.dispatch_and_wait(
            request_id, self.name, input_data,
        )
        return ToolResult(content=output, is_error=not ok)

    def input_schema(self):
        # type: () -> Dict[str, Any]
        return self._schema
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_ui_tool.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/ui_tool.py tests/test_agent_ui_tool.py
git commit -m "Add UiTool wrapper for cross-thread UI tool execution"
git push
```

---

### Task 5: Add set_messages to AgentLoop and update exports

**Files:**
- Modify: `qgitc/agent/agent_loop.py`
- Modify: `qgitc/agent/__init__.py`

- [ ] **Step 1: Write failing test for set_messages**

Add to `tests/test_agent_loop.py`:

```python
class TestAgentLoopSetMessages(TestBase):

    def setUp(self):
        super().setUp()
        self.loop = _make_loop(SimpleProvider())

    def tearDown(self):
        self.loop.abort()
        self.loop.wait(3000)
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_set_messages(self):
        msgs = [
            UserMessage(content=[TextBlock(text="Hello")]),
            AssistantMessage(content=[TextBlock(text="Hi")]),
        ]
        self.loop.set_messages(msgs)
        result = self.loop.messages()
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], UserMessage)
        self.assertIsInstance(result[1], AssistantMessage)

    def test_set_messages_copies(self):
        msgs = [UserMessage(content=[TextBlock(text="Hello")])]
        self.loop.set_messages(msgs)
        msgs.append(UserMessage(content=[TextBlock(text="World")]))
        self.assertEqual(len(self.loop.messages()), 1)

    def test_set_system_prompt(self):
        self.loop.set_system_prompt("New prompt")
        self.assertEqual(self.loop._system_prompt, "New prompt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_loop.py::TestAgentLoopSetMessages -v`
Expected: AttributeError — `set_messages` doesn't exist yet.

- [ ] **Step 3: Add set_messages and set_system_prompt to AgentLoop**

In `qgitc/agent/agent_loop.py`, after the `messages()` method (around line 120), add:

```python
    def set_messages(self, messages):
        # type: (List[Message]) -> None
        """Replace conversation history (call before submit, not while running)."""
        self._messages = list(messages)

    def set_system_prompt(self, prompt):
        # type: (str) -> None
        """Update the system prompt."""
        self._system_prompt = prompt
```

- [ ] **Step 4: Update `qgitc/agent/__init__.py` to export new modules**

Add to the imports and `__all__` list:

```python
from qgitc.agent.message_convert import (
    history_dicts_to_messages,
    messages_to_history_dicts,
)
from qgitc.agent.permission_presets import create_permission_engine
from qgitc.agent.tool_registration import register_builtin_tools
from qgitc.agent.ui_tool import UiTool, UiToolDispatcher
```

Add to `__all__`:
```python
    "create_permission_engine",
    "history_dicts_to_messages",
    "messages_to_history_dicts",
    "register_builtin_tools",
    "UiTool",
    "UiToolDispatcher",
```

- [ ] **Step 5: Run all agent tests to verify nothing broke**

Run: `python -m pytest tests/test_agent_loop.py tests/test_agent_message_convert.py tests/test_agent_permission_presets.py tests/test_agent_ui_tool.py tests/test_agent_tool_registration.py -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add qgitc/agent/agent_loop.py qgitc/agent/__init__.py tests/test_agent_loop.py
git commit -m "Add set_messages/set_system_prompt to AgentLoop and update exports"
git push
```

---

## Phase 2: Widget Integration

### Task 6: Integrate AgentLoop into AiChatWidget

This is the core swap. Replace the old tool orchestration with AgentLoop.

**Files:**
- Modify: `qgitc/aichatwidget.py`
- Modify: `qgitc/aichatcontextprovider.py`
- Modify: `qgitc/mainwindowcontextprovider.py`
- Modify: `qgitc/commitcontextprovider.py`

- [ ] **Step 1: Update AiChatContextProvider to use new Tool type**

In `qgitc/aichatcontextprovider.py`, change the import and return type:

Replace:
```python
from qgitc.agenttools import AgentTool
```

With:
```python
from qgitc.agent.tool import Tool
```

Change `uiTools` return type from `List[AgentTool]` to `List[Tool]`.

- [ ] **Step 2: Convert MainWindowContextProvider UI tools**

In `qgitc/mainwindowcontextprovider.py`:

Replace imports:
```python
from qgitc.agenttools import AgentTool, ToolType, createToolFromModel
```
With:
```python
from qgitc.agent.ui_tool import UiTool
```

Replace `uiTools()` method body — instead of `createToolFromModel()`, create `UiTool` instances:

```python
def uiTools(self) -> List[Tool]:
    if self._uiToolsCache is None:
        self._uiToolsCache = [
            UiTool(
                name="ui_switch_to_commit",
                description="Jump (select and scroll) the log view to a given commit SHA1 visible in the current log list.",
                schema=UiSwitchToCommitParams.model_json_schema(),
            ),
            UiTool(
                name="ui_apply_log_filter",
                description="Apply git log filter options to the main window's log view. Use standard git log options like --since, --until, --author, --grep, -n, etc.",
                schema=UiApplyLogFilterParams.model_json_schema(),
            ),
        ]
    return self._uiToolsCache
```

Keep the Pydantic model classes and `executeUiTool()` unchanged — they're still used for validation.

- [ ] **Step 3: Convert CommitContextProvider UI tools**

In `qgitc/commitcontextprovider.py`:

Same pattern — replace `createToolFromModel` usage with `UiTool`:

Replace imports:
```python
from qgitc.agenttools import AgentTool, ToolType, createToolFromModel
```
With:
```python
from qgitc.agent.ui_tool import UiTool
```

Replace `uiTools()`:
```python
def uiTools(self) -> List[Tool]:
    if self._uiToolsCache is None:
        self._uiToolsCache = [
            UiTool(
                name="ui_reload_status",
                description="Reload the CommitWindow staged/unstaged status lists from Git.",
                schema=UiReloadStatusParams.model_json_schema(),
            ),
            UiTool(
                name="ui_set_commit_message",
                description="Replace the commit message text in the CommitWindow editor.",
                schema=UiSetCommitMessageParams.model_json_schema(),
            ),
        ]
    return self._uiToolsCache
```

- [ ] **Step 4: Rewrite AiChatWidget to use AgentLoop**

In `qgitc/aichatwidget.py`:

**Replace old imports:**
```python
from qgitc.agentmachine import (
    AgentToolMachine,
    AggressiveStrategy,
    AllAutoStrategy,
    DefaultStrategy,
    SafeStrategy,
)
from qgitc.agenttoolexecutor import AgentToolExecutor
from qgitc.agenttools import (
    AgentTool,
    AgentToolRegistry,
    AgentToolResult,
    ToolType,
    parseToolArguments,
)
from qgitc.uitoolexecutor import UiToolExecutor
```

With:
```python
from qgitc.agent import (
    AgentLoop,
    AiModelBaseAdapter,
    ConversationCompactor,
    PermissionEngine,
    ToolRegistry,
    Tool,
    UiTool,
    UiToolDispatcher,
    create_permission_engine,
    history_dicts_to_messages,
    messages_to_history_dicts,
    register_builtin_tools,
)
from qgitc.agent.types import TextBlock
from qgitc.agenttools import ToolType, parseToolArguments
```

Note: We keep importing `ToolType` and `parseToolArguments` from `agenttools` for now — the confirmation UI still needs them. They'll be moved in the cleanup phase.

**Replace __init__ tool setup (lines ~338-356):**

Remove:
```python
self._agentExecutor = AgentToolExecutor(self)
self._agentExecutor.toolFinished.connect(self._onAgentToolFinished)
self._uiToolExecutor = UiToolExecutor(self)
self._uiToolExecutor.toolFinished.connect(self._onAgentToolFinished)

settings = ApplicationBase.instance().settings()
strategy = self._createStrategy(settings.toolExecutionStrategy())
self._toolMachine = AgentToolMachine(
    strategy=strategy,
    toolLookupFn=self._toolByName,
    maxConcurrent=4,
    parent=self)
self._toolMachine.toolExecutionRequested.connect(self._onExecuteTool)
self._toolMachine.userConfirmationNeeded.connect(
    self._onToolConfirmationNeeded)
self._toolMachine.toolExecutionCancelled.connect(
    self._onToolExecutionCancelled)
self._toolMachine.agentContinuationReady.connect(self._onContinueAgent)

settings.toolExecutionStrategyChanged.connect(
    self._onToolExecutionStrategyChanged)
```

Replace with:
```python
self._uiToolDispatcher = UiToolDispatcher(self)
self._uiToolDispatcher.set_handler(self._executeUiToolHandler)

settings = ApplicationBase.instance().settings()
self._permissionEngine = create_permission_engine(
    settings.toolExecutionStrategy())
settings.toolExecutionStrategyChanged.connect(
    self._onToolExecutionStrategyChanged)

self._agentLoop = None  # type: Optional[AgentLoop]
self._toolRegistry = None  # type: Optional[ToolRegistry]
```

**Add helper methods:**

```python
def _buildToolRegistry(self):
    # type: () -> ToolRegistry
    """Build a ToolRegistry with built-in tools + UI tools."""
    registry = ToolRegistry()
    register_builtin_tools(registry)
    # Register UI tools from context provider
    for tool in self._providerUiTools():
        if isinstance(tool, UiTool):
            tool.set_dispatcher(self._uiToolDispatcher)
        registry.register(tool)
    return registry

def _executeUiToolHandler(self, toolName, params):
    # type: (str, dict) -> tuple
    """Handler called on main thread by UiToolDispatcher."""
    provider = self.contextProvider()
    if provider is None:
        return False, "No context provider"
    return provider.executeUiTool(toolName, params)

def _ensureAgentLoop(self):
    # type: () -> AgentLoop
    """Create or return the current AgentLoop."""
    if self._agentLoop is not None:
        return self._agentLoop
    self._toolRegistry = self._buildToolRegistry()
    model = self.currentChatModel()
    adapter = AiModelBaseAdapter(model)
    compactor = ConversationCompactor(
        adapter, context_window=100000, max_output_tokens=4096)
    loop = AgentLoop(
        provider=adapter,
        tool_registry=self._toolRegistry,
        permission_engine=self._permissionEngine,
        compactor=compactor,
        parent=self,
    )
    self._connectAgentLoop(loop)
    self._agentLoop = loop
    return loop

def _connectAgentLoop(self, loop):
    # type: (AgentLoop) -> None
    loop.textDelta.connect(self._onAgentTextDelta)
    loop.reasoningDelta.connect(self._onAgentReasoningDelta)
    loop.toolCallStart.connect(self._onAgentToolCallStart)
    loop.toolCallResult.connect(self._onAgentToolCallResult)
    loop.turnComplete.connect(self._onAgentTurnComplete)
    loop.agentFinished.connect(self._onAgentFinished)
    loop.permissionRequired.connect(self._onAgentPermissionRequired)
    loop.errorOccurred.connect(self._onAgentError)

def _disconnectAgentLoop(self):
    # type: () -> None
    if self._agentLoop is None:
        return
    loop = self._agentLoop
    loop.textDelta.disconnect(self._onAgentTextDelta)
    loop.reasoningDelta.disconnect(self._onAgentReasoningDelta)
    loop.toolCallStart.disconnect(self._onAgentToolCallStart)
    loop.toolCallResult.disconnect(self._onAgentToolCallResult)
    loop.turnComplete.disconnect(self._onAgentTurnComplete)
    loop.agentFinished.disconnect(self._onAgentFinished)
    loop.permissionRequired.disconnect(self._onAgentPermissionRequired)
    loop.errorOccurred.disconnect(self._onAgentError)

def _resetAgentLoop(self):
    # type: () -> None
    """Stop and discard the current agent loop."""
    if self._agentLoop is not None:
        self._agentLoop.abort()
        self._agentLoop.wait(3000)
        self._disconnectAgentLoop()
        self._agentLoop = None
        self._toolRegistry = None
```

**Add AgentLoop signal handlers:**

```python
def _onAgentTextDelta(self, text):
    # type: (str) -> None
    response = AiResponse(AiRole.Assistant, text, is_delta=True)
    self._chatBot.appendResponse(response)
    if not self._disableAutoScroll:
        sb = self._chatBot.verticalScrollBar()
        self._adjustingSccrollbar = True
        sb.setValue(sb.maximum())
        self._adjustingSccrollbar = False

def _onAgentReasoningDelta(self, text):
    # type: (str) -> None
    response = AiResponse(
        AiRole.Assistant, text,
        description=self.tr("🧠 Reasoning"),
        is_delta=True,
    )
    self._chatBot.appendResponse(response)

def _onAgentToolCallStart(self, toolCallId, toolName, params):
    # type: (str, str, dict) -> None
    uiResponse = self._makeUiToolCallResponse(toolName, params)
    self._chatBot.appendResponse(uiResponse, collapsed=True)
    if not self._disableAutoScroll:
        sb = self._chatBot.verticalScrollBar()
        self._adjustingSccrollbar = True
        sb.setValue(sb.maximum())
        self._adjustingSccrollbar = False

def _onAgentToolCallResult(self, toolCallId, content, isError):
    # type: (str, str, bool) -> None
    prefix = "✓" if not isError else "✗"
    desc = self.tr("{} tool output").format(prefix)
    response = AiResponse(AiRole.Tool, content, description=desc)
    self._chatBot.appendResponse(response, collapsed=True)

def _onAgentTurnComplete(self, assistantMsg):
    # type: (object) -> None
    self._saveChatHistoryFromLoop()

def _onAgentFinished(self):
    # type: () -> None
    self._saveChatHistoryFromLoop()
    self._updateStatus()
    self._chatBot.collapseLatestReasoningBlock()

def _onAgentPermissionRequired(self, toolCallId, tool, inputData):
    # type: (str, object, dict) -> None
    toolName = tool.name if hasattr(tool, 'name') else str(tool)
    if tool.is_destructive():
        toolType = ToolType.DANGEROUS
    elif tool.is_read_only():
        toolType = ToolType.READ_ONLY
    else:
        toolType = ToolType.WRITE

    uiResponse = self._makeUiToolCallResponse(toolName, inputData)
    self._chatBot.appendResponse(uiResponse)

    expl = inputData.get("explanation", "").strip() if isinstance(inputData, dict) else ""
    desc = expl if expl else (tool.description if hasattr(tool, 'description') else "")
    self._chatBot.insertToolConfirmation(
        toolName=toolName,
        params=inputData,
        toolDesc=desc,
        toolType=toolType,
        toolCallId=toolCallId,
    )

def _onAgentError(self, errorMsg):
    # type: (str) -> None
    self._chatBot.appendServiceUnavailable(errorMsg)

def _saveChatHistoryFromLoop(self):
    # type: () -> None
    """Save current AgentLoop messages to the history store."""
    if self._agentLoop is None:
        return
    chatHistory = self._historyPanel.currentHistory()
    if not chatHistory:
        return
    messages = self._agentLoop.messages()
    dicts = messages_to_history_dicts(messages)
    chatHistory.messages = dicts
    model = self.currentChatModel()
    if model:
        chatHistory.modelKey = AiModelFactory.modelKey(model)
        chatHistory.modelId = model.modelId or model.name
    settings = ApplicationBase.instance().settings()
    settings.saveChatHistory(chatHistory.historyId, chatHistory.toDict())
```

**Replace `_doRequest`:**

```python
def _doRequest(self, prompt, chatMode, sysPrompt=None, collapsed=False):
    # type: (str, AiChatMode, Optional[str], bool) -> None
    settings = ApplicationBase.instance().settings()
    self._disableAutoScroll = False

    model = self.currentChatModel()
    isNewConversation = self._agentLoop is None or not self._agentLoop.messages()

    # Determine system prompt
    if not sysPrompt:
        if chatMode == AiChatMode.Agent:
            provider = self.contextProvider()
            overridePrompt = provider.agentSystemPrompt() if provider else None
            sysPrompt = overridePrompt or AGENT_SYS_PROMPT
        elif chatMode == AiChatMode.CodeReview:
            sysPrompt = CODE_REVIEW_SYS_PROMPT

    # Build full prompt with context
    injectedContext = self._injectedContext
    fullPrompt = prompt

    if chatMode == AiChatMode.CodeReview:
        fullPrompt = CODE_REVIEW_PROMPT.format(diff=prompt)

    if not collapsed:
        provider = self.contextProvider()
        selectedIds = self._contextPanel.selectedContextIds() if provider else []
        contextText = provider.buildContextText(selectedIds) if provider else ""

        if injectedContext:
            merged = (contextText or "").strip()
            if merged:
                merged += "\n\n" + injectedContext
            else:
                merged = injectedContext
            contextText = merged

        if contextText:
            fullPrompt = f"<context>\n{contextText.rstrip()}\n</context>\n\n" + fullPrompt

    # Display user message in chatbot
    self._chatBot.appendResponse(AiResponse(AiRole.User, fullPrompt), collapsed)

    # Display system prompt if new
    loop = self._ensureAgentLoop()
    if sysPrompt:
        existingMsgs = loop.messages()
        if not self._historyHasSameSystemPromptInMessages(existingMsgs, sysPrompt):
            self._chatBot.appendResponse(
                AiResponse(AiRole.System, sysPrompt), True)

    loop.set_system_prompt(sysPrompt or "")

    # UI state
    self._contextPanel.btnSend.setVisible(False)
    self._contextPanel.btnStop.setVisible(True)
    self._historyPanel.setEnabled(False)
    self._contextPanel.cbBots.setEnabled(False)
    self._contextPanel.setFocus()
    self._setGenerating(True)

    # Submit to agent loop
    loop.submit(fullPrompt)

    # Clear tool restrictions and injected context
    self._restrictedToolNames = None

    titleSeed = (sysPrompt + "\n" + prompt) if sysPrompt else prompt
    if isNewConversation and not ApplicationBase.instance().testing and titleSeed:
        self._generateChatTitle(
            self._historyPanel.currentHistory().historyId, titleSeed)

    self._updateChatHistoryModel(model)
    self._setEmbeddedRecentListVisible(False)
```

**Replace `_onToolApproved` and `_onToolRejected`:**

```python
def _onToolApproved(self, toolName, params, toolCallId):
    # type: (str, dict, str) -> None
    if self._agentLoop:
        self._agentLoop.approve_tool(toolCallId)

def _onToolRejected(self, toolName, toolCallId):
    # type: (str, str) -> None
    if self._agentLoop:
        self._agentLoop.deny_tool(toolCallId)
    self._chatBot.setToolConfirmationStatus(
        toolCallId, ConfirmationStatus.REJECTED)
```

**Replace `_onButtonStop`:**

```python
def _onButtonStop(self):
    if self._agentLoop and self._agentLoop.isRunning():
        self._agentLoop.abort()
        self._agentLoop.wait(3000)
    self._saveChatHistoryFromLoop()
    self._updateStatus()
```

**Replace `_clearCurrentChat`:**

```python
def _clearCurrentChat(self):
    self._resetAgentLoop()
    self._codeReviewDiffs.clear()
    self._injectedContext = None
    self.messages.clear()
```

**Replace `_loadMessagesFromHistory`:**

```python
def _loadMessagesFromHistory(self, messages, addToChatBot=True):
    # type: (list, bool) -> None
    if not messages:
        return

    agentMsgs = history_dicts_to_messages(messages)
    loop = self._ensureAgentLoop()
    loop.set_messages(agentMsgs)

    if addToChatBot:
        chatbot = self._chatBot
        chatbot.setHighlighterEnabled(False)

        for msg_dict in messages:
            role_str = msg_dict.get("role", "user")
            role = AiRole.fromString(role_str)
            content = msg_dict.get("content", "")
            reasoning = msg_dict.get("reasoning")
            description = msg_dict.get("description")
            tool_calls = msg_dict.get("tool_calls")

            if role == AiRole.Tool and isinstance(tool_calls, dict):
                # Tool result
                response = AiResponse(role, content, description=description)
                chatbot.appendResponse(response, collapsed=True)
            elif role == AiRole.Assistant and isinstance(tool_calls, list):
                # Assistant with tool calls
                if reasoning:
                    reasoningResponse = AiResponse(
                        AiRole.Assistant, reasoning,
                        description=self.tr("🧠 Reasoning"))
                    chatbot.appendResponse(reasoningResponse, collapsed=True)
                if content:
                    chatbot.appendResponse(AiResponse(role, content))
                for tc in tool_calls:
                    func = (tc.get("function") or {})
                    toolName = func.get("name", "")
                    uiResponse = self._makeUiToolCallResponse(
                        toolName, func.get("arguments", "{}"))
                    chatbot.appendResponse(uiResponse, collapsed=True)
            else:
                if reasoning:
                    reasoningResponse = AiResponse(
                        AiRole.Assistant, reasoning,
                        description=self.tr("🧠 Reasoning"))
                    chatbot.appendResponse(reasoningResponse, collapsed=True)
                response = AiResponse(role, content)
                collapsed = (role == AiRole.Tool) or (role == AiRole.System)
                chatbot.appendResponse(response, collapsed=collapsed)

        chatbot.setHighlighterEnabled(True)
```

**Replace `_onToolExecutionStrategyChanged`:**

```python
def _onToolExecutionStrategyChanged(self, strategyValue):
    # type: (int) -> None
    self._permissionEngine = create_permission_engine(strategyValue)
    if self._agentLoop:
        self._agentLoop._permission_engine = self._permissionEngine
```

**Replace `queryClose`:**

```python
def queryClose(self):
    if self._titleGenerator:
        self._titleGenerator.cancel()

    self._resetAgentLoop()

    for i in range(self._contextPanel.cbBots.count()):
        model = self._contextPanel.cbBots.itemData(i)
        if not isinstance(model, AiModelBase):
            continue
        if model.isRunning():
            model.requestInterruption()
        model.cleanup()

    if self._codeReviewExecutor:
        self._codeReviewExecutor.cancel()
        self._codeReviewExecutor = None
        self._codeReviewDiffs.clear()
    self._injectedContext = None
```

**Add helper for system prompt check:**

```python
@staticmethod
def _historyHasSameSystemPromptInMessages(messages, sp):
    # type: (list, str) -> bool
    if not sp:
        return False
    from qgitc.agent.types import SystemMessage as SysMsg
    for msg in messages:
        if isinstance(msg, SysMsg) and msg.content == sp:
            return True
    return False
```

**Remove these methods** (no longer needed):
- `_continueAgentConversation`
- `_onExecuteTool`
- `_onToolConfirmationNeeded`
- `_onToolExecutionCancelled`
- `_onContinueAgent`
- `_onAgentToolFinished`
- `_executeToolAsync`
- `_toolByName`
- `_availableOpenAiTools`
- `_createStrategy`
- `_onMessageReady`
- `_onReasoningFinished`
- `_onResponseFinish`
- `_saveChatHistory` (replaced by `_saveChatHistoryFromLoop`)
- `_collectToolCallResult`

**Remove old instance variables:**
- `self._agentExecutor`
- `self._uiToolExecutor`
- `self._toolMachine`

**Keep `_providerUiTools`** — still needed by `_buildToolRegistry`.

**Keep `_makeUiToolCallResponse`** — still used for displaying tool calls. Update its `_toolByName` lookup:

```python
def _makeUiToolCallResponse(self, toolName, args):
    # type: (str, Any) -> AiResponse
    tool = self._toolRegistry.get(toolName) if self._toolRegistry else None
    if tool:
        if tool.is_destructive():
            toolType = ToolType.DANGEROUS
        elif tool.is_read_only():
            toolType = ToolType.READ_ONLY
        else:
            toolType = ToolType.WRITE
    else:
        toolType = ToolType.DANGEROUS

    icon = self._getToolIcon(toolType)
    title = self.tr("{} run `{}`").format(icon, toolName or "unknown")

    if isinstance(args, str):
        body = args
    else:
        body = json.dumps(args, ensure_ascii=False)
    return AiResponse(AiRole.Tool, body, title)
```

- [ ] **Step 5: Update `isBusyForCodeReview`**

Replace:
```python
def isBusyForCodeReview(self):
    if self.isGenerating():
        return True
    return self._toolMachine.taskInProgress()
```

With:
```python
def isBusyForCodeReview(self):
    if self.isGenerating():
        return True
    return self._agentLoop is not None and self._agentLoop.isRunning()
```

- [ ] **Step 6: Update `isGenerating`**

Replace:
```python
def isGenerating(self):
    model = self.currentChatModel()
    return model is not None and model.isRunning()
```

With:
```python
def isGenerating(self):
    return self._agentLoop is not None and self._agentLoop.isRunning()
```

- [ ] **Step 7: Update `_onButtonSend` to remove old toolMachine references**

Replace:
```python
def _onButtonSend(self, clicked):
    prompt = self._contextPanel.userPrompt().strip()
    if not prompt:
        return
    if self._toolMachine.hasPendingResults():
        self._toolMachine.rejectPendingResults()
    ...
```

With:
```python
def _onButtonSend(self, clicked):
    prompt = self._contextPanel.userPrompt().strip()
    if not prompt:
        return
    ...
```

(Remove the `hasPendingResults` / `rejectPendingResults` calls — AgentLoop handles this internally.)

- [ ] **Step 8: Run the application to verify it starts and basic chat works**

Run: `python -m qgitc`
Test: Open AI chat, send a message, verify response appears.

- [ ] **Step 9: Commit**

```bash
git add qgitc/aichatwidget.py qgitc/aichatcontextprovider.py qgitc/mainwindowcontextprovider.py qgitc/commitcontextprovider.py
git commit -m "Integrate AgentLoop into AiChatWidget replacing old tool orchestration"
git push
```

---

### Task 7: Update AiChatHistoryStore for AgentLoop messages

**Files:**
- Modify: `qgitc/aichathistorystore.py`

- [ ] **Step 1: Add `updateFromMessages` method**

In `qgitc/aichathistorystore.py`, add after `updateFromModel`:

```python
def updateFromMessages(self, historyId, messages, modelKey=None, modelId=None):
    # type: (str, list, Optional[str], Optional[str]) -> Optional[AiChatHistory]
    """Update a history item from agent Message list and persist."""
    from qgitc.agent.message_convert import messages_to_history_dicts

    self.ensureLoaded()
    row = self._model.findHistoryRow(historyId)
    if row < 0:
        return None

    idx = self._model.index(row, 0)
    history = self._model.data(idx, Qt.UserRole)
    if not history:
        return None

    history.messages = messages_to_history_dicts(messages)
    if modelKey is not None:
        history.modelKey = modelKey
    if modelId is not None:
        history.modelId = modelId

    # Move to top if not already there.
    if row > 0:
        self._model.moveToTop(row)
    self._scheduleSave()
    self.historyUpdated.emit(history)
    return history
```

- [ ] **Step 2: Update `_saveChatHistoryFromLoop` in AiChatWidget to use the new method**

In `qgitc/aichatwidget.py`, update `_saveChatHistoryFromLoop`:

```python
def _saveChatHistoryFromLoop(self):
    if self._agentLoop is None:
        return
    chatHistory = self._historyPanel.currentHistory()
    if not chatHistory:
        return
    store = ApplicationBase.instance().aiChatHistoryStore()
    model = self.currentChatModel()
    modelKey = AiModelFactory.modelKey(model) if model else None
    modelId = (model.modelId or model.name) if model else None
    updated = store.updateFromMessages(
        chatHistory.historyId,
        self._agentLoop.messages(),
        modelKey=modelKey,
        modelId=modelId,
    )
    if updated:
        self._historyPanel.setCurrentHistory(updated.historyId)
```

- [ ] **Step 3: Verify chat history saves and loads correctly**

Run: `python -m qgitc`
Test: Send a message, switch to another conversation, switch back — messages should persist.

- [ ] **Step 4: Commit**

```bash
git add qgitc/aichathistorystore.py qgitc/aichatwidget.py
git commit -m "Add updateFromMessages to history store for AgentLoop integration"
git push
```

---

## Phase 3: ResolveConflictJob Refactor

### Task 8: Refactor ResolveConflictJob

**Files:**
- Modify: `qgitc/aichatwidget.py` (the `ResolveConflictJob` class)

- [ ] **Step 1: Rewrite ResolveConflictJob**

Replace the entire `ResolveConflictJob` class in `qgitc/aichatwidget.py`:

```python
class ResolveConflictJob(QObject):
    finished = Signal(bool, object)  # ok, reason

    def __init__(
        self,
        widget,          # type: AiChatWidget
        repoDir,         # type: str
        sha1,            # type: str
        path,            # type: str
        conflictText,    # type: str
        context=None,    # type: Optional[str]
        reportFile=None, # type: Optional[str]
        parent=None,     # type: Optional[QObject]
    ):
        super().__init__(parent or widget)
        self._widget = widget
        self._repoDir = repoDir
        self._sha1 = sha1
        self._path = path
        self._conflictText = conflictText
        self._context = context
        self._reportFile = reportFile

        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._agentLoop = None  # type: Optional[AgentLoop]

    def start(self):
        w = self._widget
        w._waitForInitialization()

        model = w.currentChatModel()
        if not model:
            self._finish(False, "no_model")
            return

        # Always start a new conversation for conflict resolution.
        w._createNewConversation()

        # Set context
        contextText = (self._context or "").strip() or None
        w._injectedContext = contextText

        prompt = RESOLVE_PROMPT.format(
            operation="cherry-pick" if self._sha1 else "merge",
            conflict=self._conflictText,
        )

        # Build the full prompt with context
        fullPrompt = prompt
        if contextText:
            fullPrompt = f"<context>\n{contextText.rstrip()}\n</context>\n\n" + prompt

        # Create own AgentLoop with all-auto permissions
        adapter = AiModelBaseAdapter(model)
        toolRegistry = ToolRegistry()
        register_builtin_tools(toolRegistry)
        allAutoEngine = create_permission_engine(3)  # AllAuto
        compactor = ConversationCompactor(
            adapter, context_window=100000, max_output_tokens=4096)
        self._agentLoop = AgentLoop(
            provider=adapter,
            tool_registry=toolRegistry,
            permission_engine=allAutoEngine,
            compactor=compactor,
            system_prompt=RESOLVE_SYS_PROMPT,
            parent=self,
        )

        # Connect signals for rendering in the widget
        self._agentLoop.textDelta.connect(w._onAgentTextDelta)
        self._agentLoop.reasoningDelta.connect(w._onAgentReasoningDelta)
        self._agentLoop.toolCallStart.connect(w._onAgentToolCallStart)
        self._agentLoop.toolCallResult.connect(w._onAgentToolCallResult)
        self._agentLoop.agentFinished.connect(self._onAgentFinished)
        self._agentLoop.errorOccurred.connect(self._onError)

        self._timer.timeout.connect(self._onTimeout)
        self._timer.start(5 * 60 * 1000)

        # Display user message
        w._chatBot.appendResponse(AiResponse(AiRole.User, fullPrompt))
        w._chatBot.appendResponse(
            AiResponse(AiRole.System, RESOLVE_SYS_PROMPT), True)

        # UI state
        w._contextPanel.btnSend.setVisible(False)
        w._contextPanel.btnStop.setVisible(True)
        w._setGenerating(True)

        self._agentLoop.submit(fullPrompt)

    def abort(self):
        if self._agentLoop:
            self._agentLoop.abort()

    def _onAgentFinished(self):
        if self._done:
            return
        self._checkDone()

    def _onError(self, errorMsg):
        self._finish(False, errorMsg)

    def _onTimeout(self):
        if self._agentLoop:
            self._agentLoop.abort()
        self._finish(False, "Assistant response timed out")

    def _checkDone(self):
        if self._done:
            return
        if self._agentLoop is None:
            return

        response = self._lastAssistantText()
        status, detail = self._parseFinalResolveMessage(response)

        if status == "failed":
            self._finish(False, detail or "Assistant reported failure")
            return

        if status != "ok":
            self._finish(False, "No resolve status marker found")
            return

        # Verify the file is conflict-marker-free
        try:
            absPath = os.path.join(self._repoDir, self._path)
            with open(absPath, "rb") as f:
                merged = f.read()
        except Exception as e:
            self._finish(False, f"read_back_failed: {e}")
            return

        if b"<<<<<<<" in merged or b"=======" in merged or b">>>>>>>" in merged:
            self._finish(False, "conflict_markers_remain")
            return

        self._finish(True, detail or "Assistant reported success")

    def _lastAssistantText(self):
        # type: () -> str
        if self._agentLoop is None:
            return ""
        from qgitc.agent.types import AssistantMessage as AMsg, TextBlock as TBlk
        for msg in reversed(self._agentLoop.messages()):
            if isinstance(msg, AMsg):
                parts = [b.text for b in msg.content if isinstance(b, TBlk)]
                if parts:
                    return "".join(parts)
        return ""

    @staticmethod
    def _parseFinalResolveMessage(text):
        # type: (str) -> tuple
        if not text:
            return None, ""
        pos = text.find("QGITC_RESOLVE_OK")
        if pos != -1:
            detail = text[pos + len("QGITC_RESOLVE_OK"):].lstrip('\n')
            return "ok", detail
        pos = text.find("QGITC_RESOLVE_FAILED")
        if pos != -1:
            detail = text[pos + len("QGITC_RESOLVE_FAILED"):].lstrip('\n')
            return "failed", detail
        return None, ""

    def _finish(self, ok, reason):
        # type: (bool, object) -> None
        if self._done:
            return
        self._done = True

        if self._reportFile:
            try:
                entry = buildResolutionReportEntry(
                    repoDir=self._repoDir,
                    path=self._path,
                    sha1=self._sha1,
                    operation="cherry-pick" if self._sha1 else "merge",
                    ok=ok,
                    reason=reason,
                )
                appendResolutionReportEntry(self._reportFile, entry)
            except Exception:
                pass

        self._timer.stop()
        if self._agentLoop:
            self._agentLoop.abort()
            self._agentLoop.wait(3000)

        self._widget._updateStatus()
        self.finished.emit(ok, reason)
```

- [ ] **Step 2: Verify resolve functionality still works**

This requires a merge conflict scenario. Manual test:
1. Create a branch with conflicting changes
2. Attempt merge/cherry-pick
3. Use AI resolve feature
4. Verify it completes or reports failure

- [ ] **Step 3: Commit**

```bash
git add qgitc/aichatwidget.py
git commit -m "Refactor ResolveConflictJob to use its own AgentLoop"
git push
```

---

## Phase 4: Cleanup

### Task 9: Move ToolType to agent module and update UI imports

**Files:**
- Modify: `qgitc/aitoolconfirmation.py`
- Modify: `qgitc/aichatbot.py`
- Modify: `qgitc/aichatwidget.py`

- [ ] **Step 1: Add tool_type_from_tool helper and ToolType to agent module**

Add to `qgitc/agent/tool.py`:

```python
class ToolType:
    """Tool type constants for UI rendering."""
    READ_ONLY = 0
    WRITE = 1
    DANGEROUS = 2
```

Add a helper function:
```python
def tool_type_from_tool(tool):
    # type: (Tool) -> int
    """Convert Tool boolean flags to ToolType constant for UI."""
    if tool.is_destructive():
        return ToolType.DANGEROUS
    if tool.is_read_only():
        return ToolType.READ_ONLY
    return ToolType.WRITE
```

Update `qgitc/agent/__init__.py` to export `ToolType` and `tool_type_from_tool`.

- [ ] **Step 2: Update aitoolconfirmation.py imports**

Replace:
```python
from qgitc.agenttools import ToolType
```
With:
```python
from qgitc.agent.tool import ToolType
```

- [ ] **Step 3: Update aichatbot.py imports**

Replace:
```python
from qgitc.agenttools import ToolType
```
With:
```python
from qgitc.agent.tool import ToolType
```

- [ ] **Step 4: Update aichatwidget.py imports**

Remove the remaining `agenttools` import:
```python
from qgitc.agenttools import ToolType, parseToolArguments
```

Replace with:
```python
from qgitc.agent.tool import ToolType, tool_type_from_tool
```

Replace any remaining `parseToolArguments` usage with `json.loads` or dict handling.

- [ ] **Step 5: Run the application and verify tool confirmation UI still renders correctly**

Run: `python -m qgitc`
Test: In Agent mode, trigger a tool that requires confirmation. Verify the card renders with correct styling.

- [ ] **Step 6: Commit**

```bash
git add qgitc/agent/tool.py qgitc/agent/__init__.py qgitc/aitoolconfirmation.py qgitc/aichatbot.py qgitc/aichatwidget.py
git commit -m "Move ToolType to agent module and update all imports"
git push
```

---

### Task 10: Remove old modules

**Files:**
- Delete: `qgitc/agenttools.py`
- Delete: `qgitc/agenttoolexecutor.py`
- Delete: `qgitc/agentmachine.py`
- Delete: `qgitc/uitoolexecutor.py`

- [ ] **Step 1: Verify no remaining imports of old modules**

Run:
```bash
grep -rn "from qgitc.agenttools\|from qgitc.agenttoolexecutor\|from qgitc.agentmachine\|from qgitc.uitoolexecutor\|import agenttools\|import agenttoolexecutor\|import agentmachine\|import uitoolexecutor" qgitc/ tests/
```

Fix any remaining imports found.

- [ ] **Step 2: Delete old modules**

```bash
git rm qgitc/agenttools.py qgitc/agenttoolexecutor.py qgitc/agentmachine.py qgitc/uitoolexecutor.py
```

- [ ] **Step 3: Update or remove tests that reference old modules**

Check each test file:
- `tests/test_agentmachine.py` — Delete (replaced by permission preset and agent loop tests)
- `tests/test_agent_mode.py` — Update imports to use new module
- `tests/test_agent_read_external_file.py` — Update to use new tool directly
- `tests/test_agent_read_file.py` — Update to use new tool directly
- `tests/test_agent_repo_dir.py` — Update to use new tool directly
- `tests/test_aichat_tool_confirmation_session.py` — Update imports
- `tests/test_aichat_tool_explanation_preference.py` — Update imports
- `tests/test_aichatbot.py` — Update imports
- `tests/test_apply_patch_tool.py` — Update to use new tool directly

For each test file, replace imports like:
```python
from qgitc.agenttools import ToolType
```
With:
```python
from qgitc.agent.tool import ToolType
```

And replace:
```python
from qgitc.agenttoolexecutor import AgentToolExecutor
```
With the appropriate new module import (or rewrite the test to use the new Tool class directly).

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass with no import errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Remove old agent tool modules: agenttools, agenttoolexecutor, agentmachine, uitoolexecutor"
git push
```

---

## Phase 5: AiModelBase Simplification (Optional / Future)

### Task 11: Simplify AiModelBase to use new message types

This task is large and affects all model providers. It can be done as a follow-up.

**Files:**
- Modify: `qgitc/llm.py`
- Modify: All model provider files that reference `AiChatMessage`

- [ ] **Step 1: Replace AiChatMessage with agent Message types**

In `qgitc/llm.py`:
- Change `self._history: List[AiChatMessage]` to `self._history: List[Message]`
- Update `addHistory()` to create `UserMessage`/`AssistantMessage`/`SystemMessage` with `ContentBlock`s
- Update `toOpenAiMessages()` to convert from new types (similar logic to `AiModelBaseAdapter._build_history()`)
- Keep `AiChatMessage` as a deprecated alias or remove it

- [ ] **Step 2: Update AiModelBaseAdapter to use model's history directly**

Since the model now stores the same types, the adapter can reference `model.history` directly instead of rebuilding.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add qgitc/llm.py qgitc/agent/aimodel_adapter.py
git commit -m "Simplify AiModelBase to use agent message types"
git push
```
