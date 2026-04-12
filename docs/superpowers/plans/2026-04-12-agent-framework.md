# Agent Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, pluggable agent framework for qgitc with a QThread-based agent loop, Tool ABC, ModelProvider protocol, permission engine, and conversation compaction.

**Architecture:** The agent package (`qgitc/agent/`) is fully independent of UI code. An `AgentLoop` QThread orchestrates: prompt → LLM streaming → tool execution → permission checks → compaction → loop. Communication with consumers is via Qt signals.

**Tech Stack:** Python 3.7+, PySide6 (QThread, Signal, QMutex, QWaitCondition), unittest, dataclasses

**Commit rules:** Never add Co-Authored-By footer. Never push automatically.

---

### Task 1: Agent types — message types, content blocks, usage

**Files:**
- Create: `qgitc/agent/__init__.py`
- Create: `qgitc/agent/types.py`
- Create: `tests/test_agent_types.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_types.py`:

```python
# -*- coding: utf-8 -*-
import unittest

from qgitc.agent.types import (
    AssistantMessage,
    ContentBlock,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UserMessage,
)


class TestContentBlocks(unittest.TestCase):

    def test_text_block(self):
        block = TextBlock(text="hello")
        self.assertEqual(block.text, "hello")

    def test_tool_use_block(self):
        block = ToolUseBlock(id="call_1", name="git_status", input={"path": "."})
        self.assertEqual(block.id, "call_1")
        self.assertEqual(block.name, "git_status")
        self.assertEqual(block.input, {"path": "."})

    def test_tool_result_block(self):
        block = ToolResultBlock(tool_use_id="call_1", content="ok")
        self.assertFalse(block.is_error)
        block_err = ToolResultBlock(tool_use_id="call_1", content="fail", is_error=True)
        self.assertTrue(block_err.is_error)

    def test_thinking_block(self):
        block = ThinkingBlock(thinking="let me think")
        self.assertEqual(block.thinking, "let me think")


class TestMessages(unittest.TestCase):

    def test_user_message_defaults(self):
        msg = UserMessage(content=[TextBlock(text="hi")])
        self.assertIsNotNone(msg.uuid)
        self.assertIsNotNone(msg.timestamp)
        self.assertEqual(len(msg.content), 1)

    def test_assistant_message_defaults(self):
        msg = AssistantMessage(content=[TextBlock(text="hello")])
        self.assertIsNone(msg.model)
        self.assertIsNone(msg.stop_reason)
        self.assertIsNone(msg.usage)

    def test_assistant_message_with_usage(self):
        usage = Usage(input_tokens=10, output_tokens=20)
        msg = AssistantMessage(
            content=[TextBlock(text="hello")],
            model="gpt-4",
            stop_reason="end_turn",
            usage=usage,
        )
        self.assertEqual(msg.usage.input_tokens, 10)
        self.assertEqual(msg.usage.output_tokens, 20)

    def test_system_message(self):
        msg = SystemMessage(subtype="compact_boundary", content="summary")
        self.assertIsNotNone(msg.uuid)
        self.assertIsNone(msg.compact_metadata)

    def test_user_message_with_tool_results(self):
        result = ToolResultBlock(tool_use_id="call_1", content="output")
        msg = UserMessage(content=[result])
        self.assertIsInstance(msg.content[0], ToolResultBlock)


class TestUsage(unittest.TestCase):

    def test_defaults(self):
        usage = Usage()
        self.assertEqual(usage.input_tokens, 0)
        self.assertEqual(usage.output_tokens, 0)
        self.assertEqual(usage.cache_creation_input_tokens, 0)
        self.assertEqual(usage.cache_read_input_tokens, 0)

    def test_custom_values(self):
        usage = Usage(input_tokens=100, output_tokens=50,
                      cache_creation_input_tokens=10,
                      cache_read_input_tokens=5)
        self.assertEqual(usage.input_tokens, 100)
        self.assertEqual(usage.cache_read_input_tokens, 5)


class TestContentBlockUnion(unittest.TestCase):

    def test_content_block_types(self):
        blocks = [
            TextBlock(text="hi"),
            ToolUseBlock(id="1", name="t", input={}),
            ToolResultBlock(tool_use_id="1", content="ok"),
            ThinkingBlock(thinking="hmm"),
        ]
        for block in blocks:
            self.assertIsInstance(block, ContentBlock)


class TestMessageUnion(unittest.TestCase):

    def test_message_types(self):
        msgs = [
            UserMessage(content=[]),
            AssistantMessage(content=[]),
            SystemMessage(subtype="test", content="test"),
        ]
        for msg in msgs:
            self.assertIsInstance(msg, Message)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent'`

- [ ] **Step 3: Create the agent package and types module**

Create `qgitc/agent/__init__.py`:

```python
# -*- coding: utf-8 -*-
```

Create `qgitc/agent/types.py`:

```python
# -*- coding: utf-8 -*-
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


def _make_uuid() -> str:
    return str(uuid.uuid4())


def _make_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class ThinkingBlock:
    thinking: str


# Union of all content block types.
# isinstance() checks work because each is a distinct dataclass.
ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class UserMessage:
    content: List[ContentBlock]
    uuid: str = field(default_factory=_make_uuid)
    timestamp: str = field(default_factory=_make_timestamp)


@dataclass
class AssistantMessage:
    content: List[ContentBlock]
    uuid: str = field(default_factory=_make_uuid)
    timestamp: str = field(default_factory=_make_timestamp)
    model: Optional[str] = None
    stop_reason: Optional[str] = None
    usage: Optional[Usage] = None


@dataclass
class SystemMessage:
    subtype: str
    content: str
    uuid: str = field(default_factory=_make_uuid)
    timestamp: str = field(default_factory=_make_timestamp)
    compact_metadata: Optional[Dict[str, Any]] = None


Message = Union[UserMessage, AssistantMessage, SystemMessage]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_types.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/__init__.py qgitc/agent/types.py tests/test_agent_types.py
git commit -m "Add agent types: message types, content blocks, usage"
```

---

### Task 2: Tool ABC and ToolResult

**Files:**
- Create: `qgitc/agent/tool.py`
- Create: `tests/test_agent_tool.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_tool.py`:

