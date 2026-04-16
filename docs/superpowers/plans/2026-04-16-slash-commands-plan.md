# Slash Commands Implementation Plan

**Date:** 2026-04-16  
**Spec Reference:** [2026-04-16-slash-commands-design.md](../specs/2026-04-16-slash-commands-design.md)  
**Phases:** 4 (sequential, with builds/tests after each)

---

## Phase 1: CommandRegistry + SlashCommandPopup Foundation

**Goal:** Create core registry and popup widget with unit tests passing.  
**Duration:** ~2 hours  
**Commits:** 2

### Phase 1A: CommandRegistry

**Files to create:**
- `qgitc/agent/slash_commands.py` — registry + SlashCommand protocol

**Implementation:**

```python
from typing import List, Optional, Protocol

class SlashCommand(Protocol):
    """Protocol for slash commands."""
    name: str
    description: str
    aliases: List[str]
    argument_hint: Optional[str]

class CommandRegistry:
    """Registry of slash commands indexed by name and alias."""
    
    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}
        self._aliases: dict[str, str] = {}
    
    def register(self, command: SlashCommand) -> None:
        """Register a slash command by name and all its aliases."""
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name
    
    def find(self, name: str) -> Optional[SlashCommand]:
        """Look up a command by name or alias. Returns None if not found."""
        cmd = self._commands.get(name)
        if cmd is not None:
            return cmd
        canonical = self._aliases.get(name)
        if canonical is not None:
            return self._commands.get(canonical)
        return None
    
    def has(self, name: str) -> bool:
        """Check if a command is registered (by name or alias)."""
        return self.find(name) is not None
    
    def list_commands(self) -> List[SlashCommand]:
        """Return all commands in insertion order."""
        return list(self._commands.values())
```

**Tests** (`tests/test_slash_commands.py`):
- `test_register_command()` — register and list
- `test_find_by_name()` — lookup by name
- `test_find_by_alias()` — lookup by alias
- `test_has()` — existence check
- `test_register_multiple_aliases()` — single command with multiple aliases

**Commit Message:**
```
feat: Add CommandRegistry for slash commands

- Create SlashCommand protocol (name, description, aliases, argument_hint)
- Implement CommandRegistry for registration and lookup
- Support name + alias-based lookups
- Add unit tests for all registry operations
```

### Phase 1B: SlashCommandPopup Widget

**Files to create:**
- `qgitc/slash_command_popup.py` — popup UI widget

**Implementation:**

```python
from typing import List, Optional
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QWidget
from qgitc.agent.slash_commands import SlashCommand

class SlashCommandPopup(QWidget):
    """Non-blocking popup for slash command suggestions."""
    
    selectedCommand = Signal(SlashCommand)  # Emitted when user selects
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self._list = QListWidget(self)
        self._list.itemClicked.connect(self._onItemClicked)
        self._list.itemDoubleClicked.connect(self._onItemClicked)
        self._list.setMaximumHeight(8 * 24)  # ~8 items max
        self._list.setFocusProxy(self.parentWidget())
        
        self._currentCommand = None  # type: Optional[SlashCommand]
        self._commands = []  # type: List[SlashCommand]
    
    def setCommands(self, commands: List[SlashCommand]) -> None:
        """Update the popup with filtered commands."""
        self._commands = commands
        self._list.clear()
        self._currentCommand = None
        
        for cmd in commands:
            # Display: /name — description
            display_text = f"/{cmd.name}"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, cmd.name)
            item.setToolTip(cmd.description)
            self._list.addItem(item)
    
    def selectedCommand(self) -> Optional[SlashCommand]:
        """Get the currently highlighted command."""
        return self._currentCommand
    
    def selectNext(self) -> None:
        """Highlight next command."""
        current = self._list.currentRow()
        if current < len(self._commands) - 1:
            self._list.setCurrentRow(current + 1)
            self._updateCurrentCommand()
    
    def selectPrevious(self) -> None:
        """Highlight previous command."""
        current = self._list.currentRow()
        if current > 0:
            self._list.setCurrentRow(current - 1)
            self._updateCurrentCommand()
    
    def _updateCurrentCommand(self) -> None:
        """Update _currentCommand based on current selection."""
        row = self._list.currentRow()
        if 0 <= row < len(self._commands):
            self._currentCommand = self._commands[row]
    
    def _onItemClicked(self, item: QListWidgetItem) -> None:
        """Handle item click."""
        name = item.data(Qt.UserRole)
        cmd = next((c for c in self._commands if c.name == name), None)
        if cmd:
            self._currentCommand = cmd
            self.selectedCommand.emit(cmd)
    
    def showAt(self, pos: QPoint) -> None:
        """Show popup at the given position."""
        self.move(pos)
        self.show()
```

