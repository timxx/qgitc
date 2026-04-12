# Agent Loop Migration Design

Refactor AiChatWidget to use the new `qgitc/agent/` module (AgentLoop, ToolRegistry,
PermissionEngine) for all chat modes, replacing the old tool orchestration system.

## Goals

- Route all chat modes (Chat, Agent, CodeReview) through AgentLoop
- Replace old tool orchestration (AgentToolMachine, AgentToolExecutor, strategies) with
  AgentLoop + PermissionEngine
- Simplify AiModelBase to use the new message types
- Refactor ResolveConflictJob to own its own AgentLoop
- Remove old modules after migration

## Decisions

1. **UI tools**: Wrap as Tool subclasses using signal + QWaitCondition for cross-thread
   dispatch (registered in ToolRegistry like any other tool)
2. **Permission mapping**: Old strategy settings map to PermissionEngine rule presets via
   factory functions
3. **Chat modes**: All modes go through AgentLoop (CodeReview will be removed in the
   future, replaced by skills)
4. **History ownership**: AgentLoop messages are the source of truth for persistence;
   AiModelBase.history is only used transiently by the adapter
5. **Message types**: AiModelBase simplified to use new message types from agent module
6. **ResolveConflictJob**: Refactored to own its own AgentLoop with AllAuto permissions,
   decoupled from widget internals
7. **Migration strategy**: Bridge & swap (Approach C) — build bridge layers first, swap
   widget, then clean up

## Architecture

### Bridge Layers

#### Message Conversion (`agent/message_convert.py`)

Two-way conversion between AgentLoop message types and history store dict format:

- `messages_to_history_dicts(messages: List[Message]) -> List[Dict]`: Converts
  UserMessage/AssistantMessage/SystemMessage with ContentBlocks to dict format
  (role, content, tool_calls, reasoning, description).
- `history_dicts_to_messages(dicts: List[Dict]) -> List[Message]`: Reverse for loading
  saved conversations.

Preserves backward compatibility with existing saved chat histories.

#### Permission Presets (`agent/permission_presets.py`)

Factory function mapping old strategy setting values to PermissionEngine instances:

- `create_permission_engine(strategy_value: int) -> PermissionEngine`
  - 0 (Default): allow read-only, ask for rest
  - 1 (Aggressive): allow read-only + non-destructive, ask for destructive
  - 2 (Safe): ask for everything
  - 3 (AllAuto): allow everything

#### UI Tool Wrapper (`agent/ui_tool.py`)

- `UiTool(Tool)`: Wraps a context-provider UI tool definition. Its `execute()` emits
  a signal to the main thread and blocks on QWaitCondition until the result arrives.
- `UiToolDispatcher(QObject)`: Lives on the main thread. Receives execution requests,
  calls `provider.executeUiTool()`, posts results back via the condition variable.

AgentLoop calls UI tools like any other tool without knowing about Qt threading.

### Widget Integration

#### AgentLoop Lifecycle

- One AgentLoop per active conversation
- Created fresh when conversation becomes active (not cached); previous loop is stopped
- Loading a saved conversation creates a new AgentLoop and sets its messages via
  `set_messages()` (no re-execution, just history restoration)
- Widget connects to AgentLoop signals for rendering:
  - `textDelta` -> append text to chatbot
  - `reasoningDelta` -> append to reasoning block
  - `toolCallStart` -> display tool call UI
  - `toolCallResult` -> display result (collapsed)
  - `turnComplete` -> save history
  - `agentFinished` -> re-enable input
  - `permissionRequired` -> show confirmation card
  - `errorOccurred` -> display error

#### Request Flow

All modes go through the same path:
1. Widget builds prompt (context injection, system prompt based on mode)
2. Calls `agentLoop.submit(prompt, context_blocks)`
3. AgentLoop handles the full LLM-tool loop autonomously
4. Widget renders signals as they arrive
5. No more `_continueAgentConversation`

#### History Save/Load

- On `turnComplete`/`agentFinished`: `agentLoop.messages()` -> `messages_to_history_dicts()` -> persist
- On load: stored dicts -> `history_dicts_to_messages()` -> `agentLoop.set_messages()`
- AiModelBase.history no longer source of truth

#### Removed from AiChatWidget

- `_agentExecutor` (AgentToolExecutor)
- `_uiToolExecutor` (UiToolExecutor)
- `_toolMachine` (AgentToolMachine)
- `_continueAgentConversation()`
- `_onExecuteTool()`, `_onToolConfirmationNeeded()`, `_onToolExecutionCancelled()`,
  `_onContinueAgent()`
- `_availableOpenAiTools()`
- Strategy creation/handling

### AiModelBase Simplification

- `history` becomes `List[Message]` using agent types
- `addHistory()` creates appropriate message types with content blocks
- `toOpenAiMessages()` converts from new types to OpenAI API format
- `AiResponse` stays unchanged (streaming signal payload, separate concern)
- Provider subclasses unaffected (they work with OpenAI format from toOpenAiMessages)

### AiChatHistoryStore Adaptation

- New method `updateFromMessages(historyId, messages: List[Message])`
- Uses `messages_to_history_dicts()` internally
- Loading unchanged — stored format stays the same

### ResolveConflictJob Refactor

Decoupled from widget internals. Owns its own AgentLoop:
- Creates AgentLoop with AllAuto permissions
- Submits resolve prompt directly
- Listens to `agentFinished`
- Reads `agentLoop.messages()` for final status markers
- Verifies file is conflict-marker-free

No longer accesses widget's `_toolMachine`, `_agentExecutor`, `_doRequest()`, or model signals.

### ToolType at UI Boundary

The new Tool class uses `is_read_only()` and `is_destructive()` booleans.
A helper function at the UI boundary converts to int constants for rendering:
`tool_type_from_tool(tool: Tool) -> int`

### Cleanup — Removed Files

- `qgitc/agenttools.py`
- `qgitc/agenttoolexecutor.py`
- `qgitc/agentmachine.py`
- `qgitc/uitoolexecutor.py`

Updated imports in: `aichatbot.py`, `aitoolconfirmation.py`, `aichatcontextprovider.py`,
`mainwindowcontextprovider.py`, `commitcontextprovider.py`, affected test files.

## Migration Order

### Phase 1: Bridge Layers
1. Add `message_convert.py` with tests
2. Add `permission_presets.py` with tests
3. Add `ui_tool.py` (UiTool + UiToolDispatcher) with tests

### Phase 2: Widget Integration
4. Integrate AgentLoop into AiChatWidget — create loop, connect signals, submit prompts
5. Route all modes through AgentLoop
6. Wire permission UI — permissionRequired to confirmation cards, approve/reject buttons
7. Wire history save/load through AgentLoop messages

### Phase 3: AiModelBase Simplification
8. Switch AiModelBase.history to new message types
9. Update AiChatHistoryStore to work with List[Message]

### Phase 4: ResolveConflictJob
10. Refactor ResolveConflictJob to own its AgentLoop

### Phase 5: Cleanup
11. Remove old modules
12. Update imports across codebase
13. Update/remove affected tests

Steps may merge or split based on actual size. Ordering preserves buildability at each step.
