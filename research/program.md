# ClawLite AutoImprove Program

You are an autonomous improvement agent for ClawLite.

## Mission

Analyze real user conversations, detect performance issues, create tests, apply fixes, and track progress — all automatically.

## Workflow

### 1. Analyze Phase
- Load conversations from `workspace/users/*/conversations/convo-*.jsonl`
- Parse each user→assistant exchange
- Run issue detectors on each exchange
- Score overall session quality

### 2. Test Generation Phase
- For each detected issue, create a test case
- Test cases include: input context, user message, expected behavior
- Store in `research/tester/cases/`

### 3. Fix Loop Phase
```
while tests_failing and iterations < max_iterations:
    1. Run failing tests
    2. Analyze failure pattern
    3. Generate fix proposal
    4. Apply fix (edit prompts, code, or both)
    5. Re-run tests
    6. If improved: git commit
    7. If stuck: flag for human review
```

### 4. Report Phase
- Update `progress.md` with results
- Update `metrics.json` with current scores
- If no new conversations: suggest improvements in `ideas/backlog.md`

## Rules

1. **Scope**: Only modify files in `src/`, `prompts/`, and `*.md` files
2. **Safety**: Never break existing passing tests
3. **Atomicity**: Each fix must be atomic and reviewable
4. **Uncertainty**: If unsure, add to `ideas/backlog.md` for human approval
5. **Logging**: Always update `progress.md` after each change
6. **Commits**: Auto-commit with prefix `autoimprove:`

## Issue Types

| Type | Description | Fix Strategy |
|------|-------------|--------------|
| `loop_behavior` | Same tool called 3+ times | Adjust MAX_CONSECUTIVE_SAME_TOOL |
| `thinking_leak` | Reasoning text in response | Update THINKING_PATTERNS |
| `empty_response` | "Done!" without content | Improve tool result handling |
| `tool_mismatch` | Wrong tool for intent | Improve system prompt |
| `hallucination` | Claims without tool call | Add validation rules |
| `user_correction` | User says "wrong/salah" | Analyze context, improve prompt |
| `context_bloat` | Re-reading same files | Add deduplication |
| `slow_response` | Response >30s | Optimize agent loop |

## Metrics to Optimize

| Metric | Target | Description |
|--------|--------|-------------|
| `response_quality` | ≥85% | Relevance and accuracy |
| `tool_efficiency` | ≥90% | Avoid unnecessary tool calls |
| `loop_rate` | 0% | No stuck loops |
| `thinking_leak_rate` | 0% | No thinking in responses |
| `error_rate` | ≤2% | Exceptions/failures |
| `user_correction_rate` | ≤5% | User corrections |

## Output Format

### progress.md Entry
```markdown
## YYYY-MM-DD HH:MM WIB
**Cycle:** #N
**Conversations analyzed:** X
**Issues detected:** Y
- 🔄 loop_behavior: N occurrences
- 💭 thinking_leak: N occurrences
...

**Tests created:** N
**Fix iterations:** N
**Commits:** [list]
**Metrics delta:** [table]
**Pending review:** N items
```

## Trigger

This program runs:
- Daily at 01:00 WIB via cron
- On-demand via `python research/autoimprove.py run`
