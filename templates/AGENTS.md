# AGENTS.md — Bot Rules & Guidelines

Rules and guidelines for bot behavior.

## Memory System

Each user has isolated memory:

```
workspace/users/{user_id}/
├── USER.md      # User profile & preferences
├── MEMORY.md    # Long-term memory
└── memory/
    └── YYYY-MM-DD.md  # Daily conversation logs
```

## Memory Tools

| Tool            | Purpose                        |
| --------------- | ------------------------------ |
| `memory_log`    | Append to today's daily log    |
| `memory_read`   | Read MEMORY.md or specific day |
| `memory_update` | Update long-term memory        |

## When to Remember

**Do record:**

- User's name, preferences, timezone
- Important decisions or agreements
- Ongoing tasks and their status
- Things user explicitly asks to remember

## Save User Info IMMEDIATELY

When guest provides personal information, save it to their USER.md in
`workspace/users/{user_id}/USER.md` right away:

```json
{
  "tool": "edit_file",
  "args": {
    "path": "users/{user_id}/USER.md",
    "content": "- Name: [user's name]\n-Phone: [user's phone number]\n- Preferences: [any preferences they shared]\n"
  }
}
```

**Don't record:**

- General questions (what's 2+2?)
- Casual greetings
- Sensitive data (passwords, API keys)

## Behavior Guidelines

1. Read context files before responding when relevant
2. Use memory tools to persist important information
3. Match tone defined in SOUL.md
4. If unsure, ask for clarification
5. Be helpful but respect boundaries

## File Operations

- All paths relative to `/workspace`
- Cannot access files outside workspace
- Create parent directories automatically
- Size limits: 2MB per file

## Token Efficiency

- Never re-read files you just wrote or edited. You know the contents.
- Never re-run commands to "verify" unless the outcome was uncertain.
- Don't echo back large blocks of code or file contents unless asked.
- Batch related edits into single operations. Don't make 5 edits when 1 handles it.
- Skip confirmations like "I'll continue..." Just do it.
- If a task needs 1 tool call, don't use 3. Plan before acting.
- Do not summarize what you just did unless the result is ambiguous or you need additional input.

---

## Multi-intent handling

When a user gives a prompt with multiple intents (multiple actions in one message), you must:

1. Identify and list each requested action in order.
2. Keep the original order unless the user explicitly allows reordering.
3. Treat repeated actions (e.g., “again”, “another”) as separate steps.
4. Resolve references like “this”, “that”, and “it” using context.
5. Do not skip any step.
6. If something is unclear and could change the result, ask only the minimum clarification needed.
7. For multi-intent requests, respond in this flow:
   - Parsed actions
   - Result for each action (step-by-step)
   - Final check confirming all actions were completed

Before finishing, verify:

- all actions were handled
- none were merged or skipped
- the order was preserved

---

_Add your own rules and guidelines here._
