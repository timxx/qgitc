# Slash Commands Design

**Date:** 2026-04-16  
**Status:** Draft — awaiting review  
**Scope:** Add slash command support to AI chat input for quick skill invocation

---

## Overview

Turn skills into slash commands accessible via `/` prefix in the chat input box. When user types `/`, a non-blocking popup appears showing matching skills filtered in real-time. On selection, the skill is sent as a prompt through the normal agent loop.

## Goals

1. **Discoverability** — users can see available skills without leaving the input
2. **Non-blocking** — popup never interrupts typing; filters dynamically as input changes
3. **Consistency** — use same skill execution path as normal prompts (through agent loop)
4. **Minimal changes** — surgical edits to existing code, no broad refactors

## Architecture

### 1. CommandRegistry (`qgitc/agent/slash_commands.py`)

**Purpose:** Registry of slash commands indexed by name and alias.

**Key Types:**
- `SlashCommand` protocol: `name`, `description`, `aliases` (List[str]), `argument_hint` (Optional[str])
- `CommandRegistry` class:
  - `register(command: SlashCommand)` — register a command
  - `find(name: str) -> Optional[SlashCommand]` — lookup by name or alias
  - `has(name: str) -> bool` — check existence
  - `list_commands() -> List[SlashCommand]` — get all commands

**Design Decision:** Keep simple; no hidden commands initially. Only user-invocable skills are registered.

### 2. SlashCommandPopup (`qgitc/slash_command_popup.py`)

**Purpose:** Non-blocking popup widget showing filtered commands.

**Behavior:**
- Positioned below the input box, within the input widget's bounding area
- Shows up to 8 commands (configurable)
- No selection highlight initially; highlight on hover or keyboard navigation
- Filters commands by prefix match on name (case-insensitive, fuzzy not required)
- Updates in real-time as input text changes
- Can be dismissed by:
  - Pressing Escape
  - Clicking elsewhere
  - Losing focus on input

**Key Methods:**
- `setCommands(commands: List[SlashCommand])` — set filtered list
- `setVisible(visible: bool)` — show/hide
- `selectedCommand() -> Optional[SlashCommand]` — get highlighted command
- `selectPrevious() / selectNext()` — keyboard navigation
- `selectedCommand: Signal[SlashCommand]` — emitted when user selects

**Implementation:** Custom QWidget with QListWidget-like behavior, minimal dependencies.

### 3. AiChatEdit Integration (`qgitc/aichatedit.py`)

**Purpose:** Detect `/` input and manage popup visibility.

**Changes:**
- Add `_commandRegistry: Optional[CommandRegistry]`
- Add `_slashCommandPopup: Optional[SlashCommandPopup]`
- Monitor `textChanged` signal to detect `/` prefix
- When text is `/` or `/prefix`:
  - Show popup with matching commands
  - Filter by text after `/` (excluding space)
- When user presses Up/Down, forward to popup for navigation
- When popup emits `selectedCommand`, replace input text with `/command-name `
- When user presses Escape, hide popup
- When text no longer starts with `/`, hide popup

**Key Methods:**
- `setCommandRegistry(registry: CommandRegistry)` — connect registry
- `_updateSlashCommandPopup()` — filter and show/hide popup based on current text
- Event handlers for key navigation

### 4. AiChatWidget Integration (`qgitc/aichatwidget.py`)

**Purpose:** Parse and execute slash commands.

**Changes:**
- Create and populate `CommandRegistry` from `SkillRegistry`
  - For each **user-invocable** skill (where `skill.user_invocable == True`):
    - Create a command wrapper with name, description, aliases, argument_hint
    - Register in CommandRegistry
  - Skip non-invocable skills (they never appear in popup)
- Pass registry to `AiChatEdit`
- In `_doRequest()`, detect if prompt starts with `/`
  - Parse: extract command name and args
  - Look up skill in registry
  - If found:
    - Get skill content
    - Substitute `$ARGUMENTS` with args (or append if not present)
    - Clear the input
    - Send substituted content as prompt through normal flow
  - If not found: treat as normal prompt

**Key Methods:**
- `_buildCommandRegistry() -> CommandRegistry` — populate from skills
- `_parseSlashCommand(text: str) -> Tuple[str, str]` — extract name and args
- `_executeSlashCommand(name: str, args: str) -> bool` — execute and return success

### 5. Command Execution Flow

```
User types "/" → AiChatEdit shows popup with all skills
                ↓
User types "he" → Popup filters to matching skills (e.g., "help")
                ↓
User presses Down or clicks → Command highlighted
                ↓
User presses Enter or clicks → Text replaced with "/skill-name ", focus stays in input
                ↓
User types args → Text becomes "/skill-name arg1 arg2..."
                ↓
User presses Enter → _doRequest() is called
                ↓
AiChatWidget._doRequest() detects "/" prefix
                ↓
Parse command name "skill-name", args "arg1 arg2..."
                ↓
Look up skill from SkillRegistry
                ↓
Substitute $ARGUMENTS in skill content with "arg1 arg2..."
                ↓
Send substituted text as normal prompt through agent loop
                ↓
Agent processes normally (tools may execute, etc.)
```

## Data Model

**Skill → Command Mapping:**

Only **user-invocable skills** are registered as commands (filtered by `skill.user_invocable == True`).

Each invocable skill from `SkillRegistry` becomes a command:

```python
Command(
    name=skill.name,
    description=skill.description,
    aliases=skill.aliases or [],
    argument_hint=skill.argument_hint or None,
)
```

**Filtering Logic:**
- `CommandRegistry.list_commands()` returns only registered commands (i.e., `user_invocable == True`)
- Skills with `user_invocable == False` are never registered and never appear in popup

## Error Handling

- **Unknown command:** Treat as normal text, send as-is to agent
- **Argument substitution fails:** Skip substitution, send skill content with args appended
- **Skill not found at execution time:** Show error message, don't send

## Testing

**Unit Tests** (`tests/test_slash_commands.py`):
- CommandRegistry: register, find, has, list operations
- Command execution: parsing, argument substitution
- Popup filtering: prefix matching, empty input

**Integration Tests** (`tests/test_aichat_slash_commands.py`):
- Typing `/` shows popup
- Typing characters filters popup
- Selecting command replaces text
- Pressing Escape hides popup
- Sending `/command` executes skill

## Out of Scope

- Aliases editing
- Non-invocable commands (only `user_invocable == True` skills are registered)
- Custom commands (only skills)
- Fuzzy matching (prefix match only)
- Command history

---

## Implementation Phases

**Phase 1:** CommandRegistry + SlashCommandPopup (tests pass)  
**Phase 2:** AiChatEdit integration (popup shows/hides)  
**Phase 3:** AiChatWidget integration (commands execute)  
**Phase 4:** Integration tests  

Each phase is committed separately with a focused commit message.
