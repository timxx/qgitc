# Patch Review Skill Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the dedicated CodeReview chat mode and its hardcoded prompt constants; route all review entry points through the built-in `patch-review` skill in Agent mode.

**Architecture:** Bundle a `patch-review` skill under `qgitc/data/skills/`. Load it via `additional_directories` in the skill registry. All code-review entry points call a new `_executeSkillDirectly()` helper that expands the skill content with the diff as `$ARGUMENTS`, injects context, and sends the request in Agent mode. `AiChatMode.CodeReview` and the two prompt constants are deleted.

**Tech Stack:** Python 3, PySide6, unittest, PyYAML (already a dependency)

---

## Commit and Quality Rules (applies to every task)
- Each commit must be minimal and independently buildable/testable.
- Run tests for changed behavior before committing.
- Generate a concise commit message aligned to the task.
- Commit with regular `git commit -m "..."` only.
- Never add a `Co-authored-by` footer.
- After editing Python files, run `python -m isort <changed-files>`.
- Run `python -m py_compile <changed-files>` before committing.

## File Structure

### Modified files
- `qgitc/data/skills/patch-review/SKILL.md` — add `aliases` and `argument-hint` to frontmatter
- `pyproject.toml` — add `data/skills/*/SKILL.md` to package-data
- `qgitc/agent/skills/discovery.py` — tag additional-directory skills as `builtinSkills`
- `qgitc/aichatwidget.py` — load built-in skills dir; add `_executeSkillDirectly()`; change review entry points from `AiChatMode.CodeReview` to skill execution in Agent mode; remove `CODE_REVIEW_PROMPT` usage
- `qgitc/models/prompts.py` — delete `CODE_REVIEW_SYS_PROMPT` and `CODE_REVIEW_PROMPT`
- `qgitc/llm.py` — remove `CodeReview = 1` from `AiChatMode`
- `qgitc/aichatcontextpanel.py` — remove `CodeReview` entry from mode selector
- `tests/test_agent_skills_loader.py` — add test for `builtinSkills` source tag
- `tests/test_agent_mode.py` — update test that used `AiChatMode.CodeReview`

---

### Task 1: Update SKILL.md frontmatter and package it in the wheel

The existing `qgitc/data/skills/patch-review/SKILL.md` has review instructions but is missing the `aliases` and `argument-hint` fields required by the spec. The file must also be included in the built wheel.

**Files:**
- Modify: `qgitc/data/skills/patch-review/SKILL.md` (lines 1–4, frontmatter only)
- Modify: `pyproject.toml` (line ~71, add glob to `package-data`)

- [ ] **Step 1: Add aliases and argument-hint to SKILL.md frontmatter**

Open `qgitc/data/skills/patch-review/SKILL.md` and replace the frontmatter block:

```yaml
---
name: patch-review
description: Review a patch or diff for code quality, correctness, and potential issues
aliases: [code-review, review]
argument-hint: Unified diff or patch content to review
---
```

Leave the body unchanged.

- [ ] **Step 2: Add skill files to pyproject.toml package-data**

In `pyproject.toml`, inside the `[tool.setuptools.package-data]` `qgitc` list, add the glob after the last existing entry:

```toml
[tool.setuptools.package-data]
qgitc = [
    "data/icons/*.ico",
    "data/icons/*.svg",
    "data/licenses/Apache-2.0.html",
    "data/translations/*.qm",
    "data/templates/*.xlsx",
    "data/skills/*/SKILL.md",
]
```

- [ ] **Step 3: Verify syntax**

Run: `python -m py_compile qgitc/models/prompts.py`
Expected: no output (clean compile; this is a sanity check that imports still work).

- [ ] **Step 4: Commit**

```
git add qgitc/data/skills/patch-review/SKILL.md pyproject.toml
git commit -m "feat: add aliases/argument-hint to patch-review skill and package it"
```

---

### Task 2: Tag additional-directory skills as builtinSkills and load built-in skills directory

Skills loaded from `additional_directories` (the bundled data path) must be tagged with `source = "builtinSkills"` per spec. The skill registry loader in `_ensureSkillRegistry` must pass `dataDirPath() + "/skills"` as an additional directory.

