---
name: generating-release-notes
description: Use when generating release notes between the latest and previous git tags where commit messages are noisy, duplicated, or misleading and the summary must reflect real net code changes.
user-invocable: true
---

# Generating Release Notes

## Overview
Release notes must describe what shipped, not what commit titles claim. Infer themes from net diffs across the tag range, then group related commits under one subject. Every bullet answers **what changed** and, for a new feature, **how to use it** — written for the QGitc user, not the implementer.

## When to Use
- Commits include WIP, cleanup, typo, or duplicated messages
- Multiple commits implement one feature across follow-ups
- Some commits were reverted before the latest tag
- You need notes the user can act on, backed by accurate engineering detail

Do not use this skill for single-commit changelogs or internal forensic debugging.

## Core Pattern
1. Find the latest and previous tags.
2. Collect commit metadata in that range.
3. Read diffs for each commit and compute net effect.
4. Cluster commits by actual outcome, not title.
5. Write one subject per cluster, then body bullets in the user's view.
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
- Keep tokens that survive the bullet targets in their original form (tag names, CLI flags, file paths).

### Subject and Body Rules
- Subject line: one durable outcome, user-facing where possible.
- Body: 2-5 bullets, each one or two sentences naming what changed for the user.
- New feature: every bullet carrying one says how to use it — menu path, click target, setting name and default.
- Bug fix: name the symptom the user saw, then that it is fixed.
- Merge many commits for the same outcome into one subject.
- If a commit message conflicts with diff evidence, trust the diff.
- Default output is release notes only. Include analysis tables only when explicitly requested.

### Bullet targets
Read the diffs for accuracy; write the user's view of them.

| Bad (implementer's view) | Good (user's view) |
|---|---|
| 手工构造的 `QMimeData` 在解释器 finalize 时被 shiboken 析构，进程以 SIGSEGV 退出 | 修复退出时进程崩溃（SIGSEGV） |
| 每行按 `QTextLayout.boundingRect()` 高度预留，`_reserveDrawnHeight` 保证相邻行严丝合缝 | 修复含中文/日文的行与下一行重叠、选中背景盖住上一行下缘 |
| 滚动事件的文件定位从 3.6ms 降到 0.01ms，单帧绘制从 2.7ms 降到 1.5ms | 800 个文件的大 diff 滚动不再卡顿 |
| 文本查看器支持折叠（`beginBlock`/`addBlock` 注册块，`toggleFoldAt` 切换） | 每个文件的 diff 都可折叠：点击左侧三角图标折叠或展开 |

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
| Writing the mechanism or root cause | Name the symptom the user saw and that it is fixed |
| Naming classes, methods, or internal identifiers | Name the surface the user touches: menu, click target, setting |
| Quoting benchmark or test numbers | Keep the one number a user can feel, translate it into their experience |
| Describing a new feature without how to use it | Add the menu path, click target, or setting name |
| Listing minor churn as key changes | Keep only what the user can see or feel |
| Returning investigation notes as final output | Return clean release notes unless asked for analysis |

## Red Flags - Stop and Re-check
- "This title says feat, so I will ship it in notes"
- "I do not need to inspect diffs for small commits"
- "Duplicate commits should become duplicate bullets"
- "Reverted work still counts because it happened"
- "This root cause is interesting, so I will include it"
- "The benchmark number proves the work, so I will quote it"
- "The feature name already tells the user how to use it"

All of these mean: recompute by net effect from the full range, then cut to the user's view.

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

网络差时容易超时导致列表刷新不出来，现在去掉了超时限制

```

## Rationalization Table
| Excuse | Reality |
|---|---|
| "Messages are good enough" | Messages are hints; shipped behavior lives in diffs. |
| "Too many commits to inspect" | Grouping requires evidence; scan stats then deep-read only relevant patches. |
| "Cleanup and typo should still be highlighted" | Release notes are for impact, not repository noise. |
| "Each commit deserves a bullet" | Users need outcomes; combine related commits into one subject with detailed body. |
| "More detail shows rigor" | Detail about the mechanism buries the change; one user-facing sentence per fact is the target. |
