# ClawLite

A lightweight agentic AI assistant. Telegram bot powered by Ollama LLMs with tool-calling capabilities, running in a secure Docker container.

## Features

- **LLM-powered** - Works with any Ollama model (reasoning models like Nanbeige work best)
- **Tool calling** - Can read/write files, search, and execute commands
- **Sandboxed** - Runs in Docker with strict security constraints
- **Workspace isolation** - Only has access to mounted workspace directory
- **Streaming** - Real-time thinking and response streaming to Telegram

## Quick Start

1. **Prerequisites:**
   - Docker & Docker Compose
   - Ollama running (locally or remote)
   - Telegram bot token from [@BotFather](https://t.me/BotFather)

2. **Setup:**
   ```bash
   git clone https://github.com/anvie/clawlite.git
   cd clawlite
   cp .env.example .env
   ```

3. **Configure `.env`:**
   ```env
   TELEGRAM_TOKEN=your_bot_token_here
   OLLAMA_HOST=http://localhost:11434
   OLLAMA_MODEL=llama3.2:3b
   ALLOWED_USERS=your_telegram_user_id
   ```

4. **Run:**
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

## Security

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
+-----------------------------------------------------------+
|                    Docker Host                            |
|  +---------------------------------------------------+    |
|  |          Docker Container (clawlite)              |    |
|  |  +---------------------------------------------+  |    |
|  |  |  - Agent Loop (tool calling)                |  |    |
|  |  |  - Tool Executor (sandboxed)                |  |    |
|  |  |  - Telegram Bot                             |--+----+--> Telegram API
|  |  +---------------------------------------------+  |    |
|  |                    |                              |    |
|  |           /workspace (mounted)                    |    |
|  +--------------------+------------------------------+    |
|                       |                                   |
|        ./workspace/ (host directory)                      |
+-----------------------+-----------------------------------+
                        | HTTP
                        v
              +-------------------+
              |     Ollama        |
              |  (local/remote)   |
              +-------------------+
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_TOKEN` | Bot token from @BotFather | required |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `llama3.2:3b` |
| `ALLOWED_USERS` | Comma-separated user IDs | empty (all allowed) |
| `WORKSPACE_PATH` | Workspace path in container | `/workspace` |

## Remote Ollama

If Ollama runs on a different machine, update `docker-compose.yml`:

```yaml
extra_hosts:
  - "ollama-host:192.168.1.100"
```

And set `OLLAMA_HOST=http://ollama-host:11434` in `.env`.

## Recommended Models

- **Reasoning/thinking models** (best for agentic tasks):
  - `nanbeige4.1:q8` - Chinese reasoning model
  - `deepseek-r1:8b` - Good reasoning capability
  - `qwq:32b` - Excellent for complex tasks

- **General purpose**:
  - `llama3.2:3b` - Fast and lightweight
  - `mistral:7b` - Good balance

## License

MIT
