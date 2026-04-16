# Agent Skills Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lazy-loaded skills support to the agent so the model can choose a skill by name, load full skill content on demand, and run with optional per-skill tool allowlists.

**Architecture:** Introduce a focused skills subsystem (`types/registry/loader/discovery/prompt`) plus a new `Skill` tool. Keep the existing agent loop and permission model intact, and integrate by passing skill context through `ToolContext.extra` and appending a compact skills reminder to the system prompt.

**Tech Stack:** Python 3, PySide6, unittest, dataclasses, PyYAML

---

## File Structure

### New files
- `qgitc/agent/skills/__init__.py`: Public exports for skills subsystem.
- `qgitc/agent/skills/types.py`: `SkillDefinition` dataclass.
- `qgitc/agent/skills/registry.py`: Name/alias lookup and model-visible filtering.
- `qgitc/agent/skills/loader.py`: `SKILL.md` frontmatter parsing and command creation.
- `qgitc/agent/skills/discovery.py`: Load user/project skill directories with project override precedence.
- `qgitc/agent/skills/prompt.py`: Render compact skills reminder text.
- `qgitc/agent/tools/skill.py`: Tool implementation for skill invocation.
- `tests/test_agent_skills_loader.py`: Loader parsing coverage.
- `tests/test_agent_skills_registry.py`: Registry behavior coverage.
- `tests/test_agent_tools_skill.py`: Skill tool behavior coverage.

### Modified files
- `qgitc/agent/tool.py`: Add `extra` field on `ToolContext` for shared runtime state.
- `qgitc/agent/agent_loop.py`: Inject skill registry/state into context, enforce active allowlist, append skill reminder to system prompt.
- `qgitc/agent/tool_registration.py`: Register `SkillTool` in built-in list.
- `qgitc/agent/__init__.py`: Export new skills APIs.
- `qgitc/aichatwidget.py`: Load and pass skill registry in `QueryParams`.
- `tests/test_agent_tool.py`: Add assertions for new `ToolContext.extra` default.
- `tests/test_agent_tool_registration.py`: Assert `Skill` tool registration.
- `tests/test_agent_loop.py`: Add skill invocation and allowlist enforcement tests.
- `pyproject.toml`: Add `PyYAML` dependency.

## Commit and Quality Rules (applies to every task)
- Each commit must be minimal and independently buildable/testable.
- Run tests for changed behavior before committing.
- Generate a concise commit message aligned to the task.
- Commit with regular `git commit -m "..."` only.
- Never add a `Co-authored-by` footer.

### Task 1: Add skills core (types, registry, loader, discovery, prompt)

**Files:**
- Create: `qgitc/agent/skills/__init__.py`
- Create: `qgitc/agent/skills/types.py`
- Create: `qgitc/agent/skills/registry.py`
- Create: `qgitc/agent/skills/loader.py`
- Create: `qgitc/agent/skills/discovery.py`
- Create: `qgitc/agent/skills/prompt.py`
- Create: `tests/test_agent_skills_loader.py`
- Create: `tests/test_agent_skills_registry.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing tests for loader and registry**

```python
# tests/test_agent_skills_registry.py
# -*- coding: utf-8 -*-
import unittest

from qgitc.agent.skills.registry import SkillRegistry
from qgitc.agent.skills.types import SkillDefinition


class TestSkillRegistry(unittest.TestCase):

    def test_lookup_by_name_and_alias(self):
        reg = SkillRegistry()
        reg.register(SkillDefinition(name="review", description="d", content="c", aliases=["rv"]))
        self.assertIsNotNone(reg.get("review"))
        self.assertIsNotNone(reg.get("rv"))

    def test_model_visible_filters_disabled(self):
        reg = SkillRegistry()
        reg.register(SkillDefinition(name="a", description="d", content="c"))
        reg.register(SkillDefinition(name="b", description="d", content="c", disable_model_invocation=True))
        names = [s.name for s in reg.get_model_visible_skills()]
        self.assertEqual(names, ["a"])
```

```python
# tests/test_agent_skills_loader.py
# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from qgitc.agent.skills.loader import load_skills_from_directory


