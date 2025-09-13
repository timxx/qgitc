# AI-Enhanced Git Log Filtering

This document describes the new AI-enhanced filtering functionality added to the git log filter options field (`leOpts`) in the main window.

## Overview

The filter options field now supports natural language queries using AI to generate appropriate git log command-line options. Users can simply prefix their question with `@ai` to use this feature.

## Usage

### Regular Git Log Filtering (unchanged)
You can still use traditional git log options directly:
```
--since='1 week ago'
-n 10
--author=John
--grep=bug
```

### AI-Powered Natural Language Queries (new)
Prefix your question with `@ai` to use natural language:
```
@ai show commits from last week
@ai last 10 commits by John
@ai commits about bug fixes
@ai changes since January
@ai recent commits to main.py
```

## How It Works

1. **Detection**: When you press Enter in the filter field, the system checks if the text starts with `@ai`
2. **AI Processing**: If detected as an AI query:
   - The query is sent to the configured AI model (using `AiModelProvider.createModel`)
   - A specialized system prompt instructs the AI to convert natural language to git log options
   - The AI response is processed and applied as filter options
3. **Fallback**: Regular git log options continue to work exactly as before

## Examples

| Natural Language Query | Generated Git Log Options |
|----------------------|---------------------------|
| `@ai show last 10 commits` | `-n 10` |
| `@ai commits from last week` | `--since='1 week ago'` |
| `@ai commits by John` | `--author=John` |
| `@ai commits about bug fixes` | `--grep=bug` |
| `@ai commits since January` | `--since='2024-01-01'` |
| `@ai last 5 commits with changes to main.py` | `-n 5 -- main.py` |

## UI Changes

- **Placeholder Text**: The filter field now shows a helpful placeholder that mentions both regular options and the `@ai` prefix
- **Status Messages**: When processing AI queries, status messages are shown to indicate progress
- **Error Handling**: If the AI service is unavailable or an error occurs, appropriate error messages are displayed

## Technical Implementation

### Key Components

1. **`_setupFilterAI()`**: Sets up the AI functionality and placeholder text
2. **`_handleAiFilterQuery(query)`**: Processes AI queries and communicates with the AI model
3. **`__onOptsReturnPressed()`**: Enhanced to detect and route AI queries vs regular filters
4. **AI Response Handlers**: Handle AI responses, errors, and completion

### AI Model Integration

- Uses the existing `AiModelProvider.createModel()` infrastructure
- Sends a specialized system prompt that instructs the AI to act as a Git expert
- Temperature set to 0.1 for consistent, deterministic responses
- Non-streaming mode for simpler processing

### Error Handling

- Service unavailable scenarios
- Invalid or empty AI responses  
- Network timeouts and errors
- Proper cleanup of AI model resources

## Configuration

The feature uses the existing AI model configuration from the application settings:
- Default LLM model selection
- Model-specific settings (API keys, endpoints, etc.)
- No additional configuration required

## Dependencies

- Requires the existing AI/LLM infrastructure (`llm.py`, `llmprovider.py`)
- Uses the same AI models configured for other features (commit message generation, etc.)
- No new external dependencies added
