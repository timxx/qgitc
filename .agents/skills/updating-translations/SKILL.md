---
name: updating-translations
description: Use when QGitc UI text changes or the Chinese UI still shows English — regenerate qgitc/data/translations/zh_CN.ts from the sources with lupdate, translate every pending entry, and rebuild zh_CN.qm.
user-invocable: true
---

# Updating Translations

## Overview

`qgitc/data/translations/zh_CN.ts` is lupdate output: contexts, sources and locations are generated, and only the `<translation>` bodies are hand work. Regenerate before translating — lupdate renumbers locations and marks a changed source `unfinished`, discarding work done before it.

`scripts/ts_tool.py`, in this skill's directory, rewrites only the `<translation>` elements named by a translations file; the rest of the document keeps lupdate's formatting. Never edit the `.ts` XML by hand.

## Workflow

Run every command from the repository root.

### 1. Regenerate the .ts from the sources

```
python setup.py update_ts --no-obsolete
```

Completion: lupdate reports how many source texts are new, and `git diff --stat` lists `zh_CN.ts` as the only changed file. `--no-obsolete` drops the strings whose source is gone.

### 2. List the pending entries

```
python .agents/skills/updating-translations/scripts/ts_tool.py pending qgitc/data/translations/zh_CN.ts
```

The list is written to a JSON file, because long shell output is truncated — the command prints the count and the path instead. Read that file: it carries each pending entry's context, locations, `keySequence` hint and the `terminology` samples of its context.

Completion: the printed count is accounted for (lupdate's new strings plus what was already unfinished) and you have read the file.

### 3. Translate every pending entry

Write a translations JSON beside `pending.json`, at the path step 2 printed:

```json
{"translations": [
  {"context": "MainWindow", "source": "Open", "translation": "打开"},
  {"context": "MainWindow", "source": "F5", "translation": ""}
]}
```

- Copy `context` and `source` verbatim from `pending.json`. They are unescaped XML text, so `&Soft` is the key and `&amp;Soft` is not.
- `"translation": ""` deliberately leaves an entry empty; Qt then shows the source text. Use it for the keep class below and for nothing else.
- Match how the term is already translated: use the `terminology` samples, and search `zh_CN.ts` for the word when they do not settle it. Consistency beats a better word.
- Keep `{0}` and `%d` placeholders, keep the accelerator `(&X)` at the end of the Chinese text, and keep the source's own spaces and punctuation (`Parent: ` keeps its trailing space).

Completion: exactly one item per entry in `pending.json` — none skipped, none invented.

### 4. Apply and re-check

```
python .agents/skills/updating-translations/scripts/ts_tool.py apply qgitc/data/translations/zh_CN.ts <scratch>/translations.json
python .agents/skills/updating-translations/scripts/ts_tool.py pending qgitc/data/translations/zh_CN.ts --stdout
```

Completion: `apply` reports no unknown keys, and the pending list that follows holds only keep-class entries you emptied on purpose. Any other entry means step 3 was incomplete.

### 5. Rebuild the .qm

```
python .agents/skills/updating-translations/scripts/ts_tool.py build qgitc/data/translations
```

Completion: lrelease prints `0 unfinished`, which is the whole-workflow check — an entry left `unfinished` is one step 3 missed. A deliberately empty entry still counts as finished, so only `unfinished` signals missing work.

`zh_CN.qm` is gitignored and is a local build artifact; `zh_CN.ts` is the tracked file. `python qgitc.py log` shows the result in the UI.

## Keep class

Entries that stay empty on purpose, with Qt falling back to the source text:

- Key sequences — `F5`, `Shift+F3`, `Ctrl+Return`, `Ctrl+1`. `pending` marks them `"keySequence": true`.
- Product and window names — `QGitc`, `GitView`.

Every other entry with English source text is pending work.

## Common mistakes

| Mistake | Fix |
|---|---|
| Editing the `.ts` XML by hand | Regenerate with lupdate, then `ts_tool.py apply` |
| Translating a key sequence | `"translation": ""` for the keep class |
| Running lupdate after translating | Regenerate first; lupdate marks changed sources `unfinished` |
| Reading the pending list from the shell | Read the JSON file — long output is truncated |
| Treating `pending` as the finish line | `0 unfinished` from lrelease is the finish line |

## Troubleshooting

- `Missing lupdate` or `Missing lrelease`: the `pyside6-*` tools are not on PATH. Reinstall PySide6 (`python -m pip install -r requirements.txt`) or put its `Scripts` directory on PATH.
- `apply` reports unknown keys: `context` and `source` must match the file exactly. Re-read `pending.json` rather than retyping them.
