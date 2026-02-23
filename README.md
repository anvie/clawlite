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

### Option 1: Create from Template (recommended)

```bash
git clone https://github.com/anvie/clawlite.git
cd clawlite

# Create instance from template
./clawlite instances new villa-cs my-villa

# Follow the interactive wizard to configure
# Then start your instance
./clawlite instances start my-villa
```

### Option 2: Manual Setup

```bash
git clone https://github.com/anvie/clawlite.git
cd clawlite

# Run setup script (creates .env, copies templates)
./setup.sh

# Edit .env with your configuration
nano .env
```

The setup script will:
- Create `.env` from `.env.example`
- Copy templates to `workspace/`
- Create necessary directories

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

## CLI Commands

ClawLite provides a unified CLI for managing instances and templates:

```bash
# Run ClawLite directly (manual setup)
./clawlite run

# Send message via internal API
./clawlite send <user_id> <message>

# Skill management
./clawlite skill new <name> [-d "description"]

# Instance management
./clawlite instances new <template> <name>
./clawlite instances list
./clawlite instances start <name>
./clawlite instances stop <name>
./clawlite instances remove <name>
./clawlite instances path <name>

# Browse available templates
./clawlite templates list
```

## Configuration

ClawLite uses two config files:
- **`config.yaml`** - All settings (LLM, channels, access control, etc.)
- **`.env`** - Secrets only (API keys, tokens)

### config.yaml (main configuration)

```yaml
# LLM settings
llm:
  provider: openrouter  # ollama | openrouter | anthropic
  model: google/gemini-2.0-flash-001
  host: http://localhost:11434  # for ollama only
  timeout: 60

# Access control
access:
  allowed_users: []  # empty = everyone allowed
  admins: [tg_123456]  # bypass all restrictions

# Channel settings
channels:
  telegram:
    enabled: true
  whatsapp:
    enabled: false

# Agent behavior
agent:
  max_iterations: 10
  tool_timeout: 30
  total_timeout: 300

# Tool filtering (empty = all tools)
tools:
  allowed: []

# Conversation persistence
conversation:
  record: true
  retention_days: 7

logging:
  level: INFO
```

### .env (secrets only)

```env
# API Keys
OPENROUTER_API_KEY=sk-or-xxx
# ANTHROPIC_API_KEY=sk-ant-xxx

# Bot Tokens
TELEGRAM_TOKEN=123456:ABC-xxx
```

### Channel Examples

**Telegram only (default):**
```yaml
# config.yaml
channels:
  telegram:
    enabled: true
  whatsapp:
    enabled: false
```

**WhatsApp only:**
```yaml
# config.yaml
channels:
  telegram:
    enabled: false
  whatsapp:
    enabled: true
```

On first run, scan the QR code shown in logs with WhatsApp on your phone.

### LLM Provider Examples

**Ollama (local):**
```yaml
llm:
  provider: ollama
  model: llama3.2:3b
  host: http://localhost:11434
```

**OpenRouter (cloud):**
```yaml
llm:
  provider: openrouter
  model: google/gemini-2.5-pro-preview-03-25
```

**Anthropic:**
```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
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

### Web

| Tool | Description | Parameters |
|------|-------------|------------|
| `web_search` | Search the web (DuckDuckGo) | `query`, `max_results` |
| `web_fetch` | Extract readable content from URL | `url`, `max_chars` |

## Internal API

ClawLite runs an internal HTTP API on port 8080 for cron jobs and external integrations.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/send` | Send message to user |
| `POST` | `/api/prompt` | Run agent with prompt, send response |
| `GET` | `/api/health` | Health check |

### Usage

```bash
# Send a simple message
curl -X POST http://localhost:8080/api/send \
  -H "Content-Type: application/json" \
  -d '{"user_id": "tg_123456", "message": "Hello!"}'

# Run agent with prompt (LLM-powered response)
curl -X POST http://localhost:8080/api/prompt \
  -H "Content-Type: application/json" \
  -d '{"user_id": "tg_123456", "prompt": "What time is it?"}'
```

### Helper Scripts for Cron

```bash
# Simple message reminder
*/30 * * * * /path/to/clawlite-send tg_123456 "Time for a break!"

# LLM-powered cron (agent generates response)
0 8 * * * /path/to/clawlite-prompt tg_123456 "Good morning greeting"
```

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

## Instance & Template System

ClawLite supports creating multiple isolated instances from templates.

### Template Resolution

Templates are resolved in this order:

| Pattern | Resolution |
|---------|------------|
| `./my-template` | Local directory |
| `user/name` | `github.com/user/name-clawlite-tmpl` |
| `name` | `github.com/$CLAWLITE_TEMPLATE_NAMESPACE/name-clawlite-tmpl` |

