# Cherry-Pick with Drag and Drop

## Overview

The drag-and-drop feature allows you to cherry-pick commits between branches by simply dragging commits from one log view and dropping them onto another. This is ideal when you need to pick **a few specific commits** quickly and interactively.

> **Note:** If you want to cherry-pick an entire branch or many commits at once, consider using the [Cherry Pick Window](CHERRY_PICK_WINDOW.md) instead.

## When to Use Drag and Drop

Use drag-and-drop cherry-picking when you need to:

- Pick **one or a few specific commits** from a branch
- Visually select commits you want to transfer
- Quickly cherry-pick commits without opening additional windows
- Pick commits from different branches in a flexible, ad-hoc manner

## Prerequisites

Before you can cherry-pick commits using drag and drop:

1. **The target branch must be checked out** - You can only drop commits onto a branch that has been checked out to a working directory
2. **Both repositories must share the same origin** - You can cherry-pick between different clones/working directories of the same repository
3. **Source and target branches must be different** - You cannot cherry-pick commits to the same branch

## How to Use

### Step 1: Open Both Source and Target Branches

1. Open the main log window showing your **target branch** (where you want to apply the commits)
2. Open a second log window or branch comparison window showing your **source branch** (where the commits are)

You can open multiple log windows by:
- Using the Compare Mode (View → Compare Mode)
- Opening multiple repository windows

### Step 2: Select Commits to Cherry-Pick

In the source branch log view:

- **Single commit**: Simply click on the commit you want to cherry-pick
- **Multiple commits**: 
  - Hold **Ctrl** and click to select individual commits
  - Hold **Shift** and click to select a range of commits
  - **Ctrl+A** to select all commits

### Step 3: Drag the Commits

1. Click and hold on one of the selected commits
2. Start dragging - after moving the mouse a few pixels, you'll see a **preview** showing:
   - The short SHA of the selected commit(s)
   - The commit summary
   - A count indicator if multiple commits are selected (e.g., "+ 3 more")

### Step 4: Drop onto Target Branch

1. Drag the commits over to the target branch log view
2. As you hover over the target, you'll see an **animated drop indicator** showing:
   - A glowing line showing where the commits will be inserted
   - Arrow indicators on both sides
   - The line appears at the insertion point (typically after local changes or at HEAD)
3. Release the mouse button to execute the cherry-pick

### Step 5: Review Results

After dropping:

- The cherry-pick operation executes automatically for all selected commits
- Commits are applied in order from **oldest to newest**
- The target branch log view refreshes to show the newly applied commits
- Successfully picked commits are marked with a visual indicator in the source view

## Multi-Selection Behavior

You can cherry-pick multiple commits in a single drag-and-drop operation:

1. **Selecting multiple commits**:
   - **Ctrl+Click**: Add/remove individual commits to/from selection
   - **Shift+Click**: Select a continuous range of commits

2. **Dragging behavior**:
   - If you drag a **selected commit**, all selected commits are included
   - If you drag an **unselected commit**, only that commit is dragged

3. **Order of application**:
   - Commits are automatically applied from oldest to newest
   - This matches the natural Git cherry-pick order

## Handling Conflicts

If a conflict occurs during cherry-picking:

1. A conflict dialog will appear showing:
   - The commit that caused the conflict
   - Options to resolve the conflict
   - Conflict details

2. You can choose to:
   - **Resolve manually**: Opens the merge tool to resolve conflicts
   - **Abort**: Cancels the cherry-pick operation

3. After resolving conflicts, the operation continues with any remaining commits

## Record Origin Option

By default, cherry-picked commits record their origin in the commit message with a `(cherry picked from commit <sha1>)` line. This helps track where commits came from.

You can disable this in **Settings → Cherry-Pick → Record Origin**.

## Visual Feedback

The drag-and-drop feature provides rich visual feedback:

### Drag Preview
- Shows abbreviated SHA (first 7 characters)
- Displays the commit summary (first line)
- For multiple commits, shows "+ N more" indicator
- Semi-transparent badge follows your cursor

### Drop Indicator
- **Animated glowing line** shows where commits will be inserted
- **Arrow indicators** on both edges make the drop position clear
- **Smooth animations** for professional feel
- Automatically positions commits after local changes or at HEAD

### Status Markers
- Successfully cherry-picked commits are marked in the source view
- Failed commits remain unmarked
- Visual distinction helps track what was transferred

## Limitations

1. **Same repository origin**: Can only cherry-pick between branches that share the same Git repository origin URL (different clones of the same repo are supported)
2. **Same branch restriction**: Cannot drag commits to the same branch they came from
3. **Target must be checked out**: The target branch must have a working directory

## Advanced Tips

### Picking from Remote Branches
You can drag commits from remote branches (e.g., `origin/feature`) to your local checked-out branch. The commits are cherry-picked just like local branches.

### Working with Submodules
If you're using composite mode with submodules, the drag-and-drop will handle both main repository commits and submodule commits automatically.

### Cherry-Picking Between Repository Clones
You can cherry-pick commits between different working directories of the same repository:
- Open the same repository in multiple locations (e.g., `C:\repo` and `D:\repo-clone`)
- Both must be clones of the same origin repository
- Drag and drop commits between them
- The tool automatically uses patch-and-apply internally when needed

### Keyboard Shortcuts During Drag
- **Escape**: Cancel the drag operation (browser dependent)
- The drag operation uses standard OS drag-and-drop, so system shortcuts apply

## Troubleshooting

**Problem**: Cannot drag commits
- **Solution**: Ensure you're clicking on a valid commit (not a header or empty space)

**Problem**: Drop indicator doesn't appear
- **Solution**: Check that the target branch is checked out and you're not trying to drop on the same branch

**Problem**: "Cherry-pick Failed" error
- **Solution**: Check the error message - common issues include:
  - Target branch not checked out
  - Same source and target branch
  - Different repository origins (must be clones of the same repo)

**Problem**: Some commits fail to cherry-pick
- **Solution**: This is normal - commits may have conflicts or dependencies. Review the error messages and resolve conflicts manually if needed.

## Related Features

- **[Cherry Pick Window](CHERRY_PICK_WINDOW.md)**: For cherry-picking entire branches or many commits with filtering options
- **Compare Mode**: View differences between branches side-by-side
- **Markers**: Use Alt+Click to mark commits for later reference

## See Also

- Git cherry-pick documentation: `git help cherry-pick`
- Conflict resolution documentation
- Branch management documentation