```python
# -*- coding: utf-8 -*-
import unittest

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class EchoTool(Tool):
    name = "echo"
    description = "Echoes input back"

    def execute(self, input_data, context):
        return ToolResult(content=input_data.get("text", ""))

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo"},
            },
            "required": ["text"],
        }


class TestToolABC(unittest.TestCase):

    def test_cannot_instantiate_abstract(self):
        with self.assertRaises(TypeError):
            Tool()

    def test_concrete_tool_has_name(self):
        tool = EchoTool()
        self.assertEqual(tool.name, "echo")
        self.assertEqual(tool.description, "Echoes input back")

    def test_is_read_only_default_false(self):
        tool = EchoTool()
        self.assertFalse(tool.is_read_only())

    def test_is_destructive_default_false(self):
        tool = EchoTool()
        self.assertFalse(tool.is_destructive())

    def test_execute(self):
        tool = EchoTool()
        ctx = ToolContext(working_directory="/tmp", abort_requested=lambda: False)
        result = tool.execute({"text": "hello"}, ctx)
        self.assertEqual(result.content, "hello")
        self.assertFalse(result.is_error)

    def test_input_schema(self):
        tool = EchoTool()
        schema = tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("text", schema["properties"])

    def test_openai_schema(self):
        tool = EchoTool()
        schema = tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "echo")
        self.assertEqual(schema["function"]["description"], "Echoes input back")
        self.assertIn("parameters", schema["function"])


class TestToolResult(unittest.TestCase):

    def test_default_not_error(self):
        r = ToolResult(content="ok")
        self.assertFalse(r.is_error)

    def test_error_result(self):
        r = ToolResult(content="fail", is_error=True)
        self.assertTrue(r.is_error)


class TestToolContext(unittest.TestCase):

    def test_fields(self):
        ctx = ToolContext(working_directory="/repo", abort_requested=lambda: False)
        self.assertEqual(ctx.working_directory, "/repo")
        self.assertFalse(ctx.abort_requested())

    def test_abort_requested(self):
        flag = [False]
        ctx = ToolContext(working_directory="/repo",
                          abort_requested=lambda: flag[0])
        self.assertFalse(ctx.abort_requested())
        flag[0] = True
        self.assertTrue(ctx.abort_requested())


class ReadOnlyTool(Tool):
    name = "readonly"
    description = "A read-only tool"

    def is_read_only(self):
        return True

    def execute(self, input_data, context):
        return ToolResult(content="data")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class TestReadOnlyTool(unittest.TestCase):

    def test_is_read_only(self):
        tool = ReadOnlyTool()
        self.assertTrue(tool.is_read_only())
        self.assertFalse(tool.is_destructive())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent.tool'`

- [ ] **Step 3: Write the Tool ABC implementation**

Create `qgitc/agent/tool.py`:

```python
# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


@dataclass
class ToolContext:
    working_directory: str
    abort_requested: Callable[[], bool]


class Tool(ABC):
    """Abstract base class for agent tools.

    Subclasses must define class attributes ``name`` and ``description``
    and implement ``execute()`` and ``input_schema()``.
    """

    name: str
    description: str

    def is_read_only(self) -> bool:
        return False

    def is_destructive(self) -> bool:
        return False

    @abstractmethod
    def execute(self, input_data: Dict[str, Any],
                context: ToolContext) -> ToolResult:
        ...

    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        ...

    def openai_schema(self) -> Dict[str, Any]:
        """Return tool definition in OpenAI function-call format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema(),
            },
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_tool.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/tool.py tests/test_agent_tool.py
git commit -m "Add Tool ABC with ToolResult, ToolContext, and OpenAI schema"
```

---

### Task 3: ToolRegistry

**Files:**
- Create: `qgitc/agent/tool_registry.py`
- Create: `tests/test_agent_tool_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_tool_registry.py`:

```python
# -*- coding: utf-8 -*-
import unittest

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tool_registry import ToolRegistry


class StubToolA(Tool):
    name = "tool_a"
    description = "Tool A"

    def execute(self, input_data, context):
        return ToolResult(content="a")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class StubToolB(Tool):
    name = "tool_b"
    description = "Tool B"

    def execute(self, input_data, context):
        return ToolResult(content="b")

    def input_schema(self):
        return {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        }


class TestToolRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()

    def test_register_and_get(self):
        tool = StubToolA()
        self.registry.register(tool)
        self.assertIs(self.registry.get("tool_a"), tool)

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.registry.get("nonexistent"))

    def test_list_tools(self):
        a = StubToolA()
        b = StubToolB()
        self.registry.register(a)
        self.registry.register(b)
        tools = self.registry.list_tools()
        self.assertEqual(len(tools), 2)
        names = {t.name for t in tools}
        self.assertEqual(names, {"tool_a", "tool_b"})

    def test_unregister(self):
        self.registry.register(StubToolA())
        self.registry.unregister("tool_a")
        self.assertIsNone(self.registry.get("tool_a"))
        self.assertEqual(len(self.registry.list_tools()), 0)

    def test_unregister_missing_is_noop(self):
        self.registry.unregister("nonexistent")  # should not raise

    def test_register_overwrites(self):
        tool1 = StubToolA()
        tool2 = StubToolA()
        self.registry.register(tool1)
        self.registry.register(tool2)
        self.assertIs(self.registry.get("tool_a"), tool2)

    def test_get_tool_schemas(self):
        self.registry.register(StubToolA())
        self.registry.register(StubToolB())
        schemas = self.registry.get_tool_schemas()
        self.assertEqual(len(schemas), 2)
        for s in schemas:
            self.assertEqual(s["type"], "function")
            self.assertIn("function", s)
            self.assertIn("name", s["function"])
            self.assertIn("parameters", s["function"])

    def test_empty_registry(self):
        self.assertEqual(self.registry.list_tools(), [])
        self.assertEqual(self.registry.get_tool_schemas(), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_tool_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent.tool_registry'`

- [ ] **Step 3: Write the ToolRegistry implementation**

Create `qgitc/agent/tool_registry.py`:

```python
# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Optional

from qgitc.agent.tool import Tool


class ToolRegistry:
    """Central registry for agent tools."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [tool.openai_schema() for tool in self._tools.values()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_tool_registry.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/tool_registry.py tests/test_agent_tool_registry.py
git commit -m "Add ToolRegistry for agent tool management"
```

---

### Task 4: ModelProvider ABC and StreamEvent types

**Files:**
- Create: `qgitc/agent/provider.py`
- Create: `tests/test_agent_provider.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_provider.py`:

```python
# -*- coding: utf-8 -*-
import unittest
from typing import Iterator

from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    StreamEvent,
    ToolCallDelta,
)
from qgitc.agent.types import Usage


class TestStreamEvents(unittest.TestCase):

    def test_content_delta(self):
        e = ContentDelta(text="hello")
        self.assertEqual(e.text, "hello")
        self.assertIsInstance(e, StreamEvent)

    def test_reasoning_delta(self):
        e = ReasoningDelta(text="thinking")
        self.assertEqual(e.text, "thinking")
        self.assertIsInstance(e, StreamEvent)

    def test_tool_call_delta(self):
        e = ToolCallDelta(id="call_1", name="git_status", arguments_delta='{"p')
        self.assertEqual(e.id, "call_1")
        self.assertEqual(e.name, "git_status")
        self.assertEqual(e.arguments_delta, '{"p')
        self.assertIsInstance(e, StreamEvent)

    def test_message_complete(self):
        usage = Usage(input_tokens=10, output_tokens=5)
        e = MessageComplete(stop_reason="end_turn", usage=usage)
        self.assertEqual(e.stop_reason, "end_turn")
        self.assertEqual(e.usage.input_tokens, 10)
        self.assertIsInstance(e, StreamEvent)

    def test_message_complete_no_usage(self):
        e = MessageComplete(stop_reason="tool_use")
        self.assertIsNone(e.usage)


class FakeProvider(ModelProvider):

    def __init__(self, events):
        self._events = events

    def stream(self, messages, system_prompt=None, tools=None,
               model=None, max_tokens=4096):
        yield from self._events

    def count_tokens(self, messages, system_prompt=None, tools=None):
        return 42


class TestModelProviderProtocol(unittest.TestCase):

    def test_cannot_instantiate_abstract(self):
        with self.assertRaises(TypeError):
            ModelProvider()

    def test_fake_provider_stream(self):
        events = [
            ContentDelta(text="hi"),
            MessageComplete(stop_reason="end_turn"),
        ]
        provider = FakeProvider(events)
        result = list(provider.stream(messages=[]))
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], ContentDelta)
        self.assertIsInstance(result[1], MessageComplete)

    def test_fake_provider_count_tokens(self):
        provider = FakeProvider([])
        self.assertEqual(provider.count_tokens(messages=[]), 42)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent.provider'`

