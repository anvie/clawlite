# ClawLite

A lightweight agentic AI assistant. Telegram bot powered by LLMs with tool-calling capabilities.

## Features

- **Multi-provider LLM** - Works with Ollama (local) or OpenRouter (cloud: Gemini, Claude, etc.)
- **Tool calling** - Can read/write files, search, and execute commands
- **Multi-user sessions** - Each user gets isolated persistent memory
- **Workspace isolation** - Only has access to configured workspace directory
- **Streaming** - Real-time thinking and response streaming to Telegram
- **Optional Docker** - Run directly with Python or in a sandboxed Docker container

## Quick Start

### Prerequisites

- Python 3.10+
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- **One of:**
  - Ollama running (locally or remote)
  - OpenRouter API key

### Setup

```bash
git clone https://github.com/anvie/clawlite.git
cd clawlite
cp .env.example .env
```

### Configure LLM Provider

**Option 1: Ollama (local/self-hosted)**

```env
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

**Option 2: OpenRouter (cloud)**

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_MODEL=google/gemini-2.5-pro-preview-03-25
```

See [OpenRouter Models](https://openrouter.ai/models) for available models.

### Run with Python

```bash
pip install -r requirements.txt
python -m src.bot
```

### Run with Docker (optional)

For sandboxed execution with security constraints:

```bash
docker-compose up -d --build
docker-compose logs -f
```

## Available Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Create/write files |
| `list_dir` | List directory contents |
| `exec` | Execute safe shell commands |
| `search_files` | Search text in files |
| `memory_log` | Append to today's memory log |
| `memory_read` | Read long-term or daily memory |
| `memory_update` | Update long-term memory |
| `user_update` | Update user profile |

## Security (Docker mode)

When running in Docker, additional security constraints apply:

- Non-root user inside container
- Read-only root filesystem
- No privilege escalation (`no-new-privileges`)
- All capabilities dropped
- Memory limited to 512MB
- CPU limited to 1 core
- Command allowlist (no rm -rf, sudo, etc.)
- Path traversal protection

## Telegram Commands

- `/start` - Welcome message
- `/clear` - Clear conversation history
- `/tools` - List available tools
- `/workspace` - Show workspace contents

## Architecture

```
+----------------------------------------------------------+
|                       ClawLite                           |
|  +----------------------------------------------------+  |
|  |  Telegram Bot                                      |--+--> Telegram API
|  |    |                                               |  |
|  |    v                                               |  |
|  |  Context Loader (per-user)                         |  |
|  |    |  - Load SOUL.md, AGENTS.md (shared)           |  |
|  |    |  - Load USER.md, MEMORY.md (per-user)         |  |
|  |    v                                               |  |
|  |  Agent Loop                                        |  |
|  |    |                                               |  |
|  |    +---> Tool Executor ---> ./workspace/users/{id} |  |
|  |    |                                               |  |
|  |    v                                               |  |
|  |  LLM Client (multi-provider)                       |  |
|  |    +-- Ollama ----------------------------------|--+--> Local LLM
|  |    +-- OpenRouter -----------------------------|--+--> Cloud LLM
|  +----------------------------------------------------+  |
+----------------------------------------------------------+
```

## Multi-User Sessions

Each Telegram user gets their own isolated memory space:

```
workspace/
├── SOUL.md              # Shared bot persona
├── AGENTS.md            # Shared bot rules
├── TOOLS.md             # Shared tool notes (optional)
└── users/
    └── {user_id}/
        ├── USER.md      # Info about this user
        ├── MEMORY.md    # Long-term memory
        └── memory/
            └── YYYY-MM-DD.md  # Daily conversation logs
```

**How it works:**
- Shared files (`SOUL.md`, `AGENTS.md`) define the bot's personality and rules
- User folders are auto-created on first message
- Memory tools read/write to the user's own folder
- Context is loaded per-user: shared files + user's files

**Memory tools:**
- `memory_log` - Append notes to today's daily log
- `memory_read` - Read `MEMORY.md` or a specific day's log
- `memory_update` - Append to long-term memory
- `user_update` - Update user profile (`USER.md`)

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_TOKEN` | Bot token from @BotFather | required |
| `LLM_PROVIDER` | LLM provider (`ollama` or `openrouter`) | `ollama` |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | `llama3.2:3b` |
| `OPENROUTER_API_KEY` | OpenRouter API key | - |
| `OPENROUTER_MODEL` | OpenRouter model ID | `google/gemini-2.5-pro-preview-03-25` |
| `ALLOWED_USERS` | Comma-separated user IDs | empty (all allowed) |
| `WORKSPACE_DIR` | Workspace directory | `/workspace` |
| `TRANSLATION_ENABLED` | Enable ID↔EN translation | `false` |

## Remote Ollama

If Ollama runs on a different machine:

**Python mode:** Set `OLLAMA_HOST=http://192.168.1.100:11434` in `.env`

**Docker mode:** Update `docker-compose.yml`:

```yaml
extra_hosts:
  - "ollama-host:192.168.1.100"
```

And set `OLLAMA_HOST=http://ollama-host:11434` in `.env`.

## Recommended Models

**OpenRouter (cloud):**
- `google/gemini-2.5-pro-preview-03-25` - Excellent reasoning, tool use
- `anthropic/claude-sonnet-4` - Great for agentic tasks
- `openai/gpt-4o` - Good all-rounder

**Ollama (local) - Reasoning models:**
- `nanbeige4.1:q8` - Chinese reasoning model
- `deepseek-r1:8b` - Good reasoning capability
- `qwq:32b` - Excellent for complex tasks

**Ollama (local) - General purpose:**
- `llama3.2:3b` - Fast and lightweight
- `mistral:7b` - Good balance

## License

MIT
