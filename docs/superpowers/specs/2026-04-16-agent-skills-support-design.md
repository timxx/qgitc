# Agent Skills Support Design

## Goal
Add skills support to the QGitc agent framework by reusing the established skills architecture:
- discover and load skills from markdown files
- expose skill metadata to the model
- allow the model to invoke a dedicated skill tool
- inject full skill content only when selected
- enforce per-skill tool allowlists through the existing tool/permission flow

This design intentionally avoids preloading full skill content in the base system prompt.

## Scope
### In scope (v1)
- Skill data model and registry
- Skill discovery and markdown frontmatter parsing
- Skill invocation tool integrated into the existing agent loop
- Compact skills reminder in system prompt/context
- Runtime enforcement of skill-level allowed-tools constraints
- Unit tests for loader, registry, tool behavior, and loop integration

### Out of scope (v1)
- Forked skill execution with subagents
- Plugin-distributed skills
- New UI slash-command adapters beyond existing behavior

## Architecture Overview
### Core concept
Skills are prompt modules, not direct side-effect executors.
The model first sees a compact list of available skills (name, description, when-to-use).
When needed, it calls the Skill tool with a skill name and optional args.
The Skill tool loads and injects full skill content into the conversation as a meta message.
Then the normal assistant/tool loop continues.

### Flow
1. Agent setup loads skills into a registry.
2. Agent adds a short "available skills" reminder to system context.
3. Model decides whether a skill applies.
4. If yes, model calls Skill tool with `skill` + optional `args`.
5. Skill tool resolves the skill, substitutes `$ARGUMENTS`, and returns an injected meta message containing full skill instructions.
6. If skill specifies `allowed_tools`, the active tool allowlist is updated in tool context.
7. Agent continues execution under normal permission engine controls.

## Component Design
### 1. Skills package
Create `qgitc/agent/skills/` with:

- `types.py`
  - `SkillDefinition` dataclass with fields:
    - `name`, `description`, `content`
    - `aliases`, `source`, `loaded_from`
    - `when_to_use`, `argument_hint`
    - `user_invocable`, `disable_model_invocation`
    - `context`, `agent`, `model`, `effort`
    - `paths`, `allowed_tools`, `hooks`, `skill_root`

- `registry.py`
  - `SkillRegistry`:
    - `register(skill)`
    - `get(name_or_alias)`
    - `list_skills()`
    - `get_model_visible_skills()`
    - `clear()` for tests

- `loader.py`
  - parse YAML frontmatter from `SKILL.md`
  - map kebab-case and snake_case keys
  - create `SkillDefinition`
  - robust fallbacks when frontmatter parse fails

- `discovery.py`
  - load from user and project skill directories
  - precedence: user first, project second (project overrides by name)
  - optional additional directories for future extension/tests

- `prompt.py`
  - render compact skills reminder for system prompt:
    - skill name
    - one-line description
    - optional when-to-use

### 2. Skill tool
Create `qgitc/agent/tools/skill.py` as a regular agent tool:

- Name: `Skill`
- Input schema:
  - `skill: string` (required)
  - `args: string` (optional)

Behavior:
- Validate skill format and lookup in `SkillRegistry`
- Reject unknown skill
- Reject `disable_model_invocation` skills
- Normalize `/skill-name` and `skill-name` forms
- Expand content:
  - replace `$ARGUMENTS` when present
  - if args provided but placeholder missing, append `ARGUMENTS: ...`
  - support `${CLAUDE_SESSION_ID}` and `${CLAUDE_SKILL_DIR}` substitution where relevant
- Return tool result with:
  - success metadata
  - injected meta message containing expanded skill content
- If skill defines `allowed_tools`, write active allowlist into tool context extra state

### 3. Agent loop integration
Update the loop and context plumbing so skills work without special-case execution paths:

- Ensure `ToolContext.extra` carries:
  - `skill_registry`
  - mutable active allowlist state
- Register `Skill` tool alongside existing built-in tools
- Add compact skills reminder to the query system prompt/context before provider stream
- Enforce active allowlist before non-skill tool execution:
  - if allowlist exists and requested tool not in list, return tool error
  - permission engine still runs for allowed tools
- Keep all existing tool/result message semantics unchanged

### 4. Registration and wiring
- Load skill registry during chat/session setup
- Provide registry to agent loop execution context
- Add exports in `qgitc/agent/__init__.py` for new skills APIs used by callers/tests

## Error Handling
- Missing registry: Skill tool returns structured error, does not crash loop
- Unknown skill: explicit error with requested name
- Disabled model invocation: explicit error and guidance
- Invalid skill file/frontmatter: skip or degrade gracefully with logged warning
- Recursive repeated invocation in same turn chain: block and return concise error

## Security and Permissions
- Skill invocation does not bypass permissions
- Existing path and filesystem protections remain unchanged
- `allowed_tools` narrows permissions; it never broadens them
- Deny-by-default behavior remains with current permission engine policies

## Testing Strategy
### Unit tests
- Skills loader:
  - frontmatter parse success/failure
  - field mapping
  - description extraction fallback
- Skills registry:
  - name lookup
  - alias lookup
  - precedence behavior
- Skill tool:
  - valid invocation
  - unknown/disabled skill
  - argument substitution behavior
  - allowlist propagation

### Agent loop tests
- model triggers `Skill`, then uses injected guidance in next turn
- disallowed tool blocked when skill allowlist is active
- normal tools still run when allowed

### Integration smoke tests
- discovery from user/project skill directories
- compact reminder includes visible skills only

## Rollout Plan
### Phase 1
- Add skills package and tests
- Add skill tool and tests

### Phase 2
- Wire registry and tool into agent loop
- Add prompt reminder and allowlist enforcement
- Add integration tests

### Phase 3
- Validate in chat flow manually
- iterate on prompt format only if needed (no behavior change)

## Compatibility Notes
- Preserve existing tool APIs and event signals
- Keep changes additive to avoid regressions in current chat/tool flows
- Do not require UI changes for v1; backend support is sufficient

## Open Decisions Resolved
- Invocation style: hybrid lazy loading via Skill tool
- Prompt strategy: descriptions in prompt, full content on-demand
- Restriction model: reuse per-skill allowlist behavior from established skills patterns
- Initial execution mode: inline only for v1