- [ ] **Step 3: Write the ModelProvider and StreamEvent implementation**

Create `qgitc/agent/provider.py`:

```python
# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Union

from qgitc.agent.types import Message, Usage


@dataclass
class ContentDelta:
    text: str


@dataclass
class ReasoningDelta:
    text: str


@dataclass
class ToolCallDelta:
    id: str
    name: str
    arguments_delta: str


@dataclass
class MessageComplete:
    stop_reason: str
    usage: Optional[Usage] = None


StreamEvent = Union[ContentDelta, ReasoningDelta, ToolCallDelta, MessageComplete]


class ModelProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def stream(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> Iterator[StreamEvent]:
        ...

    @abstractmethod
    def count_tokens(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_provider.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/provider.py tests/test_agent_provider.py
git commit -m "Add ModelProvider ABC and StreamEvent types"
```

---

### Task 5: Permission engine

**Files:**
- Create: `qgitc/agent/permissions.py`
- Create: `tests/test_agent_permissions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_permissions.py`:

```python
# -*- coding: utf-8 -*-
import unittest

from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionBehavior,
    PermissionDeny,
    PermissionEngine,
    PermissionRule,
    PermissionUpdate,
)
from qgitc.agent.tool import Tool, ToolResult


class StubReadOnlyTool(Tool):
    name = "git_status"
    description = "Show git status"

    def is_read_only(self):
        return True

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class StubWriteTool(Tool):
    name = "git_commit"
    description = "Commit changes"

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class StubDestructiveTool(Tool):
    name = "run_command"
    description = "Run a shell command"

    def is_destructive(self):
        return True

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class TestPermissionEngineDefaults(unittest.TestCase):

    def test_read_only_tool_allowed_by_default(self):
        engine = PermissionEngine()
        result = engine.check(StubReadOnlyTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_write_tool_asks_by_default(self):
        engine = PermissionEngine()
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)

    def test_destructive_tool_asks_by_default(self):
        engine = PermissionEngine()
        result = engine.check(StubDestructiveTool(), {})
        self.assertIsInstance(result, PermissionAsk)


class TestPermissionEngineDenyRules(unittest.TestCase):

    def test_deny_rule_blocks_tool(self):
        engine = PermissionEngine(
            deny_rules=[PermissionRule(tool_name="run_command")]
        )
        result = engine.check(StubDestructiveTool(), {})
        self.assertIsInstance(result, PermissionDeny)

    def test_deny_wildcard_blocks_all(self):
        engine = PermissionEngine(
            deny_rules=[PermissionRule(tool_name="*")]
        )
        result = engine.check(StubReadOnlyTool(), {})
        self.assertIsInstance(result, PermissionDeny)

    def test_deny_takes_precedence_over_allow(self):
        engine = PermissionEngine(
            allow_rules=[PermissionRule(tool_name="run_command")],
            deny_rules=[PermissionRule(tool_name="run_command")],
        )
        result = engine.check(StubDestructiveTool(), {})
        self.assertIsInstance(result, PermissionDeny)


class TestPermissionEngineAllowRules(unittest.TestCase):

    def test_allow_rule_permits_write_tool(self):
        engine = PermissionEngine(
            allow_rules=[PermissionRule(tool_name="git_commit")]
        )
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_allow_wildcard_permits_all(self):
        engine = PermissionEngine(
            allow_rules=[PermissionRule(tool_name="*")]
        )
        result = engine.check(StubDestructiveTool(), {})
        self.assertIsInstance(result, PermissionAllow)


class TestPermissionEnginePatternRules(unittest.TestCase):

    def test_deny_with_matching_pattern(self):
        engine = PermissionEngine(
            deny_rules=[PermissionRule(tool_name="run_command", pattern="rm -rf")]
        )
        result = engine.check(StubDestructiveTool(), {"command": "rm -rf /"})
        self.assertIsInstance(result, PermissionDeny)

    def test_deny_with_non_matching_pattern(self):
        engine = PermissionEngine(
            deny_rules=[PermissionRule(tool_name="run_command", pattern="rm -rf")]
        )
        result = engine.check(StubDestructiveTool(), {"command": "ls"})
        self.assertIsInstance(result, PermissionAsk)


class TestPermissionUpdate(unittest.TestCase):

    def test_add_allow_rule(self):
        engine = PermissionEngine()
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)

        engine.apply_update(PermissionUpdate(
            action="add",
            rule=PermissionRule(tool_name="git_commit",
                                behavior=PermissionBehavior.ALLOW),
        ))
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_add_deny_rule(self):
        engine = PermissionEngine()
        engine.apply_update(PermissionUpdate(
            action="add",
            rule=PermissionRule(tool_name="git_status",
                                behavior=PermissionBehavior.DENY),
        ))
        result = engine.check(StubReadOnlyTool(), {})
        self.assertIsInstance(result, PermissionDeny)

    def test_remove_rule(self):
        rule = PermissionRule(tool_name="git_commit",
                              behavior=PermissionBehavior.ALLOW)
        engine = PermissionEngine(allow_rules=[rule])
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAllow)

        engine.apply_update(PermissionUpdate(action="remove", rule=rule))
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)


class TestPermissionAskMessage(unittest.TestCase):

    def test_ask_includes_tool_name(self):
        engine = PermissionEngine()
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)
        self.assertIn("git_commit", result.message)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_permissions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent.permissions'`

- [ ] **Step 3: Write the permission engine implementation**

Create `qgitc/agent/permissions.py`:

```python
# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from qgitc.agent.tool import Tool


class PermissionBehavior(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class PermissionRule:
    tool_name: str
    behavior: PermissionBehavior = PermissionBehavior.ASK
    pattern: Optional[str] = None


@dataclass
class PermissionAllow:
    updated_input: Optional[Dict[str, Any]] = None


@dataclass
class PermissionAsk:
    message: str = ""


@dataclass
class PermissionDeny:
    message: str = ""


PermissionResult = object  # Union[PermissionAllow, PermissionAsk, PermissionDeny]


@dataclass
class PermissionUpdate:
    action: str  # "add" or "remove"
    rule: PermissionRule = None


def _rule_matches(rule: PermissionRule, tool: Tool,
                  input_data: Dict[str, Any]) -> bool:
    if rule.tool_name != "*" and rule.tool_name != tool.name:
        return False
    if rule.pattern is not None:
        input_str = " ".join(str(v) for v in input_data.values())
        if rule.pattern not in input_str:
            return False
    return True


class PermissionEngine:
    """Decides whether a tool invocation is allowed, needs confirmation,
    or is denied.

    Pipeline:
    1. Deny rules match? -> Deny
    2. Allow rules match? -> Allow
    3. Tool is read-only? -> Allow
    4. Otherwise -> Ask
    """

    def __init__(
        self,
        allow_rules: Optional[List[PermissionRule]] = None,
        deny_rules: Optional[List[PermissionRule]] = None,
    ):
        self._allow_rules: List[PermissionRule] = list(allow_rules or [])
        self._deny_rules: List[PermissionRule] = list(deny_rules or [])

    def check(self, tool: Tool,
              input_data: Dict[str, Any]) -> "PermissionResult":
        # Step 1: deny rules
        for rule in self._deny_rules:
            if _rule_matches(rule, tool, input_data):
                return PermissionDeny(
                    message="Tool '{}' is denied by rule".format(tool.name))

        # Step 2: allow rules
        for rule in self._allow_rules:
            if _rule_matches(rule, tool, input_data):
                return PermissionAllow()

        # Step 3: read-only tools are allowed
        if tool.is_read_only():
            return PermissionAllow()

        # Step 4: ask
        return PermissionAsk(
            message="Tool '{}' requires confirmation".format(tool.name))

    def apply_update(self, update: PermissionUpdate) -> None:
        if update.rule is None:
            return

        if update.rule.behavior == PermissionBehavior.ALLOW:
            target_list = self._allow_rules
        elif update.rule.behavior == PermissionBehavior.DENY:
            target_list = self._deny_rules
        else:
            return

        if update.action == "add":
            target_list.append(update.rule)
        elif update.action == "remove":
            try:
                target_list.remove(update.rule)
            except ValueError:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_permissions.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/permissions.py tests/test_agent_permissions.py
git commit -m "Add permission engine with allow/ask/deny rules"
```

---

### Task 6: Conversation compaction

**Files:**
- Create: `qgitc/agent/compaction.py`
- Create: `tests/test_agent_compaction.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_compaction.py`:

```python
# -*- coding: utf-8 -*-
import unittest

from qgitc.agent.compaction import ConversationCompactor, estimate_tokens
from qgitc.agent.provider import ContentDelta, MessageComplete, ModelProvider
from qgitc.agent.types import (
    AssistantMessage,
    SystemMessage,
    TextBlock,
    Usage,
    UserMessage,
)


class FakeSummaryProvider(ModelProvider):
    """Returns a fixed summary text."""

    def __init__(self, summary_text="Summary of conversation."):
        self._summary = summary_text

    def stream(self, messages, system_prompt=None, tools=None,
               model=None, max_tokens=4096):
        yield ContentDelta(text=self._summary)
        yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        return estimate_tokens(messages)


class TestEstimateTokens(unittest.TestCase):

    def test_empty_messages(self):
        self.assertEqual(estimate_tokens([]), 0)

    def test_estimates_by_char_count(self):
        msg = UserMessage(content=[TextBlock(text="a" * 400)])
        tokens = estimate_tokens([msg])
        self.assertEqual(tokens, 100)  # 400 chars / 4

    def test_multiple_messages(self):
        msgs = [
            UserMessage(content=[TextBlock(text="a" * 400)]),
            AssistantMessage(content=[TextBlock(text="b" * 800)]),
        ]
        tokens = estimate_tokens(msgs)
        self.assertEqual(tokens, 300)  # (400 + 800) / 4


class TestShouldCompact(unittest.TestCase):

    def test_no_compact_when_under_threshold(self):
        compactor = ConversationCompactor(
            provider=FakeSummaryProvider(),
            context_window=100000,
            max_output_tokens=4096,
        )
        msgs = [UserMessage(content=[TextBlock(text="short")])]
        self.assertFalse(compactor.should_compact(msgs))

    def test_compact_when_over_threshold(self):
        compactor = ConversationCompactor(
            provider=FakeSummaryProvider(),
            context_window=1000,
            max_output_tokens=200,
        )
        # ~2500 tokens worth of text (10000 chars / 4)
        msgs = [UserMessage(content=[TextBlock(text="x" * 10000)])]
        self.assertTrue(compactor.should_compact(msgs))

    def test_empty_messages_no_compact(self):
        compactor = ConversationCompactor(
            provider=FakeSummaryProvider(),
            context_window=1000,
            max_output_tokens=200,
        )
        self.assertFalse(compactor.should_compact([]))


class TestCompact(unittest.TestCase):

    def test_compact_returns_boundary_and_summary(self):
        compactor = ConversationCompactor(
            provider=FakeSummaryProvider("The summary."),
            context_window=1000,
            max_output_tokens=200,
        )
        msgs = [
            UserMessage(content=[TextBlock(text="a" * 4000)]),
            AssistantMessage(content=[TextBlock(text="b" * 4000)]),
        ]
        result = compactor.compact(msgs)
        self.assertIsInstance(result.boundary, SystemMessage)
        self.assertEqual(result.boundary.subtype, "compact_boundary")
        self.assertIsInstance(result.summary, UserMessage)
        self.assertEqual(len(result.summary.content), 1)
        self.assertIsInstance(result.summary.content[0], TextBlock)
        self.assertIn("The summary.", result.summary.content[0].text)
        self.assertGreater(result.pre_token_estimate, 0)
        self.assertGreater(result.pre_token_estimate, result.post_token_estimate)

    def test_compact_empty_raises(self):
        compactor = ConversationCompactor(
            provider=FakeSummaryProvider(),
            context_window=1000,
            max_output_tokens=200,
        )
        with self.assertRaises(ValueError):
            compactor.compact([])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_compaction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent.compaction'`

- [ ] **Step 3: Write the compaction implementation**

Create `qgitc/agent/compaction.py`:

```python
# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from qgitc.agent.provider import ContentDelta, ModelProvider, StreamEvent
from qgitc.agent.types import (
    AssistantMessage,
    ContentBlock,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


def _message_text(msg: Message) -> str:
    """Extract all text content from a message for token estimation."""
    if isinstance(msg, (UserMessage, AssistantMessage)):
        parts = []
        for block in msg.content:
            if isinstance(block, TextBlock):
                parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                parts.append(block.name)
                parts.append(str(block.input))
            elif isinstance(block, ToolResultBlock):
                parts.append(block.content)
            elif isinstance(block, ThinkingBlock):
                parts.append(block.thinking)
        return " ".join(parts)
    elif isinstance(msg, SystemMessage):
        return msg.content
    return ""


def estimate_tokens(messages: List[Message]) -> int:
    """Heuristic: ~4 characters per token."""
    total_chars = sum(len(_message_text(m)) for m in messages)
    return total_chars // 4


def _build_summarization_prompt(messages: List[Message]) -> str:
    """Build a prompt asking the LLM to summarize the conversation."""
    parts = ["Summarize the following conversation concisely. "
             "Preserve key decisions, tool results, and context "
             "needed to continue the conversation.\n\n"]
    for msg in messages:
        if isinstance(msg, UserMessage):
            parts.append("User: " + _message_text(msg) + "\n")
        elif isinstance(msg, AssistantMessage):
            parts.append("Assistant: " + _message_text(msg) + "\n")
        elif isinstance(msg, SystemMessage):
            parts.append("System: " + msg.content + "\n")
    return "".join(parts)


@dataclass
class CompactionResult:
    boundary: SystemMessage
    summary: UserMessage
    pre_token_estimate: int
    post_token_estimate: int


class ConversationCompactor:
    """Compacts conversation history when approaching context limits."""

    BUFFER_TOKENS = 2000

    def __init__(
        self,
        provider: ModelProvider,
        context_window: int,
        max_output_tokens: int,
    ):
        self._provider = provider
        self._context_window = context_window
        self._max_output_tokens = max_output_tokens

    def _threshold(self) -> int:
        return (self._context_window
                - self._max_output_tokens
                - self.BUFFER_TOKENS)

    def should_compact(self, messages: List[Message]) -> bool:
        if not messages:
            return False
        return estimate_tokens(messages) > self._threshold()

    def compact(self, messages: List[Message]) -> CompactionResult:
        if not messages:
            raise ValueError("Cannot compact empty message list")

        pre_tokens = estimate_tokens(messages)

        prompt = _build_summarization_prompt(messages)
        summary_parts = []
        for event in self._provider.stream(
            messages=[UserMessage(content=[TextBlock(text=prompt)])],
        ):
            if isinstance(event, ContentDelta):
                summary_parts.append(event.text)

        summary_text = "".join(summary_parts)

        boundary = SystemMessage(
            subtype="compact_boundary",
            content="Conversation compacted",
            compact_metadata={"pre_token_estimate": pre_tokens},
        )
        summary_msg = UserMessage(
            content=[TextBlock(
                text="[Conversation summary]\n" + summary_text
            )]
        )

        post_tokens = estimate_tokens([summary_msg])

        return CompactionResult(
            boundary=boundary,
            summary=summary_msg,
            pre_token_estimate=pre_tokens,
            post_token_estimate=post_tokens,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_compaction.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/compaction.py tests/test_agent_compaction.py
git commit -m "Add conversation compaction with token estimation"
```

