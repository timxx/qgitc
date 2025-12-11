# Cherry Pick Window

## Overview

The Cherry Pick Window is a dedicated interface for cherry-picking commits from one branch to another. It's designed for cherry-picking **entire branches** or **many commits** at once, with powerful filtering and selection options.

> **Note:** If you only need to pick **a few specific commits**, consider using the faster [Drag and Drop](CHERRY_PICK_DRAG_DROP.md) method instead.

## When to Use Cherry Pick Window

Use the Cherry Pick Window when you need to:

- Cherry-pick an **entire branch** or a large portion of it
- Cherry-pick **many commits** with specific criteria
- **Filter commits** based on patterns or characteristics (e.g., exclude reverted commits)
- Have a **dedicated workspace** for reviewing and selecting commits
- See the **difference between source and base branches** clearly

## How to Open

Access the Cherry Pick Window through:

1. **Menu**: Git → Cherry-Pick
2. **Keyboard shortcut**: Check your application's keyboard shortcuts
3. **Context menu**: Right-click on a branch in some views
4. **Command line**: qgitc pick [source-branch]

## Interface Overview

The Cherry Pick Window consists of several key sections:

### Branch Selection (Top)
- **Source Branch**: The branch containing commits you want to cherry-pick
- **Base Branch**: The branch to compare against (commits not in this branch will be shown)
- **Target Branch**: The branch where commits will be applied (usually your current branch)

### Commit List (Left)
- Shows all commits from source branch that are not in base branch
- Commits can be marked for cherry-picking
- Shows commit graph, SHA, author, date, and message

### Commit Details (Right)
- **Top**: Detailed commit information (message, author, dates, parents)
- **Bottom**: File changes and diff view for the selected commit

### Action Buttons (Bottom)
- **Select All**: Mark all commits for cherry-picking
- **Select None**: Unmark all commits
- **Filter Commits**: Apply configured filters to remove unwanted commits
- **Settings**: Open cherry-pick settings
- **Cherry-Pick**: Execute the cherry-pick operation for marked commits

## Step-by-Step Guide

### Step 1: Select Branches

1. **Source Branch**: Choose the branch containing the commits you want to cherry-pick
   - Can be a local or remote branch (e.g., `origin/feature-branch`)
   - Use autocomplete for quick selection

2. **Base Branch**: Choose the comparison baseline
   - Typically the point where the source branch diverged
   - Or the main/master branch to see all feature commits
   - Commits in base branch will be excluded from the list

3. **Target Branch**: Select where to apply commits
   - Usually your currently checked-out branch
   - **Must be checked out** to enable cherry-picking
   - Defaults to your current branch

**Example Scenario:**
```
Source: feature/new-api (the feature branch)
Base: main (to see only feature commits)
Target: release/1.5 (where to apply them)
```

### Step 2: Review and Select Commits

Once branches are selected, the window displays all commits from source branch that aren't in base branch:

1. **Review the commit list**:
   - Commits are shown newest first
   - Each commit shows SHA, author, date, and summary
   - Click on a commit to see its details and diff

2. **Mark commits for cherry-picking**:
   - Click on individual commits to toggle their mark (checkbox)
   - Use **Select All** button to mark all commits
   - Use **Select None** button to unmark all commits
   - **Alt+Click** on commits to toggle marks with keyboard

3. **Use filters** (optional):
   - Click **Filter Commits** to apply configured filters
   - Removes commits matching filter criteria (e.g., reverted commits)
   - Configure filters in Settings

### Step 3: Apply Filters (Optional)

The Filter feature helps remove unwanted commits:

1. Click the **Filter Commits** button (funnel icon)

2. Configured filters are applied:
   - **Filter Reverted Commits**: Removes commits with "This reverts commit" in message
   - **Filter by Patterns**: Removes commits matching configured regex or text patterns
   
3. Filtered commits are automatically **unmarked**

4. Status message shows how many commits were filtered out

**Note:** Configure filters in Settings → Cherry-Pick before using this feature.

### Step 4: Execute Cherry-Pick

1. Review your selection - the status bar shows how many commits are marked

2. Click the **Cherry-Pick** button

3. Commits are applied in order from **oldest to newest**:
   - Each commit is cherry-picked sequentially
   - If conflicts occur, you'll be prompted to resolve them
   - Successfully picked commits are marked with a visual indicator
   - Operation stops if you abort or skip a commit

4. After completion, the commit list shows which commits were successfully picked

## Features in Detail

### Automatic Commit Ordering

Commits are **automatically reversed** before cherry-picking to maintain chronological order:
- The UI shows commits newest-first (natural Git log order)
- Cherry-pick applies them oldest-first (correct dependency order)
- You don't need to manually reorder commits

### Record Origin Option

The **Record Origin** checkbox (bottom left) controls whether cherry-picked commits include origin information:

- **Checked** (default): Adds `(cherry picked from commit <sha1>)` to commit messages
- **Unchecked**: Cherry-picks without adding origin information

This setting is saved and applied to all cherry-pick operations.

### Conflict Resolution

When conflicts occur during cherry-picking:

