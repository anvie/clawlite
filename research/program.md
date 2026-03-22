# ClawLite AutoImprove Program

This system is **judged by Aisyah** (OpenClaw main agent). The cron job generates analysis reports, but Aisyah reviews and decides which fixes to apply.

## Mission

Analyze real user conversations, detect performance issues, generate reports for Aisyah to review. Aisyah then decides which fixes to implement.

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

### 3. Report Phase (Automated)
- Update `progress.md` with analysis results
- Update `metrics.json` with current scores
- Generate improvement proposals in `ideas/backlog.md`
- **DO NOT auto-apply fixes** — wait for Aisyah's review

### 4. Review Phase (Aisyah)
Aisyah reviews the analysis and decides:
- Which issues are real problems vs false positives
- Which proposed fixes to implement
- Whether to create/update test cases
- When to commit changes

### 5. Fix Phase (Aisyah-initiated)
Only after Aisyah's approval:
```
1. Run test suite
2. Apply approved fixes
3. Verify tests pass
4. Git commit with proper message
```

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
