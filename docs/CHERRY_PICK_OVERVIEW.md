# Cherry-Pick Features Overview

This application provides two powerful methods for cherry-picking commits between branches. Choose the method that best fits your workflow.

## Quick Comparison

| Method | Best For | Key Features |
|--------|----------|------------|
| **[Drag and Drop](CHERRY_PICK_DRAG_DROP.md)** | **1-10 commits** | Fast, visual, in-place |
| **[Cherry Pick Window](CHERRY_PICK_WINDOW.md)** | **Entire branches** or **many commits** | Filtering, dedicated workspace |

## When to Use Each Method

### Use Drag and Drop When:
- ✅ You need to pick **just a few specific commits** (1-10)
- ✅ You want a **quick, visual workflow**
- ✅ You're already viewing both branches in log windows
- ✅ You want **immediate feedback** without extra windows

**Example:** "I need to pick those 3 bug fix commits from the feature branch to the release branch"

👉 **[Read Drag and Drop Documentation](CHERRY_PICK_DRAG_DROP.md)**

### Use Cherry Pick Window When:
- ✅ You want to cherry-pick an **entire branch**
- ✅ You need to pick **many commits** (10+)
- ✅ You want to **filter commits** (exclude reverts, pattern matching)
- ✅ You need a **dedicated workspace** to review commits carefully
- ✅ You want to see commits **not in base branch** clearly

**Example:** "I need to cherry-pick all commits from the feature branch except the reverted ones and WIP commits"

👉 **[Read Cherry Pick Window Documentation](CHERRY_PICK_WINDOW.md)**

## Both Methods Support:

✓ Multi-commit cherry-picking  
✓ Conflict resolution  
✓ Submodule handling  
✓ Record origin option  
✓ Visual feedback  
✓ Automatic commit ordering  

## Quick Start Guides

### Drag and Drop (30 seconds)
1. Open both source and target branch log views
2. Select commit(s) in source branch (Ctrl+Click for multiple)
3. Drag and drop onto target branch
4. Done! ✨

### Cherry Pick Window (2 minutes)
1. Open Git → Cherry-Pick
2. Select Source, Base, and Target branches
3. Mark commits to cherry-pick (or use Select All)
4. Optional: Apply filters to remove unwanted commits
5. Click Cherry-Pick button
6. Done! ✨

## Need Help?

- **Drag and Drop Issues?** See [Drag and Drop Troubleshooting](CHERRY_PICK_DRAG_DROP.md#troubleshooting)
- **Cherry Pick Window Issues?** See [Cherry Pick Window Troubleshooting](CHERRY_PICK_WINDOW.md#troubleshooting)
- **General Git Cherry-Pick Help?** Run `git help cherry-pick` in terminal

## Related Documentation

- Branch Compare Window
- Merge Tools
- Conflict Resolution
- Git Integration