class TestSkillLoader(unittest.TestCase):

    def test_load_skill_from_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "review"
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                """---\nname: review\ndescription: Review code\naliases: [rv]\nallowed-tools: [read_file]\n---\n# body\nDo review\n""",
                encoding="utf-8",
            )
            skills = load_skills_from_directory(str(root))
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "review")
            self.assertEqual(skills[0].aliases, ["rv"])
            self.assertEqual(skills[0].allowed_tools, ["read_file"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_agent_skills_loader tests.test_agent_skills_registry -v`
Expected: FAIL with `ModuleNotFoundError` for `qgitc.agent.skills`.

- [ ] **Step 3: Implement minimal skills core**

```python
# qgitc/agent/skills/types.py
# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class SkillDefinition:
    name: str
    description: str
    content: str
    aliases: List[str] = field(default_factory=list)
    source: str = "projectSettings"
    loaded_from: str = "skills"
    when_to_use: Optional[str] = None
    argument_hint: Optional[str] = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    context: Optional[str] = None
    agent: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    paths: Optional[List[str]] = None
    allowed_tools: List[str] = field(default_factory=list)
    hooks: Optional[dict] = None
    skill_root: Optional[str] = None
```

```python
# qgitc/agent/skills/registry.py
# -*- coding: utf-8 -*-
from typing import Dict, List, Optional

from qgitc.agent.skills.types import SkillDefinition


class SkillRegistry:

    def __init__(self):
        self._skills = {}  # type: Dict[str, SkillDefinition]
        self._aliases = {}  # type: Dict[str, str]

    def register(self, skill):
        # type: (SkillDefinition) -> None
        self._skills[skill.name] = skill
        for alias in skill.aliases:
            self._aliases[alias] = skill.name

    def get(self, name):
        # type: (str) -> Optional[SkillDefinition]
        skill = self._skills.get(name)
        if skill is not None:
            return skill
        real = self._aliases.get(name)
        return self._skills.get(real) if real else None

    def list_skills(self):
        # type: () -> List[SkillDefinition]
        return list(self._skills.values())

    def get_model_visible_skills(self):
        # type: () -> List[SkillDefinition]
        return [s for s in self._skills.values() if not s.disable_model_invocation]
```

```python
# qgitc/agent/skills/loader.py
# -*- coding: utf-8 -*-
import os
import re
from typing import Any, Dict, List, Tuple

import yaml

from qgitc.agent.skills.types import SkillDefinition


def parse_skill_frontmatter(content):
    # type: (str) -> Tuple[Dict[str, Any], str]
    m = re.match(r"\A---\s*\n(.*?)\n?---\s*\n?(.*)", content, re.DOTALL)
    if not m:
        return {}, content
    fm = m.group(1)
    body = m.group(2)
    try:
        data = yaml.safe_load(fm)
        return (data if isinstance(data, dict) else {}), body
    except yaml.YAMLError:
        return {}, content


def load_skills_from_directory(directory):
    # type: (str) -> List[SkillDefinition]
    skills = []  # type: List[SkillDefinition]
    if not os.path.isdir(directory):
        return skills
    for entry in sorted(os.listdir(directory)):
        folder = os.path.join(directory, entry)
        if not os.path.isdir(folder):
            continue
        p = os.path.join(folder, "SKILL.md")
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        fm, body = parse_skill_frontmatter(content)
        skills.append(SkillDefinition(
            name=str(fm.get("name", entry)),
            description=str(fm.get("description", "Skill command")),
            content=body,
            aliases=fm.get("aliases", []) or [],
            when_to_use=fm.get("when_to_use") or fm.get("when-to-use"),
            argument_hint=fm.get("argument_hint") or fm.get("argument-hint"),
            allowed_tools=fm.get("allowed_tools") or fm.get("allowed-tools") or [],
            disable_model_invocation=bool(fm.get("disable_model_invocation") or fm.get("disable-model-invocation")),
            skill_root=folder,
        ))
    return skills
```

```python
# qgitc/agent/skills/discovery.py
# -*- coding: utf-8 -*-
from pathlib import Path

from qgitc.agent.skills.loader import load_skills_from_directory
from qgitc.agent.skills.registry import SkillRegistry


def load_skill_registry(cwd, home_directory=None, additional_directories=None):
    # type: (str, object, object) -> SkillRegistry
    home = Path(home_directory) if home_directory is not None else Path.home()
    reg = SkillRegistry()
    user_dir = home / ".qgitc" / "skills"
    project_dir = Path(cwd) / ".qgitc" / "skills"
    for s in load_skills_from_directory(str(user_dir)):
        s.source = "userSettings"
        reg.register(s)
    for s in load_skills_from_directory(str(project_dir)):
        s.source = "projectSettings"
        reg.register(s)
    for d in additional_directories or []:
        for s in load_skills_from_directory(d):
            reg.register(s)
    return reg
```

```python
# qgitc/agent/skills/prompt.py
# -*- coding: utf-8 -*-


def render_skills_reminder(skills):
    # type: (list) -> str
    if not skills:
        return ""
    lines = ["Available skills:"]
    for s in skills:
        line = "- {}: {}".format(s.name, s.description)
        if s.when_to_use:
            line += " (when: {})".format(s.when_to_use)
        lines.append(line)
    return "\n".join(lines)
```

```toml
# pyproject.toml (dependencies)
"PyYAML>=6.0",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_agent_skills_loader tests.test_agent_skills_registry -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml qgitc/agent/skills tests/test_agent_skills_loader.py tests/test_agent_skills_registry.py
git commit -m "feat(agent): add skills core loading and registry"
```

### Task 2: Add `Skill` tool with lazy content injection

**Files:**
- Create: `qgitc/agent/tools/skill.py`
- Create: `tests/test_agent_tools_skill.py`

- [ ] **Step 1: Write failing tests for skill tool**

```python
# tests/test_agent_tools_skill.py
# -*- coding: utf-8 -*-
import unittest

from qgitc.agent.skills.registry import SkillRegistry
from qgitc.agent.skills.types import SkillDefinition
from qgitc.agent.tools.skill import SkillTool
from qgitc.agent.tool import ToolContext


class TestSkillTool(unittest.TestCase):

    def setUp(self):
        self.registry = SkillRegistry()
        self.registry.register(SkillDefinition(
            name="review",
            description="Review",
            content="Use checklist\n$ARGUMENTS",
            allowed_tools=["read_file"],
        ))
        self.ctx = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={"skill_registry": self.registry},
        )

    def test_invoke_skill_returns_content(self):
        tool = SkillTool()
        result = tool.execute({"skill": "review", "args": "target.py"}, self.ctx)
        self.assertFalse(result.is_error)
        self.assertIn("Use checklist", result.content)
        self.assertIn("target.py", result.content)

    def test_sets_allowed_tools_in_context(self):
        tool = SkillTool()
        _ = tool.execute({"skill": "review"}, self.ctx)
        self.assertEqual(self.ctx.extra.get("tool_allowed_tools"), ["read_file"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_agent_tools_skill -v`
Expected: FAIL with `ModuleNotFoundError` for `qgitc.agent.tools.skill`.

- [ ] **Step 3: Implement `SkillTool` minimally**

```python
# qgitc/agent/tools/skill.py
# -*- coding: utf-8 -*-
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class SkillTool(Tool):
    name = "Skill"
    description = "Execute a named skill and load its instructions"

    def is_read_only(self):
        return True

    def execute(self, input_data, context):
        # type: (Dict[str, Any], ToolContext) -> ToolResult
        skill_name = (input_data.get("skill") or "").strip()
        args = input_data.get("args") or ""
        if skill_name.startswith("/"):
            skill_name = skill_name[1:]
        if not skill_name:
            return ToolResult(content="skill is required", is_error=True)

        reg = context.extra.get("skill_registry") if context.extra else None
        if reg is None:
            return ToolResult(content="No skill registry available", is_error=True)

        skill = reg.get(skill_name)
        if skill is None:
            return ToolResult(content="Unknown skill: {}".format(skill_name), is_error=True)
        if skill.disable_model_invocation:
            return ToolResult(content="Skill {} cannot be model-invoked".format(skill_name), is_error=True)

        text = skill.content
        if args:
            replaced = text.replace("$ARGUMENTS", args)
            if replaced == text:
                text = text + "\n\nARGUMENTS: {}".format(args)
            else:
                text = replaced

        if skill.allowed_tools:
            context.extra["tool_allowed_tools"] = list(skill.allowed_tools)

        return ToolResult(content=text)

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "Skill name"},
                "args": {"type": "string", "description": "Optional skill arguments"},
            },
            "required": ["skill"],
            "additionalProperties": False,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_agent_tools_skill -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/tools/skill.py tests/test_agent_tools_skill.py
git commit -m "feat(agent): add skill invocation tool"
```

### Task 3: Extend `ToolContext` and register `Skill` tool

**Files:**
- Modify: `qgitc/agent/tool.py`
- Modify: `qgitc/agent/tool_registration.py`
- Modify: `tests/test_agent_tool.py`
- Modify: `tests/test_agent_tool_registration.py`

- [ ] **Step 1: Write failing tests for context extra + registration**

```python
# tests/test_agent_tool.py (add)
def test_extra_default_dict(self):
    ctx = ToolContext(working_directory="/tmp", abort_requested=lambda: False)
    self.assertEqual(ctx.extra, {})
```

```python
# tests/test_agent_tool_registration.py (add Skill expected name)
expected_names = [
    # existing names...
    "Skill",
]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_agent_tool tests.test_agent_tool_registration -v`
Expected: FAIL because `ToolContext` has no `extra` and `Skill` not registered.

- [ ] **Step 3: Implement minimal changes**

```python
# qgitc/agent/tool.py (ToolContext)
from dataclasses import dataclass, field

@dataclass
class ToolContext:
    working_directory: str
    abort_requested: Callable[[], bool]
    extra: Dict[str, Any] = field(default_factory=dict)
```

```python
# qgitc/agent/tool_registration.py (imports + builtins)
from qgitc.agent.tools.skill import SkillTool

_BUILTIN_TOOLS = [
    # ...existing tools...
    RunCommandTool,
    SkillTool,
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_agent_tool tests.test_agent_tool_registration -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/tool.py qgitc/agent/tool_registration.py tests/test_agent_tool.py tests/test_agent_tool_registration.py
git commit -m "refactor(agent): add tool context extras and register skill tool"
```

### Task 4: Integrate skills into `AgentLoop` (prompt reminder + allowlist)

**Files:**
- Modify: `qgitc/agent/agent_loop.py`
- Modify: `qgitc/agent/__init__.py`
- Modify: `tests/test_agent_loop.py`

- [ ] **Step 1: Write failing loop tests**

```python
# tests/test_agent_loop.py (new provider/tool test)
class SkillCallProvider(ModelProvider):
    def __init__(self):
        self._calls = 0
    def stream(self, messages, system_prompt=None, tools=None, model=None, max_tokens=4096):
        self._calls += 1
        if self._calls == 1:
            yield ToolCallDelta(id="s1", name="Skill", arguments_delta='{"skill":"review"}')
            yield MessageComplete(stop_reason="tool_use")
        elif self._calls == 2:
            yield ToolCallDelta(id="t1", name="run_command", arguments_delta='{"command":"echo hi"}')
            yield MessageComplete(stop_reason="tool_use")
        else:
            yield ContentDelta(text="done")
            yield MessageComplete(stop_reason="end_turn")


def test_skill_allowlist_blocks_disallowed_tool(self):
    # setup loop with Skill tool + run_command tool + skill_registry where review allows read_file only
    # assert tool result for run_command is error about not allowed by active skill
    pass
```

- [ ] **Step 2: Run targeted loop test to verify it fails**

Run: `python -m unittest tests.test_agent_loop.TestAgentLoopToolExecution.test_skill_allowlist_blocks_disallowed_tool -v`
Expected: FAIL because no skill-aware allowlist enforcement exists.

- [ ] **Step 3: Implement minimal loop integration**

```python
# qgitc/agent/agent_loop.py (QueryParams)
from qgitc.agent.skills.registry import SkillRegistry

@dataclass
class QueryParams:
    provider: ModelProvider
    system_prompt: str = ""
    context_window: int = 100000
    max_output_tokens: int = 4096
    skill_registry: Optional[SkillRegistry] = None
```

```python
# qgitc/agent/agent_loop.py (build system prompt before stream)
from qgitc.agent.skills.prompt import render_skills_reminder

skill_text = ""
if params.skill_registry is not None:
    visible = params.skill_registry.get_model_visible_skills()
    skill_text = render_skills_reminder(visible)

full_prompt = params.system_prompt or ""
if skill_text:
    full_prompt = (full_prompt + "\n\n" + skill_text).strip()

assistant_msg = self._stream_response(params.provider, full_prompt, tool_schemas)
```

```python
# qgitc/agent/agent_loop.py (_execute_tool_blocks)
active_state = {
    "tool_allowed_tools": None,
    "skill_registry": (self._params.skill_registry if self._params else None),
}

for block in tool_blocks:
    allowed = active_state.get("tool_allowed_tools")
    if allowed is not None and block.name != "Skill" and block.name not in allowed:
        msg = "Tool '{}' is not allowed by active skill".format(block.name)
        results.append(ToolResultBlock(tool_use_id=block.id, content=msg, is_error=True))
        self.toolCallResult.emit(block.id, msg, True)
        continue

    ctx = ToolContext(
        working_directory=".",
        abort_requested=lambda: self._abort_flag,
        extra=active_state,
    )
```

```python
# qgitc/agent/__init__.py (exports)
from qgitc.agent.skills.discovery import load_skill_registry
from qgitc.agent.skills.registry import SkillRegistry

__all__.extend([
    "SkillRegistry",
    "load_skill_registry",
])
```

- [ ] **Step 4: Run updated loop tests**

Run: `python -m unittest tests.test_agent_loop -v`
Expected: PASS including new skill/allowlist test.

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/agent_loop.py qgitc/agent/__init__.py tests/test_agent_loop.py
git commit -m "feat(agent): wire skills into loop prompt and tool allowlist"
```

### Task 5: Wire skill registry in chat entry point

**Files:**
- Modify: `qgitc/aichatwidget.py`

- [ ] **Step 1: Write failing test for query params carrying skill registry**

```python
# add to existing aichat widget tests near _buildQueryParams coverage
self.assertIsNotNone(params.skill_registry)
```

- [ ] **Step 2: Run targeted test to verify it fails**

Run: `python -m unittest tests.test_aichat -v`
Expected: FAIL because `_buildQueryParams` does not attach a skill registry.

- [ ] **Step 3: Implement minimal wiring**

```python
# qgitc/aichatwidget.py imports
from qgitc.agent.skills.discovery import load_skill_registry

# qgitc/aichatwidget.py __init__ or lazy init
self._skillRegistry = None

# qgitc/aichatwidget.py helper
def _ensureSkillRegistry(self):
    if self._skillRegistry is None:
        self._skillRegistry = load_skill_registry(cwd=".")
    return self._skillRegistry

# qgitc/aichatwidget.py _buildQueryParams return
return QueryParams(
    provider=adapter,
    system_prompt=self._buildSystemPrompt(chatMode, sysPrompt),
    context_window=caps.context_window,
    max_output_tokens=caps.max_output_tokens,
    skill_registry=self._ensureSkillRegistry(),
)
```

- [ ] **Step 4: Run test suite for chat + agent integration**

Run: `python -m unittest tests.test_aichat tests.test_agent_loop tests.test_agent_tool_registration -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add qgitc/aichatwidget.py
git commit -m "feat(chat): attach skill registry to agent query params"
```

### Task 6: Final verification pass and release commit guidance

**Files:**
- Modify: `qgitc/agent/skills/__init__.py` (if export gaps found)
- Modify: tests as needed for import/export consistency

- [ ] **Step 1: Run full targeted skill-related regression set**

Run: `python -m unittest tests.test_agent_skills_loader tests.test_agent_skills_registry tests.test_agent_tools_skill tests.test_agent_loop tests.test_agent_tool tests.test_agent_tool_registration -v`
Expected: PASS.

- [ ] **Step 2: Run packaging sanity check**

Run: `python -m pip install -e .`
Expected: install succeeds without dependency resolution errors.

- [ ] **Step 3: Generate final commit message (if any final fixup commit is needed)**

```text
chore(agent): finalize skills integration test coverage
```

- [ ] **Step 4: Commit final tiny fixups only if present**

```bash
git add -A
git commit -m "chore(agent): finalize skills integration test coverage"
```

- [ ] **Step 5: Confirm commit footer policy**

Run: `git log -1 --pretty=%B`
Expected: message contains no `Co-authored-by` footer.

## Self-Review Checklist
- Spec coverage: all approved requirements mapped to tasks (skills core, tool invocation, lazy content loading, prompt reminder, allowlist enforcement, tests).
- Placeholder scan: no `TODO/TBD` placeholders remain.
- Type consistency: `SkillDefinition`, `SkillRegistry`, `QueryParams.skill_registry`, `ToolContext.extra`, and `Skill` tool naming are used consistently.
- Scope check: single subsystem (agent skills) with incremental, buildable commits.
