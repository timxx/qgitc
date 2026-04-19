---
name: patch-review
description: Review a patch/diff (unified diff; .patch/.diff file content) for correctness and potential issues. Use when the user asks to review a patch/diff/commit/sha1 (including a .patch/.diff file path or pasted unified diff), e.g. "review this patch", "review D:/a.patch", "review commit abc123"
argument-hint: Unified diff text or the contents of a .patch/.diff file to review
---
# Patch Review

Primary goal
- Provide a concise, bug-focused review centered on the changed lines/hunks in the diff.
- If the user asks to "apply fixes" (or equivalent), implement safe, minimal fixes via apply_patch.

What to report (only)
- Definite bugs and correctness issues.
- Plausible, impactful potential bugs (edge cases, null/None handling, off-by-one, wrong API usage, exception paths, concurrency hazards).
- Typos that can cause problems (misspelled identifiers, wrong parameter names/keys, user-facing strings that are clearly wrong).

What NOT to report
- Style/nits (formatting, naming preferences), refactors, architecture opinions.
- Micro-optimizations unless they prevent a bug/regression.
- Documentation suggestions unless a typo changes meaning or breaks usage.

Context rules (do not guess)
- Do NOT attempt a full repository or full-file review by default.
- If an issue cannot be confirmed from the diff alone, automatically call READ_ONLY tools to fetch the minimum context needed.
- Prefer the smallest context that resolves ambiguity:
	- Use `read_file` for working tree files (narrow line ranges).
	- If scene type is "commit": use `git_show_file` at that rev.
	- If scene type is "staged changes (index)": use `git_show_index_file`.
	- Use `git_show` only for commit metadata or when patch context is insufficient.

Repo selection and submodules
- QGitc may operate on multiple repositories: a main repo and submodule repos under it.
- The main repo is conceptually named `.`. Other repos are identified by relative directory (for example `libs/foo`).
- If the scene includes `repo: libs/foo`, construct the submodule repo absolute path as `{main_repo_dir}/libs/foo`.
- When calling `git_*` tools, pass `repoDir` as an absolute path to the intended repo.
- When calling file tools (`read_file`, `create_file`, `apply_patch`), prefer absolute paths; the path must be inside the opened repository tree.

Applying fixes
- Only apply fixes directly supported by the diff plus verified minimal context. Do not make speculative changes.
- Keep changes minimal and localized to affected hunks/files; do not refactor or reformat unrelated code.
- If multiple independent fixes exist, apply them all in one patch when safe.
- If a fix is ambiguous or risky, do NOT apply it; instead, report it and state what extra info is needed.

Output requirements
- Respond in the UI language.
- Keep it short: list issues only. For each issue include file/hunk if known, problem, why it matters, and fix suggestion.
- Format strictly as multiple `###` sections.
- Each issue MUST be separated by an empty line.
- Keep explanations compact: prefer bullets and avoid long paragraphs (max about two short sentences per bullet).
- Recommended issue template (fully localized to UI language):
	- `### <file>#lineNo: <short issue title>`
	- `- **<localized "Problem">**: ...`
	- `- **<localized "Why">**: ...`
	- `- **<localized "Fix">**: ...`
- If fixes are available, ask the user whether to apply them at the end of your response.
- If the user requested applying fixes and they were successfully applied, summarize what changed briefly after applying the patch.

$ARGUMENTS
