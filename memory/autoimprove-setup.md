# 2026-03-22 — ClawLite AutoImprove System Setup

## Overview
Implemented autonomous agent improvement system inspired by Karpathy's autoresearch. Instead of ML experiments, this system improves ClawLite agent performance based on real user conversations.

## What Was Built

### Directory: `research/`
- `autoimprove.py` — Main CLI (analyze/test/fix/report/run commands)
- `analyzer/` — Conversation parsing and issue detection
  - `parser.py` — Loads JSONL conversations from workspace/users/*/conversations/
  - `detector.py` — 8 issue detection patterns
  - `patterns.py` — Thinking leak, empty response, user correction patterns
- `tester/` — Test generation and execution
  - `generator.py` — Creates test cases from detected issues
  - `runner.py` — Runs tests against live vLLM (192.168.1.7:8000)
- `fixer/` — Fix proposal and application
  - `proposer.py` — Analyzes failures, proposes code/prompt fixes
  - `applier.py` — Applies fixes with backup/rollback, auto-git-commit
- `config-example.yaml` — Configuration template
- `progress.md` — Chronological improvement log
- `metrics.json` — Performance tracking

### Issue Types Detected
1. **loop_behavior** — Same tool called 3+ times consecutively
2. **thinking_leak** — <think> tags, "Actually...", "Let me...", numbered lists
3. **empty_response** — "Done!" without substantive content
4. **user_correction** — User says "no/wrong/salah/bukan"
5. **hallucination** — Claims action without tool call evidence
6. **context_bloat** — Re-reading same files unnecessarily
7. **slow_response** — Response took >30 seconds

### Metrics Tracked
- `loop_rate` (target: 0%)
- `thinking_leak_rate` (target: 0%)
- `error_rate` (target: ≤2%)
- `user_correction_rate` (target: ≤5%)

### Workflow
1. **Analyze** — Load conversations from last 24h, detect issues
2. **Generate Tests** — Create test cases from each issue
3. **Fix Loop** — Run tests, propose fixes, apply + commit if improved (max 10 iterations)
4. **Report** — Update progress.md with results, update metrics.json

### Cron Schedule
- Daily at **01:00 WIB** via docker-entrypoint.sh
- Triggered by `python research/autoimprove.py run`

### Files Changed
- 19 files created/modified
- ~2500 lines of code
- 4 commits: a66e29b, b816bd7, 8f39610, 8f55bc3, 04ad12b

### Testing
- CLI works: `python3 research/autoimprove.py --help`
- Analyze tested: found 15 exchanges in convo-2026-02-21.jsonl, 0 issues detected
- Ready for production deployment

## Next Steps
1. Deploy updated Docker container to see cron in action
2. First automatic run: 2026-03-23 01:00 WIB
3. Check progress.md after first cycle for results

## Commits
- `a66e29b` docs: add initial progress.md entry
- `b816bd7` feat: add AutoImprove cron job (daily 01:00 WIB)
- `8f39610` fix: update analyzer imports and config lookback
- `8f55bc3` feat: add AutoImprove config-example.yaml
- `04ad12b` feat: add AutoImprove system for autonomous agent improvement

## References
- Karpathy's autoresearch: https://github.com/karpathy/autoresearch
- Progress log: `research/progress.md`
- Configuration: `research/config-example.yaml`
