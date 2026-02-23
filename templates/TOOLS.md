# TOOLS.md — Tool Notes & Configuration

> **Note:** Available tools are loaded dynamically based on your access level.
> This file is for your personal notes about tools, servers, and configurations.

## Servers & Services

*Document your server details:*

```markdown
### Production Server
- Host: 192.168.1.100
- SSH: ssh user@192.168.1.100
- Services: nginx, postgres
```

## API Endpoints

*APIs you frequently use:*

```markdown
### Weather API
- URL: https://api.weather.example/v1
- Auth: API key in header
- Usage: GET /forecast?city=Jakarta
```

## Cron Job Notes

*Track your scheduled tasks:*

| Schedule | Purpose | Notes |
|----------|---------|-------|
| `0 9 * * *` | Daily reminder | Via clawlite-send |
| `0 18 * * 5` | Weekly report | Friday 6pm |

## Common Commands

*Shortcuts and frequently used commands:*

```bash
# Check disk space
df -h

# Find large files
find . -size +100M

# Tail logs
tail -f /var/log/app.log
```

## Tips

- Use `run_bash` for multi-line scripts
- Grep supports `-i` for case-insensitive search
- `edit_file` with `append: true` to add to existing files

---

*This file is shared across all users. Add notes that apply to everyone.*
