# Patch Review Skill Refactor Design

Date: 2026-04-17
Status: Draft approved in chat, pending final file review
Scope: Remove dedicated code review mode and refactor review flow to use a built-in patch-review skill in Agent mode.

## Objective

Refactor code review so users do not need to switch to a separate mode.

1. Add a built-in skill bundled in the wheel at qgitc/data/skills/patch-review/SKILL.md.
2. Make existing code review entry points execute patch-review directly in Agent mode.
3. Allow natural-language and slash-command reuse of the same skill.
4. Remove AiChatMode.CodeReview and remove legacy code review prompt constants.
5. Keep naming camelCase for all newly introduced identifiers.

## Non-Goals

1. No broad redesign of AgentLoop.
2. No refactor of general tool permission semantics.
3. No full rewrite of slash command architecture.
4. No behavior expansion beyond patch and diff review.

## Current State Summary

Current review flow has dedicated mode branching:

1. AiChatMode.CodeReview exists and is used by code review entry points.
2. CODE_REVIEW_PROMPT wraps incoming diff content before sending.
3. CODE_REVIEW_SYS_PROMPT exists but is no longer the active system prompt path under agent refactor.
4. Users effectively rely on a dedicated review entrance and mode switching logic.

This duplicates behavior that can now be represented as a reusable skill.

## Proposed Architecture

### 1. Built-in skill packaging

1. Add directory qgitc/data/skills/patch-review/.
2. Add file qgitc/data/skills/patch-review/SKILL.md.
3. Skill metadata:
- name: patch-review
- aliases: code-review, review
- user_invocable: true
- argument_hint describes unified diff or patch input
4. Skill body contains the review instructions currently encoded by legacy code review prompts, adapted for skill invocation.

### 2. Skill registry loading

1. Keep load_skill_registry contract unchanged.
2. Resolve built-in skills directory from dataDirPath() + "/skills".
3. Pass that path through additional_directories when creating skill registry.
4. Mark loaded built-in skills with source label builtinSkills for observability.

### 3. Entry-point execution path

Existing code review UI entry points remain intact from UX perspective.

1. Continue collecting commit or staged diff exactly as today.
2. Instead of requesting AiChatMode.CodeReview, execute patch-review directly.
3. Use Agent mode for execution.
4. Preserve immediate-start behavior for review entrance.

### 4. Natural-language and slash reuse

1. patch-review can be model-invoked in normal Agent chat when user asks for review.
2. Slash aliases like /review and /code-review resolve to patch-review.
3. Users can still provide a patch file content directly and get the same review behavior.

## Naming and Style Rules

All newly introduced code should follow project-preferred camelCase.

1. Prefer names such as builtinSkillsDir, builtinSkill, loadBuiltinSkillsDir.
2. Avoid introducing new snake_case helper names unless required by existing external API contracts.
3. Keep existing mixed-style legacy names untouched unless directly needed for this change.

## Removal Plan

### 1. Mode removal

1. Remove AiChatMode.CodeReview from llm enum.
2. Update all call sites to use Agent mode where review is needed.
3. Remove dead mode-branch logic in request construction.

### 2. Prompt removal

1. Remove CODE_REVIEW_SYS_PROMPT.
2. Remove CODE_REVIEW_PROMPT.
3. Keep shared repo guidance text where needed by skill content.

## Data Flow

### A. Existing review entrance

1. UI action collects diff and optional context metadata.
2. App starts Agent-mode request.
3. Built-in patch-review skill is executed directly with provided argument.
4. Skill performs focused patch review and returns formatted findings.

### B. Natural-language path

1. User asks for patch review in regular Agent chat.
2. Model chooses patch-review skill (or user invokes alias).
3. Same skill content and behavior are used.

## Error Handling

1. If diff content is missing, return concise instruction asking for unified diff or patch.
2. If repo or file context is ambiguous, skill follows minimal read-only tool lookup behavior before reporting.
3. If invocation cannot proceed safely, report what additional context is required.

## Testing Strategy

Add or update tests to cover:

1. Built-in skill loading from dataDirPath()/skills via additional_directories.
2. Built-in skill source tagging as builtinSkills.
3. Code review entry path executes patch-review directly in Agent mode.
4. No remaining dependency on AiChatMode.CodeReview.
5. Removal of code-review prompt constants does not break startup imports.
6. Alias resolution for code-review or review maps to patch-review.

## Rollout Plan

1. Add built-in skill folder and SKILL.md.
2. Wire built-in skills path into skill registry construction.
3. Switch code review entry points to direct skill execution in Agent mode.
4. Remove CodeReview mode and prompt constants.
5. Update and run targeted tests.
6. Run full test suite before merge.

## Risks and Mitigations

1. Risk: direct skill execution path diverges from normal chat flow.
- Mitigation: route through the same skill invocation mechanism used by agent tools.

2. Risk: packaged data path differences across environments.
- Mitigation: use dataDirPath() consistently for runtime location.

3. Risk: legacy tests or UI labels rely on removed enum member.
- Mitigation: update references and keep user-visible entry behavior unchanged.

## Acceptance Criteria

1. No AiChatMode.CodeReview remains.
2. No CODE_REVIEW_SYS_PROMPT or CODE_REVIEW_PROMPT remains.
3. Built-in patch-review skill is packaged under qgitc/data/skills/patch-review/SKILL.md.
4. Existing review entrance triggers immediate Agent-mode patch review.
5. Natural-language and slash command paths can invoke the same skill.
6. New or changed identifiers introduced by this refactor follow camelCase.