**Tests** (`tests/test_slash_commands.py` — add to existing):
- `test_popup_set_commands()` — populate list
- `test_popup_select_next()` — navigate down
- `test_popup_select_previous()` — navigate up
- `test_popup_item_selected_signal()` — emit on click
- `test_popup_max_height()` — respect 8-item limit

**Commit Message:**
```
feat: Add SlashCommandPopup widget

- Create non-blocking QWidget-based popup for command suggestions
- Display commands with name and description tooltip
- Support keyboard navigation (next/previous)
- Emit selectedCommand signal on user selection
- Add tests for popup filtering and selection
```

**After Phase 1:**
- Build: `python setup.py build`
- Tests: `python -m unittest discover -s tests -p "test_slash_commands.py" -v`
- Verify: No errors, 10+ tests passing

---

## Phase 2: AiChatEdit Integration

**Goal:** Detect `/` input and show/hide popup with real-time filtering.  
**Duration:** ~1.5 hours  
**Files to modify:** `qgitc/aichatedit.py`  
**Commits:** 1

### Phase 2: Integrate Popup into AiChatEdit

**Changes to `qgitc/aichatedit.py`:**

1. **Add imports:**
```python
from typing import Optional
from qgitc.agent.slash_commands import CommandRegistry
from qgitc.slash_command_popup import SlashCommandPopup
```

2. **Add instance variables in `__init__`:**
```python
self._commandRegistry = None  # type: Optional[CommandRegistry]
self._slashCommandPopup = None  # type: Optional[SlashCommandPopup]
self._isHandlingSlashCommand = False
```

3. **Add public method to set registry:**
```python
def setCommandRegistry(self, registry: CommandRegistry) -> None:
    """Connect slash command registry."""
    self._commandRegistry = registry
```

4. **Add popup management methods:**
```python
def _ensureSlashCommandPopup(self) -> SlashCommandPopup:
    """Lazily create the popup widget."""
    if self._slashCommandPopup is None:
        self._slashCommandPopup = SlashCommandPopup(self)
        self._slashCommandPopup.selectedCommand.connect(self._onSlashCommandSelected)
    return self._slashCommandPopup

def _updateSlashCommandPopup(self) -> None:
    """Show/hide/filter popup based on current text."""
    if self._commandRegistry is None:
        return
    
    text = self.toPlainText().strip()
    
    # Hide popup if text doesn't start with /
    if not text.startswith("/"):
        if self._slashCommandPopup:
            self._slashCommandPopup.hide()
        return
    
    # Extract the part after "/"
    after_slash = text[1:]
    
    # Hide popup if there's a space (user is typing args)
    if " " in after_slash:
        if self._slashCommandPopup:
            self._slashCommandPopup.hide()
        return
    
    # Filter commands by prefix
    query = after_slash.lower()
    matching = [
        cmd for cmd in self._commandRegistry.list_commands()
        if cmd.name.lower().startswith(query)
    ]
    
    popup = self._ensureSlashCommandPopup()
    if matching:
        popup.setCommands(matching)
        # Position popup below the input
        cursor_rect = self.edit.cursorRect()
        pos = self.edit.mapToGlobal(cursor_rect.bottomLeft())
        popup.showAt(pos)
    else:
        popup.hide()

def _onSlashCommandSelected(self, cmd) -> None:
    """Handle slash command selection from popup."""
    text = self.toPlainText()
    after_slash = text[1:].split()[0] if text.startswith("/") else ""
    
    # Replace selected text with command name + space
    new_text = f"/{cmd.name} "
    self.edit.setPlainText(new_text)
    
    # Move cursor to end
    cur = self.edit.textCursor()
    cur.movePosition(cur.MoveOperation.End)
    self.edit.setTextCursor(cur)
    
    self._slashCommandPopup.hide()
```