---

### Task 7: AgentLoop core — QThread with streaming and turn management

**Files:**
- Create: `qgitc/agent/agent_loop.py`
- Create: `tests/test_agent_loop.py`

This is the largest task. The agent loop orchestrates: prompt → LLM stream → tool execution → permission checks → compaction → loop.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_loop.py`:

```python
# -*- coding: utf-8 -*-
import json
import sys
import unittest
from unittest.mock import MagicMock

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QThread
from PySide6.QtTest import QSignalSpy

from qgitc.agent.agent_loop import AgentLoop
from qgitc.agent.compaction import ConversationCompactor
from qgitc.agent.permissions import PermissionEngine
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ToolCallDelta,
)
from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import AssistantMessage, TextBlock, Usage


def processEvents(app, timeout=2000):
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < timeout:
        app.sendPostedEvents()
        app.processEvents()


def waitFor(app, condition, timeout=5000):
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < timeout:
        app.sendPostedEvents()
        app.processEvents()
        if condition():
            return True
    return False


class SimpleProvider(ModelProvider):
    """Returns a single text response, then end_turn."""

    def __init__(self, text="Hello from LLM"):
        self._text = text

    def stream(self, messages, system_prompt=None, tools=None,
               model=None, max_tokens=4096):
        yield ContentDelta(text=self._text)
        yield MessageComplete(stop_reason="end_turn",
                              usage=Usage(input_tokens=10, output_tokens=5))

    def count_tokens(self, messages, system_prompt=None, tools=None):
        return 10


class ToolCallProvider(ModelProvider):
    """First call returns a tool_use, second call returns end_turn."""

    def __init__(self):
        self._call_count = 0

    def stream(self, messages, system_prompt=None, tools=None,
               model=None, max_tokens=4096):
        self._call_count += 1
        if self._call_count == 1:
            yield ToolCallDelta(
                id="call_1", name="echo",
                arguments_delta=json.dumps({"text": "ping"}),
            )
            yield MessageComplete(stop_reason="tool_use",
                                  usage=Usage(input_tokens=10, output_tokens=5))
        else:
            yield ContentDelta(text="Tool returned: pong")
            yield MessageComplete(stop_reason="end_turn",
                                  usage=Usage(input_tokens=15, output_tokens=8))

    def count_tokens(self, messages, system_prompt=None, tools=None):
        return 10


class EchoTool(Tool):
    name = "echo"
    description = "Echoes text"

    def is_read_only(self):
        return True

    def execute(self, input_data, context):
        return ToolResult(content="pong")

    def input_schema(self):
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }


def _make_app():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


