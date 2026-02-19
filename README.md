# ClawLite

A lightweight agentic AI assistant. Telegram bot powered by Ollama LLMs with tool-calling capabilities.

## Features

- **LLM-powered** - Works with any Ollama model (reasoning models like Nanbeige work best)
- **Tool calling** - Can read/write files, search, and execute commands
- **Multi-user sessions** - Each user gets isolated persistent memory
- **Workspace isolation** - Only has access to configured workspace directory
- **Streaming** - Real-time thinking and response streaming to Telegram
- **Optional Docker** - Run directly with Python or in a sandboxed Docker container

## Quick Start

### Prerequisites

- Python 3.10+
- Ollama running (locally or remote)
- Telegram bot token from [@BotFather](https://t.me/BotFather)

### Setup

```bash
git clone https://github.com/anvie/clawlite.git
cd clawlite
cp .env.example .env
```

Configure `.env`:

```env
TELEGRAM_TOKEN=your_bot_token_here
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
ALLOWED_USERS=your_telegram_user_id
```

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
|  |  LLM Client ---------------------------------------|--+--> Ollama
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
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `llama3.2:3b` |
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

**Reasoning/thinking models** (best for agentic tasks):
- `nanbeige4.1:q8` - Chinese reasoning model
- `deepseek-r1:8b` - Good reasoning capability
- `qwq:32b` - Excellent for complex tasks

**General purpose:**
- `llama3.2:3b` - Fast and lightweight
- `mistral:7b` - Good balance

## License

MIT