Set your default namespace:
```bash
export CLAWLITE_TEMPLATE_NAMESPACE=myorg
```

### Creating an Instance

```bash
# From default namespace
./clawlite instances new villa-cs my-villa

# From specific user/org
./clawlite instances new someuser/hotel-cs my-hotel

# From local template
./clawlite instances new ./my-custom-template my-bot
```

The wizard will prompt for required variables defined in the template.

### Instance Lifecycle

```bash
# List all instances
./clawlite instances list
# NAME       STATUS    TEMPLATE    CREATED
# my-villa   stopped   villa-cs    2026-02-21

# Start/stop
./clawlite instances start my-villa
./clawlite instances stop my-villa

# Get path for manual editing
./clawlite instances path my-villa
# /home/user/.clawlite/instances/my-villa

# Remove (stops if running)
./clawlite instances remove my-villa
```

### Creating Custom Templates

Template structure:

```
my-template-clawlite-tmpl/
├── template.yaml          # Variables & metadata
├── .env.example           # Environment template
├── workspace/
│   ├── SOUL.md            # Agent persona (with {{VAR}} placeholders)
│   ├── AGENTS.md          # Operating rules
│   └── ...
├── skills/                # Optional: bundled skills
└── README.md
```

**template.yaml:**
```yaml
name: my-template
version: "1.0"
description: My custom agent template

variables:
  BOT_NAME:
    description: Name of the bot
    required: true
    example: "MyBot"
  
  API_KEY:
    description: API key for external service
    required: false
    secret: true

files:
  - workspace/SOUL.md
  - workspace/AGENTS.md
  - .env.example
```

Use `{{VARIABLE_NAME}}` placeholders in template files. The wizard replaces them during instance creation.

## Workspace Configuration

The `workspace/` directory contains configuration and user data:

| File | Purpose | Scope |
|------|---------|-------|
| `SOUL.md` | Bot persona and communication style | Shared |
| `AGENTS.md` | Bot rules and behavior guidelines | Shared |
| `TOOLS.md` | Tool notes, servers, common commands | Shared |
| `users/{id}/` | Per-user memory and preferences | Per-user |

Copy templates to get started:

```bash
cp templates/*.md workspace/
```

Edit these files to customize your bot's personality and behavior.

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

## First-Time Bot Setup

On first conversation (when `SOUL.md` contains `_UNCONFIGURED_`), the bot will:
1. Ask what to call itself (bot name)
2. Ask about its role (personal assistant, work helper, etc.)
3. Ask about preferred tone (casual, professional, etc.)
4. Save the configuration to `SOUL.md`

After setup, users can still modify `SOUL.md` anytime by asking the bot or using the `write_file` tool.

## Telegram Commands

- `/start` - Welcome message
- `/clear` - Clear conversation history
- `/tools` - List available tools
- `/workspace` - Show workspace contents

## Configuration Reference

### config.yaml (main configuration)

| Key | Description | Default |
|-----|-------------|---------|
| `llm.provider` | LLM provider (`ollama`, `openrouter`, `anthropic`) | `ollama` |
| `llm.model` | Model name/ID | `llama3.2:3b` |
| `llm.host` | Ollama server URL (ollama only) | `http://localhost:11434` |
| `llm.timeout` | Request timeout in seconds | `60` |
| `channels.telegram.enabled` | Enable Telegram channel | `true` |
| `channels.whatsapp.enabled` | Enable WhatsApp channel | `false` |
| `channels.whatsapp.session_dir` | WhatsApp session storage | `/data/whatsapp` |
| `access.allowed_users` | Allowed user IDs (empty = all) | `[]` |
| `access.admins` | Admin user IDs (bypass restrictions) | `[]` |
| `agent.max_iterations` | Max tool calls per turn | `10` |
| `agent.tool_timeout` | Seconds per tool execution | `30` |
| `tools.allowed` | Allowed tools (empty = all) | `[]` |
| `conversation.record` | Save conversations to files | `true` |
| `conversation.retention_days` | Auto-delete old files | `7` |
| `api.port` | Internal API server port | `8080` |
| `logging.level` | Log level | `INFO` |

### .env (secrets only)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_AUTH_TOKEN` | Anthropic OAuth token (alternative) |

### Infrastructure (Docker runtime)

| Variable | Description | Default |
|----------|-------------|---------|
| `WORKSPACE_PATH` | Workspace directory mount | `/workspace` |
| `SKILLS_DIR` | Skills directory mount | `/app/skills` |

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

**Set in config.yaml:**
```yaml
llm:
  provider: ollama
  host: http://192.168.1.100:11434
  model: llama3.2:3b
```

**Docker mode:** Also update `docker-compose.yml` if needed:
```yaml
extra_hosts:
  - "ollama-host:192.168.1.100"
```
Then use `host: http://ollama-host:11434` in config.yaml.

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
