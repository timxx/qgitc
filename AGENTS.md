# QGitc agent instructions

## Project overview
- QGitc is a PySide6 desktop Git GUI with AI-assisted chat, code review, commit-message generation, and merge-conflict resolution.
- Keep changes small and localized; this codebase is Qt-heavy and uses many window-centric interactions.
- Start from [qgitc.py](qgitc.py) and [qgitc/main.py](qgitc/main.py) for entry points, then inspect [qgitc/application.py](qgitc/application.py) for app wiring.

## Architecture to understand before editing
- [qgitc/application.py](qgitc/application.py) is the composition root; it creates shared services, lazily creates windows, and routes custom Qt events.
- Cross-window behavior is event-driven through [qgitc/events.py](qgitc/events.py); follow that pattern when adding new UI actions.
- Window identity is centralized in [qgitc/windowtype.py](qgitc/windowtype.py); prefer using the existing window factory instead of introducing ad hoc window creation.
- The AI chat experience lives around [qgitc/aichatwidget.py](qgitc/aichatwidget.py) and [qgitc/agent/agent_loop.py](qgitc/agent/agent_loop.py); agent tools are permission-gated and should stay consistent with that model.

## Repo-specific conventions
- Use [qgitc/gitutils.py](qgitc/gitutils.py) for git operations instead of raw subprocess usage; it enforces the project’s process and environment conventions.
- For agent or tool code, use [qgitc/agent/tools/utils.py](qgitc/agent/tools/utils.py) and [qgitc/agent/tools](qgitc/agent/tools) rather than creating separate git helpers.
- Multi-repo and submodule behavior is first-class; treat the main repository as the current working directory and repo-relative paths as the canonical scope.
- The repo’s canonical AI prompt wording lives in [qgitc/models/prompts.py](qgitc/models/prompts.py).

## AI and agent integration points
- Provider abstractions and tool-call normalization live in [qgitc/llm.py](qgitc/llm.py).
- Providers are registered through the model factory; the main implementation is [qgitc/models/githubcopilot.py](qgitc/models/githubcopilot.py).
- Built-in tools are registered in [qgitc/agent/tool_registration.py](qgitc/agent/tool_registration.py); add new tools there and keep their permission behavior explicit.
- Path safety matters for file access; respect repo-root restrictions and Windows path normalization when touching file tools.

## Build, test, and validation
- Install dependencies with `python -m pip install -r requirements.txt`.
- Rebuild Qt-generated files with `python setup.py build` when UI files change.
- Do not edit generated output under [build](build) or the generated UI modules under [qgitc](qgitc); regenerate them instead.
- Run the app locally with `python qgitc.py log`, `python qgitc.py commit`, or `python qgitc.py chat`.
- Tests use `unittest` plus a Qt harness; see [tests/base.py](tests/base.py) for the standard setup.
- Typical test command: `python -m unittest discover -s tests -p "test_*.py" -v`.

## Editing workflow
- Follow TDD for bug fixes and new features: add or update a failing test first, then implement the smallest fix.
- Prefer file-local changes over broad refactors, especially in window and UI code.
- After editing Python files, run `python -m isort <changed-files-or-dirs>` and `python -m py_compile <changed-python-files>`.
- Always run the relevant tests before finishing; if something fails, report the exact command and output.

## Coding conventions
- Use `camelCase` for all Python identifiers, including variables, functions, methods, parameters, and local variables.
- If a UI change touches [qgitc](qgitc) `.ui` files, regenerate the corresponding Python bindings rather than editing them by hand.
- When adding or changing agent tools, add or update tests under [tests](tests) with names matching the existing agent test patterns.
- For UI-related tests that need a `QApplication`, inherit from `TestBase` in [tests/base.py](tests/base.py). If a test does not need a repo, override `doCreateRepo()` with `pass`.
