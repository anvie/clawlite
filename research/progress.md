# ClawLite AutoImprove Progress

This file tracks all improvement cycles chronologically. Each entry documents analyzed conversations, detected issues, created tests, applied fixes, and metric changes.

---

<!-- New entries will be prepended below this line -->
## 2026-03-24 01:00 WIB
**Cycle:** #10 — Analysis + Aisyah Review
**Conversations analyzed:** 1 (13 exchanges)
**Issues detected:** 5
- ✋ user_correction: 4
- 📚 context_bloat: 1

**Fix proposals generated:** 4 (all generic - not applied)
**Status:** ✅ Reviewed by Aisyah

**Current Metrics:**
| Metric | Value | Target | Trend |
|--------|-------|--------|-------|
| loop_rate | 0.0% | 0% | ✓ |
| thinking_leak_rate | 0.0% | 0% | ✓ |
| error_rate | 0.0% | 2% | ✓ |
| user_correction_rate | 30.8% | 5% | ⚠️ regression |

**Aisyah's Root Cause Analysis:**
1. **Photo timing misunderstanding** — User asked "kirim foto NANTI barengan sama reminder" but agent sent immediately. This is actually a **feature limitation**: ClawLite reminders don't support attachments. Would need code change to add `attachment` field to reminder system.

2. **False tool claims** — Agent said "Sudah saya atur semuanya" without actually calling add_reminder. Existing anti-hallucination rules should have caught this, but didn't trigger for future-tense claims ("sudah atur" = present perfect, not past with evidence).

3. **User identity not retained** — Agent didn't know user's name. USER.md existed but wasn't being read in context. The agent self-corrected by saving the name when told.

4. **Initial error response** — First "halo" got error, user had to retry. Likely transient API/runtime issue.

**Decision:** No auto-fixes applied. Issues require:
- Feature work (reminder attachments) — needs dev planning
- Prompt refinement (anti-hallucination for future-tense claims) — needs careful wording
- User context loading — verify USER.md is in system prompt context

**Backlog cleared** (proposals too generic to be actionable)

**Next Steps for Robin:**
1. Consider adding attachment support to reminder system
2. Review prompt for anti-hallucination coverage of "akan" / "sudah atur" patterns
3. Verify USER.md loading in agent startup

---


## 2026-03-23 01:15 WIB
**Cycle:** #7 — AutoImprove System Upgrade
**Enhancement:** System now fixes ClawLite core, not just analyzer

**Changes:**
1. **`program.md`** — Updated to clarify fix targets (production + dev)
2. **`config.yaml`** — Added `fix_targets` section with paths
3. **`fixer/clawlite_fixer.py`** — NEW module for ClawLite core fixes:
   - `apply_to_production()` — Apply to running container via docker cp
   - `apply_to_dev()` — Apply to dev repo templates/src
   - `add_section_to_agents_md()` — Add rules to AGENTS.md
   - `update_agent_py_constant()` — Update constants in agent.py
   - `add_thinking_pattern()` — Add patterns to strip
   - `git_commit_and_push()` — Commit & push to GitHub

**Fix Flow:**
```
Issue Detected → Analyze Root Cause → Generate Fix
      ↓
Apply to Production (immediate effect via docker cp)
      ↓
Apply to Dev Repo (for future instances)
      ↓
Git Commit & Push
```

---

## 2026-03-23 01:10 WIB
**Cycle:** #6b — ClawLite Core Fixes
**Issues addressed:** 5 user_correction, 3 loop_behavior

**Root Cause Analysis:**
From conversation analysis, main issues were:
1. Wrong reminder time parsing ("malam ini" → set for tomorrow instead of today)
2. Duplicate reminders created instead of updating existing
3. User had to repeat/correct multiple times

**Fixes Applied to AGENTS.md:**
1. **Time Parsing Rules** — Explicit definitions:
   - "malam ini" = TODAY evening
   - "besok malam" = TOMORROW evening
   - "10 menit lagi" = NOW + 10 minutes

2. **Duplicate Prevention** — New workflow:
   - Call `list_reminders` BEFORE creating new
   - Check for similar existing reminders
   - Update existing instead of creating duplicates

3. **Don't Over-Create** — One reminder per request

**Deployment:**
- ✅ Applied to running `clawlite-general` container
- ✅ Updated template for future instances

---

## 2026-03-23 01:00 WIB
**Cycle:** #6 — Parser Bug Fix
**Conversations analyzed:** 2 (53 exchanges)
**Initial issues detected:** 33
- 👻 hallucination: 28 (FALSE POSITIVES)
- ✋ user_correction: 5

**Root Cause Analysis:**
The analyzer was reporting 28 false positive hallucinations because the parser wasn't reading structured `tool_calls` from JSONL correctly. It was trying to extract tool calls from response text using regex patterns like `<tool_call>` tags, but ClawLite stores tool calls as a JSON array in the `tool_calls` field.

Example: Response says "Sudah kirim foto" with actual `tool_calls: [send_file]` → flagged as hallucination because `send_file` wasn't in regex patterns.

**Fixes Applied:**
1. **Parser fix** (`parser.py`): Added `parse_structured_tool_calls()` to read the `tool_calls` JSON field directly
2. **Detector fix** (`detector.py`): Expanded `EVIDENCE_TOOLS` set to include all ClawLite action tools:
   - `send_file` (was missing!)
   - `memory_update`, `user_update`, `memory_log`
   - `add_cron`, `remove_cron`
   - `add_reminder`, `edit_reminder`, `delete_reminder`
   - `web_search`, `web_fetch`
   - `run_bash`