**Files:**
- Modify: `qgitc/agent/skills/discovery.py` (line 28)
- Modify: `qgitc/aichatwidget.py` (lines 1048–1050, `_ensureSkillRegistry`)
- Create: test assertions in `tests/test_agent_skills_loader.py`

- [ ] **Step 1: Write failing test for builtinSkills source tag**

Add this test method at the end of `TestLoadSkillRegistry` in `tests/test_agent_skills_loader.py`:

```python
    def test_additional_directories_are_tagged_as_builtin_skills(self):
        with tempfile.TemporaryDirectory() as extra_td, tempfile.TemporaryDirectory() as proj_td:
            extra = Path(extra_td)
            proj = Path(proj_td)
            self._write_skill(extra, "patch-review", "patch-review", "Review a patch")
            registry = load_skill_registry(cwd=str(proj), additional_directories=[str(extra)])
            skill = registry.get("patch-review")
            self.assertIsNotNone(skill)
            self.assertEqual(skill.source, "builtinSkills")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_agent_skills_loader.TestLoadSkillRegistry.test_additional_directories_are_tagged_as_builtin_skills -v`
Expected: FAIL — `AssertionError: None != 'builtinSkills'` (skill source is not set).

- [ ] **Step 3: Tag additional-directory skills in discovery.py**

In `qgitc/agent/skills/discovery.py`, change the loop at line 28 from:

```python
    for extra_dir in additional_directories or []:
        for skill in load_skills_from_directory(str(extra_dir)):
            registry.register(skill)
```

to:

```python
    for extra_dir in additional_directories or []:
        for skill in load_skills_from_directory(str(extra_dir)):
            skill.source = "builtinSkills"
            registry.register(skill)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_agent_skills_loader.TestLoadSkillRegistry.test_additional_directories_are_tagged_as_builtin_skills -v`
Expected: PASS

- [ ] **Step 5: Wire built-in skills directory into _ensureSkillRegistry**

In `qgitc/aichatwidget.py`, change `_ensureSkillRegistry` (around line 1048) from:

```python
    def _ensureSkillRegistry(self):
        # type: () -> SkillRegistry
        if self._skillRegistry is None:
            self._skillRegistry = load_skill_registry(cwd=Git.REPO_DIR or ".")
            self._slashCommandRegistry = None
        return self._skillRegistry
```

to:

```python
    def _ensureSkillRegistry(self):
        # type: () -> SkillRegistry
        if self._skillRegistry is None:
            self._skillRegistry = load_skill_registry(
                cwd=Git.REPO_DIR or ".",
                additional_directories=[
                    dataDirPath() + "/skills"
                ],
            )
            self._slashCommandRegistry = None
        return self._skillRegistry
```

- [ ] **Step 6: Run isort and py_compile**

Run: `python -m isort qgitc/agent/skills/discovery.py qgitc/aichatwidget.py tests/test_agent_skills_loader.py`
Run: `python -m py_compile qgitc/agent/skills/discovery.py qgitc/aichatwidget.py`

- [ ] **Step 7: Run full skills loader tests**

Run: `python -m unittest tests.test_agent_skills_loader -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```
git add qgitc/agent/skills/discovery.py qgitc/aichatwidget.py tests/test_agent_skills_loader.py
git commit -m "feat: load built-in skills from dataDirPath and tag as builtinSkills"
```

---

### Task 3: Add _executeSkillDirectly helper and switch review entry points to Agent mode

The three code review entry points (`codeReview`, `codeReviewForDiff`, `codeReviewForStagedFiles`) currently call `_doRequest(diff, AiChatMode.CodeReview)`. They need to instead look up the `patch-review` skill, expand its content with the diff, and call `_doRequest` in `AiChatMode.Agent`.

The `CODE_REVIEW_PROMPT` branch in `_doRequest` also needs removal since skill expansion handles wrapping.

**Files:**
- Modify: `qgitc/aichatwidget.py` (lines 78–90 imports; line 788–789 CodeReview branch; lines 1332, 1347, 1365 entry points)

- [ ] **Step 1: Remove CODE_REVIEW_PROMPT import**

In `qgitc/aichatwidget.py`, change the import block (around line 79):

```python
from qgitc.models.prompts import (
    AGENT_SYS_PROMPT,
    CODE_REVIEW_PROMPT,
    RESOLVE_PROMPT,
    RESOLVE_SYS_PROMPT,
)
```

to:

```python
from qgitc.models.prompts import (
    AGENT_SYS_PROMPT,
    RESOLVE_PROMPT,
    RESOLVE_SYS_PROMPT,
)
```

- [ ] **Step 2: Remove the CodeReview branch inside _doRequest**

In `qgitc/aichatwidget.py`, remove these three lines (around line 788–789):

```python
        if chatMode == AiChatMode.CodeReview:
            prompt = CODE_REVIEW_PROMPT.format(diff=prompt)

