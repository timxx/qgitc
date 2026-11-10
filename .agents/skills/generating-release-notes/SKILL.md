---
name: generating-release-notes
description: Use when writing release notes between the latest and previous git tags, or when releasing — pick the next version from the commits since the last tag (发版 / 下个版本号 / 打个 tag), create the tag, then write notes that reflect the real net code changes.
user-invocable: true
---

# Generating Release Notes

## Overview
Release notes must describe what shipped, not what commit titles claim, and they are written for the QGitc user. When the release has no tag yet the notes also need a version, so the version is **derived from the commits in the range first**, confirmed, and only then written into the notes.

The version lives in the tag: the build derives it from git tags (see the versioning config in `pyproject.toml`), so `git tag vX.Y.Z` is what changes the app's version. No tracked file is edited to bump it.

## When to Use
- Commits in the range include WIP, cleanup, typo, or duplicated messages
- Multiple commits implement one feature across follow-ups
- Some commits were reverted before the latest tag
- The user asks to release, cut a version, or tag (发版 / 打个 tag)
- The recommended version must be confirmed before it becomes the notes' filename and a tag
- You need notes the user can act on, backed by accurate engineering detail

Do not use this skill for single-commit changelogs or internal forensic debugging.

## Core Pattern
1. Pin the base: latest `v*` tag, committed tree.
2. Settle the version: the user's if they named one, otherwise recommend from `BASE..HEAD` and **wait**.
3. Tag it — the tag is the version, so it exists before the notes file is named.
4. Read the commit bodies and the net diff in `BASE..TAG`.
5. Cluster commits by actual outcome, not title.
6. Drop no-op, reverted, and low-value noise unless it materially affects users.
7. Write the notes to `docs/releases/<version>.md`.

## Quick Reference
- Base tag and the range a new version would ship:
```bash
BASE=$(git describe --tags --abbrev=0)
git log --reverse --oneline "${BASE}..HEAD"
```
- Version inputs — a `BREAKING CHANGE` footer lives in the body, not the subject, and a merge commit carries no type of its own:
```bash
git log --format='%s%n%b' "${BASE}..HEAD"
```
- Is the recommended name still free? Nonzero exit means free, exit `0` means taken:
```bash
git rev-parse -q --verify "refs/tags/vX.Y.Z"
```
- Range of a tag that already exists:
```bash
LATEST=$(git describe --tags --abbrev=0)
PREV=$(git describe --tags --abbrev=0 "${LATEST}^")
```
- Create the tag — lightweight, no message, after the range's commits are in:
```bash
git tag vX.Y.Z
git describe --tags --abbrev=0            # must print vX.Y.Z
```
- Per-commit truth source:
```bash
git show --stat --patch --no-color <sha>
```
- Net effect of the range (once the tag exists, prefer `"${BASE}..vX.Y.Z"`):
```bash
git diff --stat "${BASE}..HEAD"
git diff --name-only "${BASE}..HEAD"
```

Always quote the range. Under PowerShell the unquoted `$BASE..HEAD` is parsed as the range operator before git is invoked and can come back empty, which reads as "no commits since the last release"; `${BASE}..HEAD` inside quotes is safe.

## Implementation
### Choosing the Version
The user may name the version outright — use it as given and skip the rest of this section. Otherwise read every subject **and body** in the range: the subject carries the type, the body carries the reason the notes need, and the `BREAKING CHANGE` footer sits at the bottom of the body.

| What the range contains | Recommend |
|---|---|
| a `BREAKING CHANGE` footer, or `!` after the type | major |
| any `feat` | minor |
| everything else (`fix`, `perf`, `refactor`, `docs`, `chore`, `test`) | patch |

While the major is `0`, a breaking change earns a **minor**, not a major.

A range made only of excluded material — tests, CI, docs, refactors with no user-visible effect — has nothing to ship: say that and recommend no release, rather than inventing a patch with an empty notes file.

The recommendation is always `BASE` plus one bump, so it is above the latest tag by construction; the collision check is for a name already used on another branch. If it is taken, do not reuse it: either write that tag's notes from `PREV..LATEST`, or move to the next free number.

Report the base tag, the commits, the recommendation, and the reason in one line, then **stop and wait**:

```
base v7.5.0 · 5 commits · recommend v7.5.1 (patch: fixes only)
```

Nothing has been written yet, so this is the cheap moment to be wrong. If the user only asked for the number, the report is the whole deliverable.

### The Range
The version decides which commits the notes cover:

| Target version | Range |
|---|---|
| a new version, recommended or named | `"${BASE}..${VERSION}"`, the new tag |
| a tag that already exists | `"${PREV}..${LATEST}"` |

Uncommitted work is outside every range: commit it first, or the tag and the notes describe only what is already committed.

