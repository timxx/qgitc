# Agent Framework Design

## Overview

A standalone, pluggable agent framework for qgitc that provides a complete LLM agent
loop with tool execution, permission management, and conversation compaction. Adapted
for Qt's event loop and signal/slot paradigm.

The agent runs as a pluggable backend for the existing chat UI (`AiChatWidget`),
decoupling orchestration logic from the UI layer. It is also usable headless for
testing and scripting.

## Goals

- **Standalone**: The agent package has no dependency on UI code
- **Pluggable**: New tools, providers, and permission rules can be added without modifying core code
- **Qt-native**: Uses QThread for the agent loop, Qt signals for communication
- **Incremental**: Each component is buildable and testable independently; existing code coexists during migration
- **Minimal disruption**: Existing `AiModelBase`, `AiChatWidget`, and tool classes remain untouched

## Non-Goals

- Cost tracking / budget enforcement (not needed for desktop app)
- Memory system (out of scope for initial implementation)
- Microcompaction (time-gap based clearing — less relevant for desktop sessions)
- Replacing `AiChatWidget` inline orchestration (future integration work)

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    AgentLoop (QThread)                │
│                                                      │
│  submit(prompt) ─────────────────────────────────┐   │
│                                                  │   │
│  ┌─────────┐    ┌──────────┐    ┌─────────────┐ │   │
│  │Compactor│───>│ Provider │───>│ Tool Exec   │ │   │
│  │         │    │ .stream()│    │ (parallel)  │ │   │
│  └─────────┘    └──────────┘    └──────┬──────┘ │   │
│                                        │        │   │
│                                 ┌──────▼──────┐ │   │
│                                 │ Permission  │ │   │
│                                 │ Engine      │ │   │
│                                 └─────────────┘ │   │
│                                                  │   │
│  ◄── signals: textDelta, toolCallStart, etc. ────┘   │
└──────────────────────────────────────────────────────┘
         │ signals (auto-marshaled to main thread)
         ▼
┌──────────────────┐
│  UI / Consumer   │
│  (AiChatWidget)  │
└──────────────────┘
```

---

## Component Design

### 1. Message Types & Events (`agent/types.py`)

Foundation data types used throughout the agent package.

**Message types:**

| Type | Fields | Purpose |
|------|--------|---------|
| `UserMessage` | uuid, timestamp, content: list[ContentBlock] | User input + tool results |
| `AssistantMessage` | uuid, timestamp, content: list[ContentBlock], model, stop_reason, usage | LLM response |
| `SystemMessage` | uuid, subtype, content, compact_metadata | Compaction boundaries |

`Message` is a union of these three.

**Content blocks:**

| Type | Fields | Purpose |
|------|--------|---------|
| `TextBlock` | text: str | Plain text content |
| `ToolUseBlock` | id: str, name: str, input: dict | Tool call request from LLM |
| `ToolResultBlock` | tool_use_id: str, content: str, is_error: bool | Tool execution result |
| `ThinkingBlock` | thinking: str | Extended thinking/reasoning |

**Usage:**

| Field | Type |
|-------|------|
| input_tokens | int |
| output_tokens | int |
| cache_creation_input_tokens | int |
| cache_read_input_tokens | int |

All types are dataclasses. The existing `AiChatMessage`/`AiResponse` in `llm.py` remain
unchanged; conversion happens at the adapter boundary.

### 2. Tool ABC & ToolRegistry (`agent/tool.py`, `agent/tool_registry.py`)

**`Tool` abstract base class:**

```python
class Tool(ABC):
    name: str                  # unique identifier (e.g., "git_status")
    description: str           # human-readable, used in LLM schema

    def is_read_only(self) -> bool:       # default: False
    def is_destructive(self) -> bool:     # default: False

    @abstractmethod
    def execute(self, input_data: dict, context: ToolContext) -> ToolResult: ...

    @abstractmethod
    def input_schema(self) -> dict: ...   # JSON schema for parameters
```

- `execute()` is synchronous — runs in QThread or ThreadPoolExecutor
- No async, no `prompt()` method — system prompt assembly is the agent loop's job
- `is_read_only()` determines if the tool can run in parallel with others

**`ToolResult`:**

```python
@dataclass
class ToolResult:
    content: str
    is_error: bool = False
```

**`ToolContext`:**

```python
@dataclass
class ToolContext:
    working_directory: str
    abort_requested: Callable[[], bool]   # check if abort was signaled
