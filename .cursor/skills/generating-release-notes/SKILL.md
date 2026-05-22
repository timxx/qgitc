---
name: generating-release-notes
description: Use when generating release notes between the latest and previous git tags where commit messages are noisy, duplicated, or misleading and the summary must reflect real net code changes.
user-invocable: true
---

# Generating Release Notes

## Overview
Release notes must describe what shipped, not what commit titles claim. Infer themes from net diffs across the tag range, then group related commits under one subject with concrete details in the body.

## When to Use
- Commits include WIP, cleanup, typo, or duplicated messages
- Multiple commits implement one feature across follow-ups
- Some commits were reverted before the latest tag
- You need user-facing notes with accurate engineering details

Do not use this skill for single-commit changelogs or internal forensic debugging.

## Core Pattern
1. Find the latest and previous tags.
2. Collect commit metadata in that range.
3. Read diffs for each commit and compute net effect.
4. Cluster commits by actual outcome, not title.
5. Write one subject per cluster, then detailed body bullets.
6. Drop no-op, reverted, and low-value noise unless it materially affects users.

## Quick Reference
- Tag range:
```bash
LATEST=$(git describe --tags --abbrev=0)
PREV=$(git describe --tags --abbrev=0 "${LATEST}^")
RANGE="${PREV}..${LATEST}"
```
- Commit list:
```bash
git log --reverse --oneline "$RANGE"
```
- Per-commit truth source:
```bash
git show --stat --patch --no-color <sha>
```
- Net validation for theme:
```bash
git diff --stat "$RANGE"
git diff --name-only "$RANGE"
```

## Implementation
### Output File
- Save generated release notes as a markdown file in `docs/releases/` directory.
- File naming: `<latest-tag>.md` (e.g., `v2.4.0.md`)
- Create `docs/releases/` directory if it does not exist.

### Writing Language
- Default when omitted: `Chinese`
- Apply language to all user-facing release note text (headings, subjects, and bullets).
- Keep technical tokens unchanged when needed for clarity (tag names, file paths, CLI flags, APIs).

### Subject and Body Rules
- Subject line: one durable outcome, user-facing where possible.
- Body: 2-5 bullets that cite concrete behavior, components, tests, or edge cases.
- Merge many commits for the same outcome into one subject.
- If a commit message conflicts with diff evidence, trust the diff.
- Default output is release notes only. Include analysis tables only when explicitly requested.

### Grouping Heuristics
Group commits together when at least one is true:
- Same component or files changed for one outcome
- Follow-up fix completes the first commit
- Initial implementation plus setting persistence/tests/docs for same feature
- Duplicate commit titles that touch same behavior

Split into separate subjects when outcomes are independently releasable.

### Exclusion Rules
Exclude by default:
- Whitespace-only edits
- Pure typo or wording tweaks
- Temporary debug code later removed
- Commit-and-revert sequences with zero net behavior change
- Test additions or changes (unit, integration, regression)
- Build system, CI/CD, or tooling changes

Include these only when they change user behavior, reliability, or migration risk.

## Common Mistakes
| Mistake | Fix |
|---|---|
| Summarizing commit titles directly | Read patch and stat first, then write notes |
| One bullet per commit | Cluster by outcome and write one subject per theme |
| Reporting reverted work as shipped | Verify net diff across the full tag range |
| Listing minor churn as key changes | Keep only durable impact and meaningful engineering changes |
| Returning investigation notes as final output | Return clean release notes unless asked for analysis |

## Red Flags - Stop and Re-check
- "This title says feat, so I will ship it in notes"
- "I do not need to inspect diffs for small commits"
- "Duplicate commits should become duplicate bullets"
- "Reverted work still counts because it happened"

All of these mean: recompute by net effect from the full range.

## Output Template
Generate and save to `docs/releases/<latest-tag>.md`:

```markdown
## <latest-tag>

### <Theme Subject 1>

1. <user-facing change 1>
2. <user-facing change 2>

### <Theme Subject 2>

1. <user-facing change 1>
```

For example:

```markdown
## v7.0.0

### 优化commit窗口相关功能

1. 现在支持管理模板，并允许AI使用指定的模板生成message
2. 新增支持隐藏未跟踪的文件（在列表中右键菜单）
3. 优化amend体验，现在会显示被amend的记录


### 修复Copilot模型列表可能刷新不出来问题

网络差的时候比较容易超时导致刷新不出来，原来设置了1.5秒超时，现在去掉了

```

## Rationalization Table
| Excuse | Reality |
|---|---|
| "Messages are good enough" | Messages are hints; shipped behavior lives in diffs. |
| "Too many commits to inspect" | Grouping requires evidence; scan stats then deep-read only relevant patches. |
| "Cleanup and typo should still be highlighted" | Release notes are for impact, not repository noise. |
| "Each commit deserves a bullet" | Users need outcomes; combine related commits into one subject with detailed body. |