**After Fix:**
- 👻 hallucination: 0 ✅
- ✋ user_correction: 5
- 🔄 loop_behavior: 3
- 📚 context_bloat: 1
- Total: 9 real issues (down from 33 false positives)

**Commits:** 1 commit (`706fcd5`)
**Tests:** All 80 ClawLite tests passing

**Next Steps:**
- Review the 5 user corrections and 3 loop behaviors for potential prompt improvements
- Consider adding unit tests for the autoimprove analyzer

---

## 2026-03-22 13:05 WIB
**Cycle:** #5 — Production Analysis
**Conversations analyzed:** 1 (real user conversation)
**Issues detected:** 7
- 👻 hallucination: 5 (agent invented phone numbers, addresses, claimed actions without evidence)
- ✋ user_correction: 2 ("Itu toko komputer, bukan pet shop")

**Root Cause Analysis:**
Agent made up information that didn't exist:
1. Invented phone "021-555-1234"
2. Made up address "Jl. Raya Pet Shop No. 123"
3. Invented email "info@bintanglandak.com"
4. Claimed "Sudah kirim foto" without actual send

**Fix Applied:**
- ✅ Added **Anti-Hallucination Rules** to AGENTS.md in production container
- Rules include: never invent data, only state facts from tools, be honest about limitations
- Applied via `docker cp` to running `clawlite-general` container

**Impact:**
Agent will now be explicitly instructed to NOT make up information and to admit when data is unavailable.

---
## 2026-03-22 13:02 WIB
**Cycle:** #5 — Analysis Only (Awaiting Aisyah Review)
**Conversations analyzed:** 1
**Issues detected:** 7
- 👻 hallucination: 5
- ✋ user_correction: 2

**Fix proposals generated:** 7
**Status:** ⏳ Awaiting Aisyah's review

**Current Metrics:**
| Metric | Value |
|--------|-------|
| loop_rate | 0.0% |
| thinking_leak_rate | 0.0% |
| error_rate | 50.0% |
| user_correction_rate | 20.0% |

---


## 2026-03-22 12:45 WIB
**Cycle:** #4 — Test Run (Aisyah Manual)
**Conversations analyzed:** 2 (1 real + 1 synthetic test)
**Issues detected:** 5
- 💭 thinking_leak: 2 (patterns already exist in agent.py)
- ✋ user_correction: 1
- 📚 context_bloat: 1
- 🔄 loop_behavior: 1

**Fix Applied:**
- ✅ Reduced `MAX_CONSECUTIVE_SAME_TOOL` from 4 to 3 in `src/agent.py`
- ℹ️ thinking_leak patterns ("Let me", "Actually") already implemented
- ⏸️ user_correction: prompt improvement deferred (need more samples)

**Commit:** `3556022` autoimprove: reduce MAX_CONSECUTIVE_SAME_TOOL from 4 to 3

**Notes:**
- Test conversation created to verify detector works
- Real conversations (tg_76639539) had 0 issues — ClawLite performing well!
- Synthetic issues correctly detected and fix proposed

---
## 2026-03-22 12:41 WIB
**Cycle:** #3 — Analysis Only (Awaiting Aisyah Review)
**Conversations analyzed:** 2
**Issues detected:** 5
- 💭 thinking_leak: 2
- ✋ user_correction: 1
- 📚 context_bloat: 1
- 🔄 loop_behavior: 1

**Fix proposals generated:** 4
**Status:** ⏳ Awaiting Aisyah's review

**Current Metrics:**
| Metric | Value |
|--------|-------|
| loop_rate | 5.9% |
| thinking_leak_rate | 11.8% |
| error_rate | 0.0% |
| user_correction_rate | 5.9% |

---

## 2026-03-22 12:37 WIB
**Cycle:** #2 — Analysis Only (Awaiting Aisyah Review)
**Conversations analyzed:** 1
**Issues detected:** 0
- ✅ No issues detected

**Fix proposals generated:** 0
**Status:** ⏳ Awaiting Aisyah's review

**Current Metrics:**
| Metric | Value |
|--------|-------|
| loop_rate | 0.0% |
| thinking_leak_rate | 0.0% |
| error_rate | 0.0% |
| user_correction_rate | 0.0% |

---


## 2026-03-22 11:30 WIB
**Cycle:** #0 — System Setup
**Status:** ✅ Complete

**Implementation:**
- Created `research/` directory with full AutoImprove system
- Analyzer module: conversation parsing, issue detection (8 pattern types)
- Tester module: test generation, vLLM-based test runner
- Fixer module: fix proposal, auto-commit with rollback support
- CLI: analyze, test, fix, report, run commands
- Cron job: daily at 01:00 WIB via docker-entrypoint.sh

**Issue Types Tracked:**
- 🔄 loop_behavior — same tool called 3+ times
- 💭 thinking_leak — reasoning text in responses
- 📭 empty_response — "Done!" without content
- ✋ user_correction — user says "wrong/salah"
- 👻 hallucination — claims without tool evidence
- 📚 context_bloat — re-reading same files
- 🐢 slow_response — >30s response time

**Metrics Tracked:**
- loop_rate (target: 0%)
- thinking_leak_rate (target: 0%)
- error_rate (target: ≤2%)
- user_correction_rate (target: ≤5%)

**Files Created:** 17 files, ~2500 lines of code
**Commits:** 4 commits to anvie/clawlite repo

**Next Steps:**
1. Deploy updated Docker image to see cron in action
2. First automatic run: tomorrow at 01:00 WIB
3. Check progress.md after first cycle

---
