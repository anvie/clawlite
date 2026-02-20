# TOOLS.md — Local Tool Notes

Document tool-specific configuration and notes here.

## Servers & Services

*Add your server details:*

```
### Example Server
- Host: 192.168.1.100
- SSH: ssh user@192.168.1.100
- Services: nginx, postgres
```

## API Endpoints

*Document APIs you frequently use:*

```
### Weather API
- URL: https://api.weather.example/v1
- Auth: API key in header
- Usage: GET /forecast?city=Jakarta
```

## Cron Jobs

*Track scheduled tasks:*

| Schedule | Command | Purpose |
|----------|---------|---------|
| `0 9 * * *` | `python report.py` | Daily report |
| `*/5 * * * *` | `curl health.check` | Health ping |

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

## Notes

*General notes and reminders:*

- Remember to backup before major changes
- Use `run_bash` for multi-line scripts
- Grep supports `-i` for case-insensitive search

---

*This file is shared across all users. Add tool notes that apply to everyone.*