5. **Connect textChanged signal to popup update:**
In `__init__`, after `self.edit.textChanged.connect(self.textChanged)`:
```python
self.edit.textChanged.connect(self._updateSlashCommandPopup)
```

6. **Handle Escape key in eventFilter:**
In `eventFilter()`, add handling for Escape to close popup:
```python
if watched == self.edit and event.type() == QEvent.KeyPress:
    if event.key() == Qt.Key_Escape:
        if self._slashCommandPopup and self._slashCommandPopup.isVisible():
            self._slashCommandPopup.hide()
            return True
    elif event.key() in [Qt.Key_Up, Qt.Key_Down]:
        # If popup visible, navigate instead of moving cursor
        if self._slashCommandPopup and self._slashCommandPopup.isVisible():
            if event.key() == Qt.Key_Down:
                self._slashCommandPopup.selectNext()
            else:
                self._slashCommandPopup.selectPrevious()
            return True
```

**Tests** (add to `tests/test_aichat_edit_slash_commands.py`):
- `test_typing_slash_shows_popup()` — typing "/" triggers popup
- `test_typing_args_hides_popup()` — typing space hides popup
- `test_filtering_by_prefix()` — popup filters on input
- `test_escape_hides_popup()` — Escape key dismisses
- `test_selecting_command_replaces_text()` — selection replaces text with `/command `
- `test_up_down_navigation()` — keyboard navigation works

**Commit Message:**
```
feat: Integrate slash command popup into AiChatEdit

- Add CommandRegistry connection via setCommandRegistry()
- Detect "/" prefix and show filtered command popup
- Hide popup when user types space (arguments)
- Support Up/Down keyboard navigation in popup
- Replace text with selected command name + space
- Hide popup on Escape key
- Add integration tests for popup behavior
```

**After Phase 2:**
- Build: `python setup.py build`
- Tests: Run full test suite
- Manual test: Open chat, type "/" → popup appears, type "h" → filters, select → text changes

---

## Phase 3: AiChatWidget Integration (Execution)

**Goal:** Parse and execute slash commands through agent loop.  
**Duration:** ~2 hours  
**Files to modify:** `qgitc/aichatwidget.py`  
**Commits:** 2

### Phase 3A: CommandRegistry Setup

**Changes to `qgitc/aichatwidget.py`:**

1. **Add imports:**
```python
from qgitc.agent.slash_commands import CommandRegistry, SlashCommand
from qgitc.agent.skills.types import SkillDefinition
```

2. **Add instance variable in `__init__`:**
```python
self._slashCommandRegistry = None  # type: Optional[CommandRegistry]
self._contextPanel = None  # type: Optional[AiChatContextPanel]
```

3. **Add method to build registry from skills:**
```python
def _buildCommandRegistry(self) -> CommandRegistry:
    """Build CommandRegistry from SkillRegistry.
    
    Only user-invocable skills are registered.
    """
    registry = CommandRegistry()
    skillRegistry = self._ensureSkillRegistry()
    
    for skill in skillRegistry.list_skills():
        # Skip non-invocable skills
        if not skill.user_invocable:
            continue
        
        # Create a simple command object from skill
        class SkillCommand:
            def __init__(self, skill_def: SkillDefinition):
                self.name = skill_def.name
                self.description = skill_def.description
                self.aliases = skill_def.aliases or []
                self.argument_hint = skill_def.argument_hint
                self.skill_def = skill_def
        
        cmd = SkillCommand(skill)
        registry.register(cmd)
    
    return registry
```