1. A dialog appears showing the conflicting commit
2. You can choose to:
   - **Resolve**: Opens merge tool for manual conflict resolution
   - **Abort**: Stops the cherry-pick operation completely

3. After resolving, the operation continues automatically

### Empty Commits

Some commits may already be applied or have no changes:

- The tool detects empty commits automatically
- You'll be prompted whether to skip or continue
- Common when commits were partially merged already

### Working with Submodules

If your repository uses submodules in composite mode:

- Submodule commits are included automatically
- Each submodule commit is cherry-picked to its respective directory
- Failures in submodules are reported separately

## Advanced Usage

### Filtering Strategies

**Filter Reverted Commits:**
- Useful when a branch contains both features and their reverts
- Automatically excludes commits with "This reverts commit" messages
- Keeps only the "forward progress" commits

**Pattern-Based Filtering:**
- Define regex or text patterns in Settings
- Filter out commits matching specific keywords (e.g., "WIP", "temp", "debug")
- Use case-insensitive text matching or powerful regex

**Apply Filters by Default:**
- Enable in Settings to automatically apply filters when loading commits
- Saves time on repeated workflows

### Branch Selection Tips

**Remote Branches:**
- Select remote branches (e.g., `origin/feature`) as source
- Useful for cherry-picking from shared branches
- No need to checkout locally first

**Complex Base Branch Selection:**
- Use merge-base commit as base branch for accurate comparisons
- Or use the target branch itself to see all source commits not yet in target

**Multiple Source Branches:**
- Close and reopen window to switch source branches
- Or use drag-and-drop for commits from multiple branches

### Keyboard Shortcuts

- **Alt+Click**: Toggle commit mark
- **Ctrl+A**: Select all commits (in log view)
- **Escape**: Close window
- Use standard navigation keys in the commit list

## Settings and Configuration

Access cherry-pick settings via the **Settings** button (gear icon):

### Cherry-Pick Tab Settings:

1. **Record Origin**: Include origin information in commit messages
2. **Filter Reverted Commits**: Enable automatic filtering of revert commits
3. **Filter Patterns**: Define text patterns or regex to filter commits
4. **Use Regex**: Toggle between simple text matching and regex patterns
5. **Apply Filter by Default**: Automatically apply filters when loading commits

These settings persist across sessions.

## Common Workflows

### Cherry-Pick an Entire Feature Branch

```
1. Source: feature/user-authentication
2. Base: main (or the branch point)
3. Target: release/2.0
4. Click "Select All"
5. Click "Cherry-Pick"
```

### Cherry-Pick Only Bug Fixes from a Branch

```
1. Source: develop
2. Base: release/1.9
3. Target: release/1.9-hotfix
4. Configure filter patterns: "feature", "enhancement"
5. Click "Select All"
6. Click "Filter Commits"
7. Review remaining commits
8. Click "Cherry-Pick"
```

### Pick Commits Between Release Branches

```
1. Source: release/1.9
2. Base: release/1.8
3. Target: release/2.0
4. Mark specific commits you want to backport
5. Click "Cherry-Pick"
```

## Limitations

1. **Target branch must be checked out**: Cannot cherry-pick to branches without working directories
2. **Same repository only**: Cross-repository cherry-picking not supported
3. **Source and target must differ**: Cannot cherry-pick to the same branch
4. **Linear application**: Commits are applied one-by-one, conflicts stop the process

## Troubleshooting

**Problem**: No commits shown after selecting branches
- **Solution**: Check that source and base branches are different. If source branch has no commits not in base, the list will be empty.

**Problem**: "Target branch not checked out" error
- **Solution**: Checkout the target branch first using your Git client or command line

**Problem**: Cherry-pick fails with conflict
- **Solution**: Resolve the conflict using the merge tool, then the operation will continue with remaining commits

**Problem**: Filter button does nothing
- **Solution**: Configure filter settings first in Settings → Cherry-Pick

**Problem**: Cannot find a branch in the dropdown
- **Solution**: Refresh branches or check that the branch exists. Use autocomplete by typing the branch name.

## Comparison with Drag and Drop

| Feature | Cherry Pick Window | Drag and Drop |
|---------|-------------------|---------------|
| **Best for** | Many commits, full branches | Few specific commits |
| **Interface** | Dedicated window | In-place, between log views |
| **Selection** | Mark commits with checkboxes | Multi-select in log view |
| **Filtering** | Built-in filter features | Manual selection only |
| **Commit review** | Detailed view with diff | Quick visual preview |
| **Speed** | Slower, more thorough | Faster, more direct |
| **Use case** | Planned, bulk operations | Ad-hoc, quick transfers |

**Recommendation**: 
- Use **Cherry Pick Window** for cherry-picking entire branches or when you need filtering
- Use **[Drag and Drop](CHERRY_PICK_DRAG_DROP.md)** for picking a few specific commits quickly

## See Also

- **[Cherry-Pick with Drag and Drop](CHERRY_PICK_DRAG_DROP.md)**: Quick method for picking individual commits
- **Branch Compare Window**: View branch differences side-by-side
- **Merge vs Cherry-Pick**: Understanding when to use each
- Git cherry-pick documentation: `git help cherry-pick`
