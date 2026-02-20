# ClawLite

A lightweight agentic AI assistant with multi-channel support. Connect via Telegram or WhatsApp, powered by LLMs with tool-calling capabilities.

## Features

- **Multi-channel** - Telegram and WhatsApp support (run one or both)
- **Multi-provider LLM** - Works with Ollama (local) or OpenRouter (cloud: Gemini, Claude, etc.)
- **Tool calling** - Can read/write files, search, and execute commands
- **Multi-user sessions** - Each user gets isolated persistent memory
- **Workspace isolation** - Only has access to configured workspace directory
- **Streaming** - Real-time thinking and response streaming
- **Docker ready** - Run in a sandboxed container with security constraints

## Quick Start

### Prerequisites

- Python 3.10+
- **Messaging:** Telegram bot token and/or WhatsApp (phone to scan QR)
- **LLM:** Ollama running (locally or remote) OR OpenRouter API key

### Setup

```bash
git clone https://github.com/anvie/clawlite.git
cd clawlite
cp .env.example .env
# Edit .env with your configuration
```

### Run with Docker (recommended)

```bash
docker compose up -d --build
docker logs -f clawlite-agent
```

### Run with Python

```bash
pip install -r requirements.txt
python -m src.main
```

## Channel Configuration

### Telegram Only (default)

```env
ENABLED_CHANNELS=telegram
TELEGRAM_TOKEN=your_bot_token_here
TELEGRAM_ALLOWED_USERS=123456,789012  # optional
```

### WhatsApp Only

```env
ENABLED_CHANNELS=whatsapp
WHATSAPP_SESSION_DIR=/data/whatsapp
WHATSAPP_ALLOWED_USERS=628xxx,628yyy  # optional
```

On first run, scan the QR code shown in logs with WhatsApp on your phone.

### Both Channels

```env
ENABLED_CHANNELS=telegram,whatsapp
TELEGRAM_TOKEN=your_bot_token_here
WHATSAPP_SESSION_DIR=/data/whatsapp
```

## LLM Configuration

### Option 1: Ollama (local/self-hosted)

```env
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

### Option 2: OpenRouter (cloud)

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_MODEL=google/gemini-2.5-pro-preview-03-25
```

See [OpenRouter Models](https://openrouter.ai/models) for available models.

## Available Tools

### File Operations

| Tool | Description | Parameters |
|------|-------------|------------|
| `read_file` | Read file contents | `path` |
| `write_file` | Create/update files | `path`, `content` |
| `list_dir` | List directory contents | `path` (default: `.`) |

### Shell Operations

| Tool | Description | Parameters |
|------|-------------|------------|
| `exec` | Execute allowed commands (cat, ls, grep, find, echo, date, head, tail, wc, curl) | `command` |
| `run_bash` | Run a bash script | `script` |
| `run_python` | Execute Python code | `code` |
| `list_processes` | List running processes | - |
| `kill_process` | Terminate a process | `target` (PID or name) |

### Search

| Tool | Description | Parameters |
|------|-------------|------------|
| `grep` | Search text in files (ripgrep) | `pattern`, `path`, `flags` (-i, -w, -l, -c) |
| `find_files` | Find files by glob pattern | `name_pattern`, `path`, `recursive`, `type` |

### Scheduling

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_cron` | List cron jobs | - |
| `add_cron` | Add a cron job | `schedule`, `command`, `comment` |
| `remove_cron` | Remove a cron job | `pattern` |

### Memory (User-Scoped)

| Tool | Description | Parameters |
|------|-------------|------------|
| `memory_log` | Append to today's daily log | `content` |
| `memory_read` | Read MEMORY.md or specific day | `date` (optional, YYYY-MM-DD) |
| `memory_update` | Append to long-term memory | `content` |
| `user_update` | Update user profile | `content` |

## Architecture

```
+------------------------------------------------------------------+
|                          ClawLite                                |
|  +------------------------------------------------------------+  |
|  |  Channel Layer                                             |  |
|  |    +-- Telegram Channel ------> Telegram API               |  |
|  |    +-- WhatsApp Channel ------> WhatsApp (neonize)         |  |
|  |           |                                                |  |
|  |           v                                                |  |
|  |  Context Loader (per-user)                                 |  |
|  |    |  - Load SOUL.md, AGENTS.md (shared)                   |  |
|  |    |  - Load USER.md, MEMORY.md (per-user)                 |  |
|  |    v                                                       |  |
|  |  Agent Loop                                                |  |
|  |    |                                                       |  |
|  |    +---> Tool Executor ---> ./workspace/users/{id}         |  |
|  |    |                                                       |  |
|  |    v                                                       |  |
|  |  LLM Client (multi-provider)                               |  |
|  |    +-- Ollama ---------------------------------> Local LLM |  |
|  |    +-- OpenRouter -----------------------------> Cloud LLM |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
```

## Multi-User Sessions

Each user gets their own isolated memory space:

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

## Telegram Commands

- `/start` - Welcome message
- `/clear` - Clear conversation history
- `/tools` - List available tools
- `/workspace` - Show workspace contents

## Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLED_CHANNELS` | Channels to enable (`telegram`, `whatsapp`) | `telegram` |
| `LLM_PROVIDER` | LLM provider (`ollama` or `openrouter`) | `ollama` |
| `TELEGRAM_TOKEN` | Bot token from @BotFather | - |
| `TELEGRAM_ALLOWED_USERS` | Allowed Telegram user IDs | empty (all) |
| `WHATSAPP_SESSION_DIR` | WhatsApp session storage | `/data/whatsapp` |
| `WHATSAPP_ALLOWED_USERS` | Allowed phone numbers | empty (all) |
| `ALLOWED_USERS` | Global fallback allowlist | empty (all) |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | `llama3.2:3b` |
| `OPENROUTER_API_KEY` | OpenRouter API key | - |
| `OPENROUTER_MODEL` | OpenRouter model ID | `google/gemini-2.5-pro-preview-03-25` |
| `WORKSPACE_PATH` | Workspace directory | `/workspace` |

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
