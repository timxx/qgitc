# Copilot instructions for QGitc

## Big picture
- QGitc is a PySide6 desktop Git GUI with AI-assisted chat, code review, commit message generation, and merge conflict resolution.
- Entry points:
  - Installed app: `qgitc` → `qgitc.main:main` (`pyproject.toml` `[project.gui-scripts]`).
  - Source launcher: `python qgitc.py <subcommand>`.
- `qgitc/main.py` is the CLI/router (`log`, `blame`, `commit`, `chat`, `bcompare`, `pick`, `mergetool`, `shell`) and bootstraps `Application`.

## Architecture that matters
- `qgitc/application.py` is the app composition root: creates shared services (`Settings`, telemetry/network manager), lazily creates windows, and routes custom Qt events.
- Cross-window actions are event-driven via `qgitc/events.py` (`BlameEvent`, `ShowCommitEvent`, `CodeReviewEvent`, etc.) handled in `Application.event()`.
- Window identity is centralized in `qgitc/windowtype.py` and instantiated through `Application.getWindow()`.
- AI chat UI (`qgitc/aichatwidget.py`) runs agent mode through `AgentLoop` (`qgitc/agent/agent_loop.py`) and permission-gated tool execution.

## Git + repo conventions (project-specific)
- Use `qgitc/gitutils.py` (`Git`, `GitProcess`, `QGitProcess`) instead of raw `subprocess`; these enforce `LANGUAGE=en_US`, platform flags, and Qt-safe process behavior.
- For agent/tool code, use `qgitc/agent/tools/utils.py:runGit` / `run_git`.
- Multi-repo/submodule semantics are first-class: main repo is `.`; submodules are repo-relative paths. Canonical wording lives in `qgitc/models/prompts.py` (`REPO_DESC`).

## AI/agent integration points
- Provider abstraction + history/tool-call normalization: `qgitc/llm.py`.
- Providers are registered via `AiModelFactory`; main implementation is `qgitc/models/githubcopilot.py` (dynamic model capability fetch + `/chat/completions` vs `/responses` endpoint selection).
- Built-in agent tools are registered in `qgitc/agent/tool_registration.py`; concrete tools live under `qgitc/agent/tools/`.
- Permission policy is explicit (`qgitc/agent/permissions.py`): deny rules, allow rules, read-only auto-allow, write tools require ask/allow.
- Tool path safety: `qgitc/agent/tools/read_file.py` normalizes `/C:/...` on Windows and blocks access outside repo root.

## Build/test workflows
- Install deps: `python -m pip install -r requirements.txt`.
- Rebuild Qt generated files: `python setup.py build` (runs `BuildQt`, regenerates `qgitc/ui_*.py` from `qgitc/*.ui`).
- Do not edit generated output under `build/` or generated `qgitc/ui_*.py` directly.
- Run app locally: `python qgitc.py log` / `python qgitc.py commit` / `python qgitc.py chat`.
- Tests are `unittest` + Qt app harness (`tests/base.py` creates temp repos and sets `QT_QPA_PLATFORM=offscreen`).
- Typical test command: `python -m unittest discover -s tests -p "test_*.py" -v`.

## Editing workflow (required)
- Keep edits minimal and file-local; avoid broad refactors unless explicitly requested.
- Follow TDD for bug fixes and new features: write/update a failing unittest first, run it to confirm failure, then implement code changes, then rerun tests until green.
- After editing Python files, run import formatting with `python -m isort <changed-files-or-dirs>` (project uses `pyproject.toml` `[tool.isort]`, profile `black`).
- Run lint/syntax check on changed files before handoff: `python -m py_compile <changed-python-files>`.
- Always run tests after changes (at least targeted tests; prefer full suite before final handoff):
  - `python -m unittest discover -s tests -p "test_*.py" -v`
- If validation fails, report the exact failing command/output and keep fixes scoped to the requested change.

## Coding conventions for this repo
- **Always use `camelCase` for all Python identifiers** (variables, functions, methods, parameters, local variables). This applies to all new and modified code throughout the project.
- Keep patches surgical in Qt-heavy code: avoid broad refactors across window classes.
- If changing `qgitc/*.ui`, regenerate with build step; do not hand-edit generated UI modules.
- When adding/changing agent tools: implement tool in `qgitc/agent/tools/`, register in `qgitc/agent/tool_registration.py`, and add/update tests under `tests/test_agent_*.py`.
- Test rule: for UI-related tests that require a `QApplication`, use `tests.base.TestBase` as the base class.
- If a `TestBase` test does not need a git repository, override `doCreateRepo()` and leave it empty (`pass`) to skip repo setup (see `tests/test_agent_ui_tool.py`).