```

The lines immediately before (`injectedContext = self._injectedContext`) and after (`# Build context`) should remain, with no blank line gap change.

- [ ] **Step 3: Add _executeSkillDirectly helper method**

Add this new method to `AiChatWidget`, immediately after `_expandSkillArguments` (around line 862):

```python
    def _executeSkillDirectly(self, skillName: str, args: str):
        """Look up a skill by name and execute it in Agent mode.

        The skill content is expanded with args via $ARGUMENTS substitution
        and sent as the user prompt in Agent mode.
        """
        skillRegistry = self._ensureSkillRegistry()
        skill = skillRegistry.get(skillName) if skillRegistry is not None else None
        if skill is None:
            logger.warning("Skill '%s' not found in registry", skillName)
            return

        expandedPrompt = self._expandSkillArguments(skill.content, args)
        self._doRequest(
            expandedPrompt,
            AiChatMode.Agent,
            collapsed=False,
            parseSlashCommand=False,
        )
```

- [ ] **Step 4: Switch codeReview entry point**

Change the last line of the `codeReview` method (around line 1332) from:

```python
        self._doRequest(diff, AiChatMode.CodeReview)
```

to:

```python
        self._executeSkillDirectly("patch-review", diff)
```

- [ ] **Step 5: Switch codeReviewForDiff entry point**

Change `codeReviewForDiff` (around line 1347) from:

```python
        self._doRequest(diff, AiChatMode.CodeReview)
```

to:

```python
        self._executeSkillDirectly("patch-review", diff)
```

- [ ] **Step 6: Run isort and py_compile**

Run: `python -m isort qgitc/aichatwidget.py`
Run: `python -m py_compile qgitc/aichatwidget.py`
Expected: clean output.

- [ ] **Step 7: Run existing tests to check nothing is broken**

Run: `python -m unittest tests.test_agent_mode -v`
Expected: tests still pass (note: `test_build_query_params_threads_temperature_and_chat_mode` still uses `AiChatMode.CodeReview` — it will be updated in Task 5).

- [ ] **Step 8: Commit**

```
git add qgitc/aichatwidget.py
git commit -m "feat: route code review entry points through patch-review skill in Agent mode"
```

---

### Task 4: Remove CODE_REVIEW_SYS_PROMPT and CODE_REVIEW_PROMPT from prompts.py

Now that no code references these constants, remove them from the module.

**Files:**
- Modify: `qgitc/models/prompts.py` (delete lines 12–70)

- [ ] **Step 1: Delete the two constants**

In `qgitc/models/prompts.py`, remove the entire `CODE_REVIEW_SYS_PROMPT` block (lines 12–63) and the `CODE_REVIEW_PROMPT` block (lines 65–70). The file should go directly from the end of `REPO_DESC` to the start of `AGENT_SYS_PROMPT`:

```python
# -*- coding: utf-8 -*-


REPO_DESC = """Repo selection / submodules
- QGitc may operate on multiple repositories: a main repo and submodule repos under it.
- The main repo is conceptually named `.`. Other repos are identified by relative directory (e.g. `libs/foo`).
- If the scene includes `repo: libs/foo`, construct the submodule repo absolute path as `{main_repo_dir}/libs/foo`.
- When calling `git_*` tools, pass `repoDir` as an absolute path to the intended repo.
- When calling file tools (`read_file`, `create_file`, `apply_patch`), prefer absolute paths; the path must be inside the opened repository tree."""


AGENT_SYS_PROMPT = f"""You are a Git assistant inside QGitc.
```

