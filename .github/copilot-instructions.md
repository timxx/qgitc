# Copilot instructions for QGitc

## Big picture
- QGitc is a cross-platform PySide6 (Qt) desktop Git GUI with optional AI features (chat, commit message generation, code review, conflict resolution).
- Entry points:
  - Installed command: `qgitc` → `qgitc.main:main` (see `pyproject.toml`).
  - Repo-local launcher: `python qgitc.py ...` (thin wrapper calling `qgitc.main:main`).

## Architecture & navigation
- App wiring + window routing is in `qgitc/application.py`:
  - `Application.event()` dispatches custom events (see `qgitc/events.py`) to the active window.
  - Windows are keyed by `WindowType` (see `qgitc/windowtype.py`) and created via `Application.getWindow()`.
- The CLI parses subcommands in `qgitc/main.py` (`log`, `blame`, `commit`, `chat`, `bcompare`, `pick`, `mergetool`, `shell`).

## Git integration (important conventions)
- Prefer the repo’s Git wrappers over ad-hoc `subprocess`:
  - Core wrappers: `qgitc/gitutils.py` (`Git`, `GitProcess`, `QGitProcess`).
  - Tool-style helpers: `qgitc/tools/utils.py:runGit()`.
- These wrappers handle Windows process flags, `LANGUAGE=en_US`, Qt-thread compatibility, and consistent error reporting.
- Multi-repo/submodule support is a first-class concept:
  - Main repo is conceptually `.`; submodules are identified by repo-relative paths.
  - See the canonical rules in `qgitc/models/prompts.py` (`REPO_DESC`).

## AI / agent tooling
- LLM abstractions live in `qgitc/llm.py` (history → OpenAI Chat Completions messages + tool call sequencing).
- Providers are registered with `AiModelFactory`; key implementations:
  - `qgitc/models/githubcopilot.py` (Copilot endpoints, model capabilities, may use `/responses`).
  - `qgitc/models/localllm.py` (OpenAI-compatible local server).
- Agent tool definitions and execution:
  - Schemas + registry: `qgitc/agenttools.py`.
  - Handlers + safety checks: `qgitc/agenttoolexecutor.py`.
  - When adding a new tool: add a schema/model + register it, implement a handler in the executor, then add/extend tests under `tests/test_agent_*.py`.

## Build/run workflows
- Run from source (examples):
  - `python qgitc.py log`
  - `python qgitc.py commit`
  - `python qgitc.py chat`
- Build Qt assets (regenerates `qgitc/ui_*.py` from `qgitc/*.ui`): `python setup.py build` (see `setup.py:BuildQt`).
- `build/` is generated output from the build; do not edit anything under `build/`.
- If you change any `qgitc/*.ui` file, rebuild to regenerate the corresponding `qgitc/ui_*.py` files (do not hand-edit the generated `ui_*.py`).
- Shell integration is implemented in `qgitc/shell.py` (`qgitc shell register|unregister`).

## Coding style (project conventions)
- Prefer `camelCase` for Python variables, function/method names, and locals to match the existing codebase.
- Keep changes minimal and consistent with surrounding code (especially in Qt widget classes and tool handlers).

## Tests (unittest + Qt)
- Tests are `unittest`-based and use a Qt `Application(testing=True)` harness that creates temporary git repos (see `tests/base.py`).
- Run tests headlessly:
  - Set `QT_QPA_PLATFORM=offscreen` (CI does this on Linux).
  - `python -m unittest discover -s tests -p "test_*.py" -v`
- CI reference: `.github/workflows/tests.yml` (also shows the coverage command used).

## Tooling safety notes (apply_patch/read_file)
- The in-app `apply_patch` tool preserves BOM/newline style and refuses writes outside the repo:
  - Implementation: `qgitc/tools/applypatch.py` + path checks in `qgitc/tools/readfile.py`.
- On Windows, tool-provided absolute paths may show up as `/C:/...`; they are normalized by `normalizeToolFilePath()`.