Once the tag exists, `BASE..VERSION` and `PREV..LATEST` are the same range — reuse the tag as the anchor rather than trusting `HEAD` to have stayed put.

### Tagging
The notes are named after the tag, so the tag comes first — confirmed version, then tag, then notes. Whether the agent runs `git tag` or hands the command over, `<version>` is a tag by the time `docs/releases/<version>.md` is written, and the report says which happened. A notes file whose name has no matching tag is a draft for a release that has not happened.

Creating it is local and cheap: a lightweight tag on `HEAD`, no push, no tag message. Re-running is idempotent — if `git describe --tags --abbrev=0` already prints the version, skip the `git tag` and go on to the notes.

```bash
git tag vX.Y.Z
git describe --tags --abbrev=0     # must print vX.Y.Z
```

- Tag after the range's commits have landed, or the tag points at fewer commits than the notes describe.
- A plain `git tag` — no `-a`, no message. The existing `v*` tags are lightweight, and the version name is the whole content.
- A taken name makes `git tag` fail. That means the base was wrong or the version already shipped: go back rather than deleting a tag.
- A notes file on disk proves nothing — `<version>.md` exists whether or not the tag does. Check the tag itself with `git describe --tags --abbrev=0`, not the file's date.
- Push stays with the maintainer: print `git push origin <branch>` and `git push origin vX.Y.Z`, and stop there.

### Output File
- Save generated release notes as a markdown file in `docs/releases/` directory, named after the tag: `<version>.md` (e.g., `v2.4.0.md`).
- Create `docs/releases/` directory if it does not exist.
- The directory is gitignored and the notes are not committed — they regenerate from git history on demand. Overwriting an existing file is expected.

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
| Picking the version from subjects only | A `BREAKING CHANGE` footer sits in the body; read bodies before recommending |
| Bumping a patch onto a taken tag | `git rev-parse` first; a taken name means that release is already out |
| Bumping the version by editing `qgitc/version.py` | It is generated from the tag; the tag is the source of truth |
| Writing notes for a version that was never tagged | Tag first — `git tag vX.Y.Z` — then name the file after that tag |
| Writing notes before the version is settled | The filename is the version — confirm it, then write |
| Tagging a different number than the notes file | The file is named after the tag; rename or regenerate it |
| Committing `docs/releases/` | It regenerates from git history and is gitignored |
| Writing the mechanism or root cause | Name the symptom the user saw and that it is fixed |
| Naming classes, methods, or internal identifiers | Name the surface the user touches: menu, click target, setting |
| Quoting benchmark or test numbers | Keep the one number a user can feel, translate it into their experience |
| Describing a new feature without how to use it | Add the menu path, click target, or setting name |
| Listing minor churn as key changes | Keep only what the user can see or feel |
| Returning investigation notes as final output | Return clean release notes unless asked for analysis |

## Red Flags - Stop and Re-check
- "This title says feat, so I will ship it in notes"
- "No `!` in the subject, so nothing here is breaking"
- "The next patch is fine, nobody will notice"
- "A `BREAKING CHANGE` under a chore commit does not count"
- "I will write the file first and pick the number later"
- "The notes file is written, so the version is released"
- "I do not need to inspect diffs for small commits"
- "Duplicate commits should become duplicate bullets"
- "Reverted work still counts because it happened"
- "This root cause is interesting, so I will include it"
- "The benchmark number proves the work, so I will quote it"
- "The feature name already tells the user how to use it"

All of these mean: recompute the range's net effect and the bump from it, then cut to the user's view.

## Output Template
Generate and save to `docs/releases/<version>.md`:

```markdown
## <version>

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
| "SemVer says minor, so the release is safe" | A breaking change hides in a body footer; scan bodies before recommending. |
| "The version is just a number, any free tag works" | The tag becomes the app's version and the notes' filename; derive it from the range. |
| "Tagging is the maintainer's job, I only write text" | The tag is the version and the notes' filename; run `git tag` or hand over the exact command before writing. |
| "Too many commits to inspect" | Grouping requires evidence; scan stats then deep-read only relevant patches. |
| "Cleanup and typo should still be highlighted" | Release notes are for impact, not repository noise. |
| "Each commit deserves a bullet" | Users need outcomes; combine related commits into one subject with detailed body. |
| "More detail shows rigor" | Detail about the mechanism buries the change; one user-facing sentence per fact is the target. |

## Done when
- `git describe --tags --abbrev=0` prints the version the notes describe — the tag exists and points at the commits the notes summarise;
- `docs/releases/<version>.md` covers every commit in `"${BASE}..${VERSION}"` except the excluded material, in Chinese;
- nothing was pushed, and the tree holds no uncommitted work the tag leaves behind;
- the push commands were printed for the maintainer.