4. **Ensure registry is created and passed to AiChatContextPanel:**
In a suitable place (e.g., when AiChatContextPanel is created or when skills are loaded):
```python
def _ensureSlashCommandRegistry(self) -> CommandRegistry:
    """Lazily create and cache the command registry."""
    if self._slashCommandRegistry is None:
        self._slashCommandRegistry = self._buildCommandRegistry()
    return self._slashCommandRegistry

# In a method that sets up the UI (e.g., after initialize):
contextPanel = ...  # Get the AiChatContextPanel
if contextPanel is not None:
    contextPanel.edit.setCommandRegistry(self._ensureSlashCommandRegistry())
```

**Commit Message:**
```
feat: Build CommandRegistry from SkillRegistry in AiChatWidget

- Add _buildCommandRegistry() to create commands from user-invocable skills
- Filter out skills with user_invocable == False
- Cache registry as _slashCommandRegistry
- Connect registry to AiChatEdit
```

### Phase 3B: Command Parsing and Execution

**Changes to `qgitc/aichatwidget.py`:**

1. **Add parsing and execution methods:**
```python
def _parseSlashCommand(self, text: str) -> tuple[str, str]:
    """Parse /command args into (command_name, args).
    
    Returns ("", "") if text doesn't start with /.
    """
    text = text.strip()
    if not text.startswith("/"):
        return ("", "")
    
    without_slash = text[1:]
    parts = without_slash.split(None, 1)  # Split on first whitespace
    
    command_name = parts[0] if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    
    return (command_name, args)

def _executeSlashCommand(self, commandName: str, args: str) -> bool:
    """Execute a slash command.
    
    Returns True if executed, False otherwise.
    """
    registry = self._ensureSlashCommandRegistry()
    cmd = registry.find(commandName)
    
    if cmd is None:
        # Unknown command, treat as normal text
        return False

    skill_def = cmd.skill_def
    content = skill_def.content
    
    # Substitute $ARGUMENTS
    if args:
        if '$ARGUMENTS' in content:
            content = content.replace('$ARGUMENTS', args)
        else:
            # Append args if no placeholder
            content = content + f"\n\nARGUMENTS: {args}"
    else:
        content = content.replace('$ARGUMENTS', '')
    
    # Send substituted content as a prompt
    self._doRequest(content, self.currentChatMode())
    
    return True
```

2. **Modify `_doRequest()` to handle slash commands:**
In the beginning of `_doRequest()`, before any other processing:
```python
def _doRequest(self, prompt: str, chatMode: AiChatMode, sysPrompt: str = None, collapsed=False):
    # type: (str, AiChatMode, str, bool) -> None
    
    # Check if this is a slash command
    commandName, args = self._parseSlashCommand(prompt)
    if commandName:
        if self._executeSlashCommand(commandName, args):
            # Clear the input after execution
            if self._contextPanel is not None:
                self._contextPanel.clear()
            return
        # If unknown command, treat as normal prompt (fall through)
    
    # ... rest of _doRequest() as before ...
```

**Tests** (add to `tests/test_aichat_slash_commands.py`):
- `test_parse_slash_command_name_only()` — parse "/skill"
- `test_parse_slash_command_with_args()` — parse "/skill arg1 arg2"
- `test_parse_no_slash()` — parse "normal text"
- `test_execute_known_command()` — execute command from registry
- `test_execute_unknown_command()` — unknown command returns False
- `test_argument_substitution()` — $ARGUMENTS replaced
- `test_argument_fallback()` — args appended if no placeholder

