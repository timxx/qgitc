---
name: commit-message
description: Generate a Git commit message for staged changes across one or more repos
argument-hint: "Space-separated list of repo dirs (. for main repo, relative submodule path for others)"
allowed-tools: git_diff_staged, git_log, git_status, Skill
---
# Commit Message Generation

Your goal is to generate a concise, accurate Git commit message for the staged changes.

## Repos to process

The repos with staged changes are listed in `$ARGUMENTS` as space-separated directory identifiers:
- `.` means the main repo root (use `Git.REPO_DIR` as the absolute path).
- Any other value (e.g. `libs/foo`) is a submodule or sub-repo; construct its absolute path as `{main_repo_dir}/{value}`.

For each repo:
1. Call `git_diff_staged` (pass `repoDir` as the absolute path) to get the staged diff.
2. Call `git_log` (pass `repoDir`, set `limit` to 10) to fetch recent commit messages for style reference.

## Generating the message

1. Analyze the staged diffs to understand what was changed and why.
2. Review the recent commits for the established format, style, and language conventions. Do NOT copy them.
3. Write a single commit message that covers all repos if there are multiple.
4. Follow the style and language of the recent commits.
5. Remove meta information (issue refs, tags, author names) — the developer adds those separately.

## Output

Output ONLY the raw commit message text. No markdown fences, no preamble, no explanations.

$ARGUMENTS