- [ ] **Step 2: Verify syntax and imports**

Run: `python -m py_compile qgitc/models/prompts.py qgitc/aichatwidget.py`
Expected: clean output.

- [ ] **Step 3: Run full test suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```
git add qgitc/models/prompts.py
git commit -m "refactor: remove legacy CODE_REVIEW_SYS_PROMPT and CODE_REVIEW_PROMPT"
```

---

### Task 5: Remove AiChatMode.CodeReview and update all references

With no call sites remaining, remove the enum member and update the mode selector and any tests.

**Files:**
- Modify: `qgitc/llm.py` (line 85)
- Modify: `qgitc/aichatcontextpanel.py` (line 358)
- Modify: `tests/test_agent_mode.py` (lines 157, 163)

- [ ] **Step 1: Remove CodeReview from AiChatMode enum**

In `qgitc/llm.py`, change:

```python
class AiChatMode(Enum):

    Chat = 0
    CodeReview = 1
    Agent = 2
```

to:

```python
class AiChatMode(Enum):

    Chat = 0
    Agent = 2
```

Keep value `2` for `Agent` to avoid breaking serialized history references.

- [ ] **Step 2: Remove CodeReview from mode selector in context panel**

In `qgitc/aichatcontextpanel.py`, change `_setupChatMode` (around line 354):

```python
    def _setupChatMode(self):
        modes = {
            AiChatMode.Agent: "🔧 " + self.tr("Agent"),
            AiChatMode.Chat: "💬 " + self.tr("Chat"),
            AiChatMode.CodeReview: "📝 " + self.tr("Code Review"),
        }
```

to:

```python
    def _setupChatMode(self):
        modes = {
            AiChatMode.Agent: "🔧 " + self.tr("Agent"),
            AiChatMode.Chat: "💬 " + self.tr("Chat"),
        }
```

- [ ] **Step 3: Update test_agent_mode.py**

In `tests/test_agent_mode.py`, the test `test_build_query_params_threads_temperature_and_chat_mode` uses `AiChatMode.CodeReview`. Change it to use `AiChatMode.Agent`:

Find (around line 157):

```python
            params = self.chatWidget._buildQueryParams(AiChatMode.CodeReview)
```

Replace with:

```python
            params = self.chatWidget._buildQueryParams(AiChatMode.Agent)
```

Find (around line 163):

```python
        self.assertEqual(params.provider._chat_mode, AiChatMode.CodeReview)
```

Replace with:

```python
        self.assertEqual(params.provider._chat_mode, AiChatMode.Agent)
```

- [ ] **Step 4: Verify no remaining references to CodeReview**

Run: `grep -rn "CodeReview" qgitc/ tests/ --include="*.py" | grep -v build/`
Expected: no matches.

- [ ] **Step 5: Run isort and py_compile**

Run: `python -m isort qgitc/llm.py qgitc/aichatcontextpanel.py tests/test_agent_mode.py`
Run: `python -m py_compile qgitc/llm.py qgitc/aichatcontextpanel.py tests/test_agent_mode.py`
Expected: clean output.

- [ ] **Step 6: Run full test suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```
git add qgitc/llm.py qgitc/aichatcontextpanel.py tests/test_agent_mode.py
git commit -m "refactor: remove AiChatMode.CodeReview and all references"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: all tests pass.

- [ ] **Step 2: Verify no legacy constants or enum members remain**

Run: `grep -rn "CODE_REVIEW_SYS_PROMPT\|CODE_REVIEW_PROMPT\|CodeReview" qgitc/ tests/ --include="*.py" | grep -v build/`
Expected: no matches.

- [ ] **Step 3: Verify skill is loadable**

Run:
```python
python -c "from qgitc.common import dataDirPath; from qgitc.agent.skills.loader import load_skills_from_directory; skills = load_skills_from_directory(dataDirPath() + '/skills'); print([(s.name, s.aliases) for s in skills])"
```
Expected: `[('patch-review', ['code-review', 'review'])]`

- [ ] **Step 4: Verify the app launches**

Run: `python qgitc.py log`
Expected: app launches without import errors or crashes.
