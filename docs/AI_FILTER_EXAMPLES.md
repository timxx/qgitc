# AI Filter Examples

This file provides examples of how to use the new AI-enhanced filter functionality.

## Basic Usage

1. **Traditional approach** (still works):
   ```
   --since='1 week ago' --author=John
   ```

2. **New AI approach**:
   ```
   @ai show commits by John from last week
   ```

## Comprehensive Examples

### Time-based Filtering

| Natural Language | Expected Git Options |
|-----------------|---------------------|
| `@ai commits from yesterday` | `--since='1 day ago'` |
| `@ai commits from last month` | `--since='1 month ago'` |
| `@ai commits since January 1st` | `--since='2024-01-01'` |
| `@ai commits between last Monday and Friday` | `--since='last Monday' --until='last Friday'` |

### Author-based Filtering

| Natural Language | Expected Git Options |
|-----------------|---------------------|
| `@ai commits by Alice` | `--author=Alice` |
| `@ai my commits` | `--author=<current_user>` |
| `@ai commits by John or Jane` | `--author=John\|Jane` |

### Limiting Results

| Natural Language | Expected Git Options |
|-----------------|---------------------|
| `@ai last 5 commits` | `-n 5` |
| `@ai first 10 commits` | `--reverse -n 10` |
| `@ai most recent commit` | `-n 1` |

### Content-based Filtering

| Natural Language | Expected Git Options |
|-----------------|---------------------|
| `@ai commits about bug fixes` | `--grep=bug` |
| `@ai commits mentioning feature` | `--grep=feature` |
| `@ai commits with fix in message` | `--grep=fix` |

### File-specific Filtering

| Natural Language | Expected Git Options |
|-----------------|---------------------|
| `@ai commits changing main.py` | `-- main.py` |
| `@ai recent changes to src directory` | `-- src/` |
| `@ai last 5 commits to README` | `-n 5 -- README.md` |

### Complex Combinations

| Natural Language | Expected Git Options |
|-----------------|---------------------|
| `@ai last 10 commits by Alice about bugs` | `-n 10 --author=Alice --grep=bug` |
| `@ai commits from last week changing Python files` | `--since='1 week ago' -- *.py` |
| `@ai recent merge commits` | `--merges --since='1 month ago'` |

## Tips for Better Results

1. **Be specific**: "commits from last week" is better than "recent commits"
2. **Use common terms**: "bug fixes" instead of "defect corrections"
3. **Mention timeframes clearly**: "last week", "yesterday", "since January"
4. **Specify file patterns**: "Python files" → `*.py`, "config files" → `*.conf`

## Fallback Behavior

If the AI cannot understand your query or generates invalid options:
- An error message will be shown
- The original query remains in the field
- You can edit it manually or try a different phrasing

## Performance Notes

- AI queries may take a few seconds to process
- A status message shows "Processing AI query..." during processing
- Regular git options are processed immediately as before

## Troubleshooting

### "AI service is currently unavailable"
- Check your AI model configuration in Preferences → LLM
- Ensure you have a valid API key or local LLM server running
- Try again in a few moments

### "AI could not generate valid filter options"
- Try rephrasing your query
- Be more specific about what you're looking for
- Use simpler, more direct language

### No response from AI
- Check your internet connection (for cloud AI services)
- Verify your API key is valid and not expired
- Check the application logs for detailed error information