```

**`ToolRegistry`:**

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None
    def unregister(self, name: str) -> None
    def get(self, name: str) -> Tool | None
    def list_tools(self) -> list[Tool]
    def get_tool_schemas(self) -> list[dict]   # OpenAI function-call format
```

**Migration:** Existing 21 tools in `AgentToolExecutor` are wrapped into `Tool` subclasses
one at a time, each in `agent/tools/<name>.py`. The old `AgentToolRegistry`/`AgentToolExecutor`
coexist until migration is complete.

### 3. ModelProvider Protocol (`agent/provider.py`)

**`ModelProvider` abstract base class:**

```python
class ModelProvider(ABC):
    @abstractmethod
    def stream(self, messages, system_prompt, tools, ...) -> Iterator[StreamEvent]: ...

    @abstractmethod
    def count_tokens(self, messages, system_prompt, tools) -> int: ...
```

**`StreamEvent` types:**

| Type | Fields | Purpose |
|------|--------|---------|
| `ContentDelta` | text: str | Streaming text chunk |
| `ReasoningDelta` | text: str | Streaming reasoning chunk |
| `ToolCallDelta` | id: str, name: str, arguments_delta: str | Incremental tool call JSON |
| `MessageComplete` | stop_reason: str, usage: Usage | End of LLM response |

- Synchronous `Iterator` (not async) — runs inside the agent's QThread where blocking is fine
- 4 event types — no `ContentBlockStart/Stop` granularity needed

**`AiModelBaseAdapter`** (`agent/aimodel_adapter.py`):

Wraps existing `AiModelBase` to satisfy `ModelProvider`:
- Calls `queryAsync()` on the underlying model
- Uses a `QEventLoop` inside the QThread to wait for `responseAvailable`/`finished` signals
- Converts `AiResponse` signals into `StreamEvent` yields
- Handles `requestInterruption()` for abort
- This is the only place where old and new systems touch

### 4. Permission Engine (`agent/permissions.py`)

**`PermissionResult` union:**

| Type | Fields | Purpose |
|------|--------|---------|
| `PermissionAllow` | updated_input: dict (optional) | Proceed with execution |
| `PermissionAsk` | message: str | Needs user confirmation |
| `PermissionDeny` | message: str | Blocked |

**`PermissionRule`:**

```python
@dataclass
class PermissionRule:
    tool_name: str                    # tool name or "*" wildcard
    behavior: PermissionBehavior      # ALLOW, ASK, DENY
    pattern: str | None = None        # optional content match
```

**`PermissionEngine`:**

```python
class PermissionEngine:
    def __init__(self, allow_rules, ask_rules, deny_rules): ...

    def check(self, tool: Tool, input_data: dict) -> PermissionResult:
        # 4-step pipeline:
        # 1. Deny rules match? -> Deny
        # 2. Allow rules match? -> Allow
        # 3. Tool is read-only? -> Allow
        # 4. Otherwise -> Ask

    def apply_update(self, update: PermissionUpdate) -> None:
        # Add/remove rules at runtime (e.g., "always allow this tool")

class PermissionUpdate:
    action: Literal["add", "remove"]   # add or remove a rule
    rule: PermissionRule               # the rule to add/remove
```

No bypass mode, no bypass-immune checks — in a desktop app the user is always present.
Runtime rule updates let the UI persist "always allow" choices for the session.

### 5. Conversation Compaction (`agent/compaction.py`)

**`ConversationCompactor`:**

```python
class ConversationCompactor:
    def __init__(self, provider: ModelProvider,
                 context_window: int,
                 max_output_tokens: int): ...

    def should_compact(self, messages: list[Message]) -> bool:
        # Heuristic: ~4 chars per token
        # Trigger when estimated > context_window - max_output_tokens - buffer

    def compact(self, messages: list[Message]) -> CompactionResult:
        # 1. Build summarization prompt from message history
        # 2. Call provider.stream() (no tools, no system prompt)
        # 3. If too long, truncate oldest messages and retry once
        # 4. Return boundary marker + summary
```

**`CompactionResult`:**

```python
@dataclass
class CompactionResult:
    boundary: SystemMessage       # marks where compaction happened
    summary: UserMessage          # condensed conversation
    pre_token_estimate: int
    post_token_estimate: int
```

Runs synchronously in the agent's QThread. Uses the same `ModelProvider` — no special
LLM plumbing needed.

### 6. AgentLoop (`agent/agent_loop.py`)

The core orchestrator. A `QThread` subclass with a sequential run loop and signal-based
output.

**Signals:**