**Commit Message:**
```
feat: Add slash command execution in AiChatWidget

- Add _parseSlashCommand(text) to extract command name and args
- Add _executeSlashCommand() to look up skill and substitute arguments
- Modify _doRequest() to detect and execute slash commands
- Skip execution if command not found (treat as normal text)
- Clear input after successful command execution
- Add unit tests for parsing and execution
```

**After Phase 3:**
- Build: `python setup.py build`
- Tests: All phase 3 tests pass
- Manual test: Type `/skill-name args` → executes through agent loop

---

## Phase 4: Integration Testing

**Goal:** End-to-end tests ensuring all components work together.  
**Duration:** ~1 hour  
**Files to create:** `tests/test_aichat_slash_commands_integration.py`  
**Commits:** 1

### Phase 4: Integration Tests

**Test Coverage:**

```python
class TestSlashCommandsIntegration(TestBase):
    """End-to-end tests for slash commands."""
    
    def setUp(self):
        super().setUp()
        self.widget = AiChatWidget(parent=None)
        # ... setup skills, models, etc. ...
    
    def test_slash_command_e2e_shows_popup_execute_skill(self):
        """Type /skill, execute, verify skill runs."""
        # Type "/" → popup shows
        # Type "he" → filters
        # Press Enter → command selected
        # Verify text replaced
        # Type args, press Enter
        # Verify skill executed through agent loop
    
    def test_slash_command_with_arguments_substitution(self):
        """Verify $ARGUMENTS substitution works."""
    
    def test_slash_command_unknown_treated_as_normal(self):
        """Unknown /command treated as prompt."""
    
    def test_slash_command_non_invocable_not_shown(self):
        """Non-invocable skills don't appear in popup."""
```

**Commit Message:**
```
test: Add integration tests for slash commands

- Test end-to-end workflow: typing, selection, execution
- Verify argument substitution for skills
- Test unknown commands fallback to normal prompts
- Verify non-invocable skills are filtered out
- All integration tests pass
```

**After Phase 4:**
- Build: `python setup.py build`
- Full test run: `python -m unittest discover -s tests -p "test_slash_commands*.py" -v`
- All tests pass (40+)
- Manual testing: interact through UI

---

## Build & Commit Checklist

### After Each Phase

1. **Python compilation check:**
   ```bash
   python -m py_compile qgitc/agent/slash_commands.py qgitc/slash_command_popup.py qgitc/aichatedit.py qgitc/aichatwidget.py
   ```

2. **Import formatting:**
   ```bash
   python -m isort qgitc/agent/slash_commands.py qgitc/slash_command_popup.py qgitc/aichatedit.py qgitc/aichatwidget.py
   ```

3. **Run tests:**
   ```bash
   python -m unittest discover -s tests -p "test_slash_commands*.py" -v
   ```

4. **Build step:**
   ```bash
   python setup.py build
   ```

5. **Commit with focused message (no Co-Authored-By).**

### Final Verification (End of Phase 4)

```bash
# Full test suite
python -m unittest discover -s tests -p "test_*.py" -v

# Manual: python qgitc.py chat
# - Type "/" → see popup with skills
# - Type skill prefix → filters
# - Select skill → text changes
# - Type args, press Enter → skill executes via agent loop
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Popup blocks input | Non-blocking design; dismisses on space/escape |
| Command conflicts | Registry lookup enforces unique names |
| Broken agent loop | Execute through `_doRequest()` (existing path) |
| Non-invocable skills appear | Filter by `user_invocable` during registration |
| Broken builds | Compile check after each phase |

---

## Success Criteria

✅ **Phase 1:** CommandRegistry + SlashCommandPopup created, 10+ unit tests pass  
✅ **Phase 2:** Popup shows/hides on "/" input, filtering works, 6+ tests pass  
✅ **Phase 3:** Slash commands execute, arguments substituted, 7+ tests pass  
✅ **Phase 4:** End-to-end workflow verified, 40+ total tests pass  
✅ **Final:** Build succeeds, manual UI testing confirms functionality
