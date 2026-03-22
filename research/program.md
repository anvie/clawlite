# ClawLite AutoImprove Program

This system is **run entirely by Aisyah** (OpenClaw main agent). Aisyah analyzes conversations, detects issues, implements fixes, and tracks progress autonomously.

## Mission

Aisyah actively improves ClawLite agent performance by:
1. Analyzing real user conversations daily
2. Detecting performance issues using pattern matching
3. Implementing fixes directly in the codebase
4. Testing changes before committing
5. Tracking all improvements in progress.md

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

### 3. Fix Phase (Aisyah implements)
For each detected issue, Aisyah:
1. Evaluates if it's a real problem or false positive
2. Identifies the root cause in the codebase
3. Implements the fix (edit prompts, agent.py, tools, etc.)
4. Tests the fix locally if possible
5. Commits with descriptive message: `autoimprove: <description>`

### 4. Report Phase
After each cycle, Aisyah updates:
- `progress.md` — chronological log of changes
- `metrics.json` — current performance scores
- Notifies Robin if significant improvements made

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