class TestAgentLoopSimple(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.registry = ToolRegistry()
        self.engine = PermissionEngine()
        self.provider = SimpleProvider()
        self.compactor = ConversationCompactor(
            provider=self.provider,
            context_window=100000,
            max_output_tokens=4096,
        )
        self.loop = AgentLoop(
            provider=self.provider,
            tool_registry=self.registry,
            permission_engine=self.engine,
            compactor=self.compactor,
        )

    def tearDown(self):
        if self.loop.isRunning():
            self.loop.abort()
            self.loop.wait(3000)

    def test_simple_text_response(self):
        text_spy = QSignalSpy(self.loop.textDelta)
        finished_spy = QSignalSpy(self.loop.agentFinished)
        turn_spy = QSignalSpy(self.loop.turnComplete)

        self.loop.submit("Hello")
        ok = waitFor(self.app, lambda: len(finished_spy) > 0)
        self.assertTrue(ok, "Agent did not finish in time")

        self.assertGreater(len(text_spy), 0)
        self.assertEqual(text_spy[0][0], "Hello from LLM")
        self.assertEqual(len(turn_spy), 1)

    def test_messages_accumulate(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)
        self.loop.submit("Hello")
        waitFor(self.app, lambda: len(finished_spy) > 0)

        msgs = self.loop.messages()
        self.assertEqual(len(msgs), 2)  # UserMessage + AssistantMessage

    def test_abort(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)
        self.loop.submit("Hello")
        self.loop.abort()
        waitFor(self.app, lambda: not self.loop.isRunning(), timeout=3000)
        self.assertFalse(self.loop.isRunning())


class TestAgentLoopToolExecution(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.registry = ToolRegistry()
        self.registry.register(EchoTool())
        self.engine = PermissionEngine()  # read-only auto-allowed
        self.provider = ToolCallProvider()
        self.compactor = ConversationCompactor(
            provider=self.provider,
            context_window=100000,
            max_output_tokens=4096,
        )
        self.loop = AgentLoop(
            provider=self.provider,
            tool_registry=self.registry,
            permission_engine=self.engine,
            compactor=self.compactor,
        )

    def tearDown(self):
        if self.loop.isRunning():
            self.loop.abort()
            self.loop.wait(3000)

    def test_tool_call_and_continuation(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)
        tool_start_spy = QSignalSpy(self.loop.toolCallStart)
        tool_result_spy = QSignalSpy(self.loop.toolCallResult)
        text_spy = QSignalSpy(self.loop.textDelta)

        self.loop.submit("Please echo")
        ok = waitFor(self.app, lambda: len(finished_spy) > 0)
        self.assertTrue(ok, "Agent did not finish in time")

        # Tool was called
        self.assertEqual(len(tool_start_spy), 1)
        self.assertEqual(tool_start_spy[0][1], "echo")  # tool name

        # Tool result was returned
        self.assertEqual(len(tool_result_spy), 1)
        self.assertEqual(tool_result_spy[0][0], "call_1")  # tool_call_id

        # Final text response after tool
        self.assertGreater(len(text_spy), 0)

    def test_messages_include_tool_round(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)
        self.loop.submit("Please echo")
        waitFor(self.app, lambda: len(finished_spy) > 0)

        msgs = self.loop.messages()
        # UserMessage, AssistantMessage(tool_use), UserMessage(tool_result),
        # AssistantMessage(text)
        self.assertEqual(len(msgs), 4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent.agent_loop'`

- [ ] **Step 3: Write the AgentLoop implementation**

Create `qgitc/agent/agent_loop.py`:

```python
# -*- coding: utf-8 -*-
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from qgitc.agent.compaction import ConversationCompactor
from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionDeny,
    PermissionEngine,
)
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    ToolCallDelta,
)
from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import (
    AssistantMessage,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

logger = logging.getLogger(__name__)


class AgentLoop(QThread):
    """Orchestrates the LLM agent loop in a dedicated thread.

    Communicates with the main thread via Qt signals.
    """

    textDelta = Signal(str)
    reasoningDelta = Signal(str)
    toolCallStart = Signal(str, str, dict)        # id, name, input
    toolCallResult = Signal(str, str, bool)        # id, content, is_error
    turnComplete = Signal(object)                  # AssistantMessage
    agentFinished = Signal()
    conversationCompacted = Signal(int, int)        # pre, post tokens
    permissionRequired = Signal(str, object, dict)  # id, Tool, input
    errorOccurred = Signal(str)

    def __init__(
        self,
        provider: ModelProvider,
        tool_registry: ToolRegistry,
        permission_engine: PermissionEngine,
        compactor: ConversationCompactor,
        system_prompt: str = "",
        max_turns: int = 25,
        parent=None,
    ):
        super().__init__(parent)
        self._provider = provider
        self._tool_registry = tool_registry
        self._permission_engine = permission_engine
        self._compactor = compactor
        self._system_prompt = system_prompt
        self._max_turns = max_turns

        self._messages: List[Message] = []
        self._pending_prompt: Optional[str] = None
        self._abort_flag = False

        # Permission wait mechanism
        self._perm_mutex = QMutex()
        self._perm_cond = QWaitCondition()
        self._perm_decisions: Dict[str, bool] = {}  # tool_call_id -> approved

    def submit(self, prompt: str, context_blocks: list = None) -> None:
        """Submit a prompt and start the agent loop."""
        content = []
        if context_blocks:
            for block in context_blocks:
                content.append(block)
        content.append(TextBlock(text=prompt))
        self._messages.append(UserMessage(content=content))
        self._abort_flag = False
        self._perm_decisions.clear()
        self.start()

    def approve_tool(self, tool_call_id: str) -> None:
        """Approve a pending tool execution (called from main thread)."""
        self._perm_mutex.lock()
        self._perm_decisions[tool_call_id] = True
        self._perm_cond.wakeAll()
        self._perm_mutex.unlock()

    def deny_tool(self, tool_call_id: str, message: str = "") -> None:
        """Deny a pending tool execution (called from main thread)."""
        self._perm_mutex.lock()
        self._perm_decisions[tool_call_id] = False
        self._perm_cond.wakeAll()
        self._perm_mutex.unlock()

    def abort(self) -> None:
        """Signal the agent loop to stop."""
        self._abort_flag = True
        # Wake any waiting permission check
        self._perm_mutex.lock()
        self._perm_cond.wakeAll()
        self._perm_mutex.unlock()

    def messages(self) -> List[Message]:
        """Return a copy of the conversation history (thread-safe)."""
        return list(self._messages)

    def run(self) -> None:
        """Main agent loop — runs in a dedicated thread."""
        try:
            self._run_loop()
        except Exception as e:
            logger.exception("Agent loop error")
            self.errorOccurred.emit(str(e))
        finally:
            self.agentFinished.emit()

    def _run_loop(self) -> None:
        for turn in range(self._max_turns):
            if self._abort_flag:
                return

            # Check compaction
            if self._compactor.should_compact(self._messages):
                result = self._compactor.compact(self._messages)
                self._messages = [result.boundary, result.summary]
                self.conversationCompacted.emit(
                    result.pre_token_estimate,
                    result.post_token_estimate,
                )

            if self._abort_flag:
                return

            # Stream from provider
            tool_schemas = self._tool_registry.get_tool_schemas() or None
            assistant_msg = self._stream_response(tool_schemas)
            if assistant_msg is None:
                return

            self._messages.append(assistant_msg)
            self.turnComplete.emit(assistant_msg)

            # Check if we need to execute tools
            tool_blocks = [
                b for b in assistant_msg.content
                if isinstance(b, ToolUseBlock)
            ]
            if assistant_msg.stop_reason != "tool_use" or not tool_blocks:
                return

            # Execute tools
            tool_results = self._execute_tool_blocks(tool_blocks)
            if tool_results is None:
                return  # aborted

            self._messages.append(
                UserMessage(content=tool_results)
            )

    def _stream_response(self, tool_schemas):
        """Stream from the LLM and accumulate into an AssistantMessage."""
        text_parts = []
        reasoning_parts = []
        tool_calls = {}  # id -> {name, arguments_parts}
        stop_reason = None
        usage = None

        try:
            for event in self._provider.stream(
                messages=self._messages,
                system_prompt=self._system_prompt or None,
                tools=tool_schemas,
            ):
                if self._abort_flag:
                    return None

                if isinstance(event, ContentDelta):
                    text_parts.append(event.text)
                    self.textDelta.emit(event.text)

                elif isinstance(event, ReasoningDelta):
                    reasoning_parts.append(event.text)
                    self.reasoningDelta.emit(event.text)

                elif isinstance(event, ToolCallDelta):
                    if event.id not in tool_calls:
                        tool_calls[event.id] = {
                            "name": event.name,
                            "arguments_parts": [],
                        }
                    tc = tool_calls[event.id]
                    if event.name and not tc["name"]:
                        tc["name"] = event.name
                    tc["arguments_parts"].append(event.arguments_delta)

                elif isinstance(event, MessageComplete):
                    stop_reason = event.stop_reason
                    usage = event.usage

        except Exception as e:
            logger.exception("Provider stream error")
            self.errorOccurred.emit(str(e))
            return None

        # Build content blocks
        content = []
        if text_parts:
            content.append(TextBlock(text="".join(text_parts)))
        for tc_id, tc_data in tool_calls.items():
            args_str = "".join(tc_data["arguments_parts"])
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {}
            content.append(ToolUseBlock(
                id=tc_id, name=tc_data["name"], input=args,
            ))

        return AssistantMessage(
            content=content,
            stop_reason=stop_reason,
            usage=usage,
        )

    def _execute_tool_blocks(self, tool_blocks):
        """Execute tool calls, respecting permissions."""
        results = []
        for block in tool_blocks:
            if self._abort_flag:
                return None

            tool = self._tool_registry.get(block.name)
            if tool is None:
                results.append(ToolResultBlock(
                    tool_use_id=block.id,
                    content="Unknown tool: {}".format(block.name),
                    is_error=True,
                ))
                self.toolCallResult.emit(
                    block.id,
                    "Unknown tool: {}".format(block.name),
                    True,
                )
                continue

            # Permission check
            perm = self._permission_engine.check(tool, block.input)
            if isinstance(perm, PermissionDeny):
                results.append(ToolResultBlock(
                    tool_use_id=block.id,
                    content=perm.message,
                    is_error=True,
                ))
                self.toolCallResult.emit(block.id, perm.message, True)
                continue

            if isinstance(perm, PermissionAsk):
                self.permissionRequired.emit(block.id, tool, block.input)

                # Wait for user decision
                self._perm_mutex.lock()
                while (block.id not in self._perm_decisions
                       and not self._abort_flag):
                    self._perm_cond.wait(self._perm_mutex)
                self._perm_mutex.unlock()

                if self._abort_flag:
                    return None

                if not self._perm_decisions.get(block.id, False):
                    results.append(ToolResultBlock(
                        tool_use_id=block.id,
                        content="Tool execution denied by user",
                        is_error=True,
                    ))
                    self.toolCallResult.emit(
                        block.id, "Tool execution denied by user", True)
                    continue

            # Execute
            self.toolCallStart.emit(block.id, block.name, block.input)
            ctx = ToolContext(
                working_directory=".",
                abort_requested=lambda: self._abort_flag,
            )
            try:
                result = tool.execute(block.input, ctx)
            except Exception as e:
                logger.exception("Tool execution error: %s", block.name)
                result = ToolResult(content=str(e), is_error=True)

            results.append(ToolResultBlock(
                tool_use_id=block.id,
                content=result.content,
                is_error=result.is_error,
            ))
            self.toolCallResult.emit(
                block.id, result.content, result.is_error)

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_loop.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/agent_loop.py tests/test_agent_loop.py
git commit -m "Add AgentLoop: QThread-based agent with streaming and tool execution"
```

---

### Task 8: AiModelBase adapter

**Files:**
- Create: `qgitc/agent/aimodel_adapter.py`
- Create: `tests/test_agent_aimodel_adapter.py`

This adapter bridges the existing `AiModelBase` (signal-driven) to the `ModelProvider` protocol (iterator-based). It uses a `QEventLoop` inside the agent's QThread to convert signals into a sequential flow.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_aimodel_adapter.py`:

```python
# -*- coding: utf-8 -*-
import json
import sys
import unittest
from unittest.mock import MagicMock

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QTimer

from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ReasoningDelta,
    ToolCallDelta,
)
from qgitc.agent.types import TextBlock, UserMessage
from qgitc.llm import AiChatMode, AiModelBase, AiResponse, AiRole


def _make_app():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


class FakeAiModel(AiModelBase):
    """Simulates AiModelBase by emitting signals on a timer."""

    def __init__(self, responses, parent=None):
        super().__init__("http://fake", parent=parent)
        self._responses = responses
        self._modelId = "fake-model"

    def queryAsync(self, params):
        self._isStreaming = params.stream
        # Emit responses asynchronously via timer
        self._emit_idx = 0
        QTimer.singleShot(10, self._emitNext)

    def _emitNext(self):
        if self._emit_idx < len(self._responses):
            self.responseAvailable.emit(self._responses[self._emit_idx])
            self._emit_idx += 1
            QTimer.singleShot(10, self._emitNext)
        else:
            self.finished.emit()

    def models(self):
        return [("fake-model", "Fake Model")]

    def supportsToolCalls(self, modelId=None):
        return True


class TestAiModelBaseAdapterText(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()

    def test_stream_text_response(self):
        responses = [
            AiResponse(message="Hello ", is_delta=True, first_delta=True),
            AiResponse(message="world", is_delta=True),
        ]
        model = FakeAiModel(responses)
        adapter = AiModelBaseAdapter(model)

        events = list(adapter.stream(
            messages=[UserMessage(content=[TextBlock(text="Hi")])],
        ))

        content_deltas = [e for e in events if isinstance(e, ContentDelta)]
        completes = [e for e in events if isinstance(e, MessageComplete)]

        self.assertEqual(len(content_deltas), 2)
        self.assertEqual(content_deltas[0].text, "Hello ")
        self.assertEqual(content_deltas[1].text, "world")
        self.assertEqual(len(completes), 1)
        self.assertEqual(completes[0].stop_reason, "end_turn")


class TestAiModelBaseAdapterToolCalls(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()

    def test_stream_tool_call_response(self):
        tool_calls = [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "git_status",
                "arguments": '{"path": "."}',
            },
        }]
        responses = [
            AiResponse(message="Let me check.", is_delta=True,
                       first_delta=True),
            AiResponse(message=None, is_delta=True, tool_calls=tool_calls),
        ]
        model = FakeAiModel(responses)
        adapter = AiModelBaseAdapter(model)

        events = list(adapter.stream(
            messages=[UserMessage(content=[TextBlock(text="status")])],
        ))

        tc_deltas = [e for e in events if isinstance(e, ToolCallDelta)]
        completes = [e for e in events if isinstance(e, MessageComplete)]

        self.assertGreater(len(tc_deltas), 0)
        self.assertEqual(tc_deltas[0].name, "git_status")
        self.assertEqual(len(completes), 1)
        self.assertEqual(completes[0].stop_reason, "tool_use")


class TestAiModelBaseAdapterReasoning(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()

    def test_stream_reasoning(self):
        responses = [
            AiResponse(reasoning="Let me think...", message=None,
                       is_delta=True, first_delta=True),
            AiResponse(message="The answer is 42", is_delta=True),
        ]
        model = FakeAiModel(responses)
        adapter = AiModelBaseAdapter(model)

        events = list(adapter.stream(
            messages=[UserMessage(content=[TextBlock(text="question")])],
        ))

        reasoning = [e for e in events if isinstance(e, ReasoningDelta)]
        content = [e for e in events if isinstance(e, ContentDelta)]

        self.assertEqual(len(reasoning), 1)
        self.assertEqual(reasoning[0].text, "Let me think...")
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0].text, "The answer is 42")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_aimodel_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent.aimodel_adapter'`

- [ ] **Step 3: Write the adapter implementation**

Create `qgitc/agent/aimodel_adapter.py`:

```python
# -*- coding: utf-8 -*-
import logging
import queue
from typing import Any, Dict, Iterator, List, Optional

from PySide6.QtCore import QCoreApplication, QElapsedTimer

from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    StreamEvent,
    ToolCallDelta,
)
from qgitc.agent.types import (
    AssistantMessage,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UserMessage,
)
from qgitc.llm import (
    AiChatMessage,
    AiChatMode,
    AiModelBase,
    AiParameters,
    AiResponse,
    AiRole,
)

logger = logging.getLogger(__name__)


class AiModelBaseAdapter(ModelProvider):
    """Adapts ``AiModelBase`` (signal-driven) to the ``ModelProvider``
    protocol (iterator-based).

    Uses a local event queue and ``QCoreApplication.processEvents()``
    to pump the Qt event loop while waiting for signals. This must be
    called from a thread that has a running Qt event dispatcher (the
    AgentLoop QThread satisfies this).
    """

    def __init__(self, model: AiModelBase):
        self._model = model

    def stream(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> Iterator[StreamEvent]:

        event_queue: queue.Queue = queue.Queue()
        finished_flag = [False]
        has_tool_calls = [False]

        def _on_response(response: AiResponse):
            if response.reasoning:
                event_queue.put(ReasoningDelta(text=response.reasoning))
            if response.message:
                event_queue.put(ContentDelta(text=response.message))
            if response.tool_calls:
                has_tool_calls[0] = True
                for tc in response.tool_calls:
                    func = tc.get("function", {})
                    event_queue.put(ToolCallDelta(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments_delta=func.get("arguments", ""),
                    ))

        def _on_finished():
            finished_flag[0] = True

        self._model.responseAvailable.connect(_on_response)
        self._model.finished.connect(_on_finished)

        try:
            # Build history from messages
            self._model.clear()
            self._build_history(messages)

            # Build parameters
            params = AiParameters()
            params.sys_prompt = system_prompt
            params.stream = True
            params.max_tokens = max_tokens
            params.chat_mode = AiChatMode.Agent
            params.continue_only = True
            if tools:
                params.tools = tools
                params.tool_choice = "auto"
            if model:
                params.model = model

            self._model.queryAsync(params)

            # Pump events until finished
            timer = QElapsedTimer()
            timer.start()
            timeout_ms = 300000  # 5 minutes

            while not finished_flag[0] and timer.elapsed() < timeout_ms:
                app = QCoreApplication.instance()
                if app:
                    app.processEvents()
                while not event_queue.empty():
                    yield event_queue.get_nowait()

            # Drain remaining events
            while not event_queue.empty():
                yield event_queue.get_nowait()

            stop_reason = "tool_use" if has_tool_calls[0] else "end_turn"
            yield MessageComplete(stop_reason=stop_reason)

        finally:
            self._model.responseAvailable.disconnect(_on_response)
            self._model.finished.disconnect(_on_finished)

    def count_tokens(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        # Heuristic: ~4 chars per token
        total = 0
        for msg in messages:
            if isinstance(msg, (UserMessage, AssistantMessage)):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        total += len(block.text)
        return total // 4

    def _build_history(self, messages: List[Message]) -> None:
        """Convert agent messages to AiModelBase history."""
        for msg in messages:
            if isinstance(msg, UserMessage):
                text_parts = []
                tool_results = []
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolResultBlock):
                        tool_results.append(block)

                if tool_results:
                    for tr in tool_results:
                        self._model.addHistory(
                            AiRole.Tool,
                            tr.content,
                            description=tr.tool_use_id,
                        )
                if text_parts:
                    self._model.addHistory(
                        AiRole.User, "\n".join(text_parts))

            elif isinstance(msg, AssistantMessage):
                text_parts = []
                tool_calls = []
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": str(block.input),
                            },
                        })

                kwargs = {}
                if tool_calls:
                    kwargs["toolCalls"] = tool_calls
                self._model.addHistory(
                    AiRole.Assistant,
                    "\n".join(text_parts) if text_parts else None,
                    **kwargs,
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_aimodel_adapter.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/aimodel_adapter.py tests/test_agent_aimodel_adapter.py
git commit -m "Add AiModelBaseAdapter: bridge AiModelBase to ModelProvider"
```

---

### Task 9: Package exports in `__init__.py`

**Files:**
- Modify: `qgitc/agent/__init__.py`

- [ ] **Step 1: Update package exports**

Edit `qgitc/agent/__init__.py`:

```python
# -*- coding: utf-8 -*-
from qgitc.agent.agent_loop import AgentLoop
from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.compaction import CompactionResult, ConversationCompactor
from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionBehavior,
    PermissionDeny,
    PermissionEngine,
    PermissionRule,
    PermissionUpdate,
)
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    StreamEvent,
    ToolCallDelta,
)
from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import (
    AssistantMessage,
    ContentBlock,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UserMessage,
)

__all__ = [
    "AgentLoop",
    "AiModelBaseAdapter",
    "AssistantMessage",
    "CompactionResult",
    "ContentBlock",
    "ContentDelta",
    "ConversationCompactor",
    "Message",
    "MessageComplete",
    "ModelProvider",
    "PermissionAllow",
    "PermissionAsk",
    "PermissionBehavior",
    "PermissionDeny",
    "PermissionEngine",
    "PermissionRule",
    "PermissionUpdate",
    "ReasoningDelta",
    "StreamEvent",
    "SystemMessage",
    "TextBlock",
    "ThinkingBlock",
    "Tool",
    "ToolCallDelta",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "ToolResultBlock",
    "ToolUseBlock",
    "Usage",
    "UserMessage",
]
```

- [ ] **Step 2: Run all agent tests to verify nothing broke**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_types.py tests/test_agent_tool.py tests/test_agent_tool_registry.py tests/test_agent_provider.py tests/test_agent_permissions.py tests/test_agent_compaction.py tests/test_agent_loop.py tests/test_agent_aimodel_adapter.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/__init__.py
git commit -m "Add public exports for agent package"
```

---

### Task 10: Migrate first tool — git_status

**Files:**
- Create: `qgitc/agent/tools/__init__.py`
- Create: `qgitc/agent/tools/git_status.py`
- Create: `tests/test_agent_tools_git_status.py`

This demonstrates the migration pattern. Each existing tool handler from `agenttoolexecutor.py` becomes a `Tool` subclass in `agent/tools/`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_tools_git_status.py`:

```python
# -*- coding: utf-8 -*-
import os
import unittest

from qgitc.agent.tool import ToolContext
from qgitc.agent.tools.git_status import GitStatusTool


class TestGitStatusTool(unittest.TestCase):

    def test_name_and_description(self):
        tool = GitStatusTool()
        self.assertEqual(tool.name, "git_status")
        self.assertIn("status", tool.description.lower())

    def test_is_read_only(self):
        tool = GitStatusTool()
        self.assertTrue(tool.is_read_only())

    def test_input_schema(self):
        tool = GitStatusTool()
        schema = tool.input_schema()
        self.assertEqual(schema["type"], "object")

    def test_openai_schema_format(self):
        tool = GitStatusTool()
        schema = tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "git_status")

    def test_execute_in_git_repo(self):
        tool = GitStatusTool()
        # Use the current working directory (should be a git repo in tests)
        ctx = ToolContext(
            working_directory=os.getcwd(),
            abort_requested=lambda: False,
        )
        result = tool.execute({}, ctx)
        self.assertFalse(result.is_error)
        # Should contain branch info from porcelain -b output
        self.assertIsInstance(result.content, str)

    def test_execute_in_nonexistent_dir(self):
        tool = GitStatusTool()
        ctx = ToolContext(
            working_directory="/nonexistent/path/xyz",
            abort_requested=lambda: False,
        )
        result = tool.execute({}, ctx)
        self.assertTrue(result.is_error)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_tools_git_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qgitc.agent.tools'`

- [ ] **Step 3: Create the tools subpackage and git_status tool**

Create `qgitc/agent/tools/__init__.py`:

```python
# -*- coding: utf-8 -*-
```

Create `qgitc/agent/tools/git_status.py`:

```python
# -*- coding: utf-8 -*-
import subprocess
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show the working tree status including branch info"

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any],
                context: ToolContext) -> ToolResult:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "-b"],
                cwd=context.working_directory,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return ToolResult(
                    content=result.stderr.strip() or "git status failed",
                    is_error=True,
                )
            return ToolResult(content=result.stdout)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd F:/Projects/qgitc && python -m pytest tests/test_agent_tools_git_status.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd F:/Projects/qgitc
git add qgitc/agent/tools/__init__.py qgitc/agent/tools/git_status.py tests/test_agent_tools_git_status.py
git commit -m "Add GitStatusTool: first agent tool migration"
```