| Signal | Arguments | Purpose |
|--------|-----------|---------|
| `textDelta` | str | Streaming text chunk |
| `reasoningDelta` | str | Streaming reasoning chunk |
| `toolCallStart` | str, str, dict | tool_call_id, name, input |
| `toolCallResult` | str, str, bool | tool_call_id, content, is_error |
| `turnComplete` | object (AssistantMessage) | Full LLM turn done |
| `agentFinished` | — | Agent loop ended |
| `conversationCompacted` | int, int | pre/post token estimates |
| `permissionRequired` | str, object, dict | tool_call_id, Tool, input |
| `errorOccurred` | str | Error description |

**Public API** (called from main thread):

```python
class AgentLoop(QThread):
    def submit(self, prompt: str, context_blocks: list = None) -> None
    def approve_tool(self, tool_call_id: str) -> None
    def deny_tool(self, tool_call_id: str, message: str = "") -> None
    def abort(self) -> None
    def messages(self) -> list[Message]   # thread-safe copy
```

**Internal `run()` flow:**

```
1. Check compaction -> compact if needed
2. Call provider.stream(messages, tools, system_prompt)
3. Process StreamEvents:
   - ContentDelta -> emit textDelta
   - ReasoningDelta -> emit reasoningDelta
   - ToolCallDelta -> accumulate
   - MessageComplete -> build AssistantMessage, emit turnComplete
4. If stop_reason == "tool_use":
   a. For each ToolUseBlock:
      - permission_engine.check()
      - Allow -> execute tool (ThreadPool for read-only, sequential otherwise)
      - Ask -> emit permissionRequired, block on QWaitCondition
      - Deny -> create error ToolResult
   b. Emit toolCallStart/toolCallResult for each
   c. Append tool results as UserMessage
   d. Loop back to step 1
5. If stop_reason == "end_turn" -> emit agentFinished
```

**Threading details:**
- `run()` executes in its own thread
- Signals auto-marshal to main thread (Qt cross-thread signal delivery)
- `approve_tool()`/`deny_tool()` from main thread set a `QWaitCondition`
- `abort()` sets a flag checked at each loop iteration
- Tool execution: sequential by default, `QThreadPool` for parallel read-only tools

**Lifecycle:**
- `submit()` can be called multiple times for multi-turn conversation
- Thread runs for one agent turn (prompt -> all LLM rounds -> final response), then finishes
- Next `submit()` starts a new run with accumulated message history

---

## Module Structure

```
qgitc/agent/
├── __init__.py              # public exports
├── types.py                 # Message, ContentBlock, ToolResult, ToolContext, Usage
├── tool.py                  # Tool ABC
├── tool_registry.py         # ToolRegistry
├── provider.py              # ModelProvider ABC, StreamEvent types (ContentDelta, etc.)
├── aimodel_adapter.py       # AiModelBaseAdapter (wraps AiModelBase)
├── permissions.py           # PermissionRule, PermissionEngine, PermissionResult
├── compaction.py            # ConversationCompactor
├── agent_loop.py            # AgentLoop (QThread)
└── tools/                   # Tool implementations (one per file)
    ├── __init__.py
    ├── git_status.py
    ├── git_log.py
    ├── read_file.py
    └── ...
```

## Integration Strategy

The agent package is the deliverable. UI integration is future work:

1. Build the agent package independently (fully testable without UI)
2. Later: add integration layer in `AiChatWidget` that creates an `AgentLoop`, connects
   signals to existing UI methods
3. Later: gradually remove inline orchestration from `AiChatWidget`
4. Later: refactor `AiChatMessage`/`AiResponse` to use agent types

**What stays unchanged:**
- `AiModelBase` / `GithubCopilot` / `LocalLLM` — adapter wraps them
- `AiChatWidget` / `AiChatBot` — untouched until integration phase
- `AiChatContextProvider` — context passed as text to `submit()`
- `agenttools.py` / `agentmachine.py` / `agenttoolexecutor.py` — coexist during migration

## Implementation Order

Each step produces a buildable, testable commit:

1. `agent/types.py` — message types, content blocks, stream events
2. `agent/tool.py` + `agent/tool_registry.py` — Tool ABC and registry
3. `agent/provider.py` — ModelProvider ABC and stream event types
4. `agent/permissions.py` — permission engine
5. `agent/compaction.py` — conversation compactor
6. `agent/agent_loop.py` — the core agent loop
7. `agent/aimodel_adapter.py` — AiModelBase adapter
8. `agent/tools/` — migrate existing tools one by one
9. Tests for each component
