#!/bin/bash
# ClawLite - Docker Entrypoint
# - Starts cron daemon (as root)
# - Bootstraps workspace on first run
# - Runs main app as clawlite user

set -e

WORKSPACE="/workspace"
TEMPLATES="/app/templates"
TEMPLATE_BIN="/app/template-bin"
RUN_USER="clawlite"

# Start cron daemon (requires root)
if [ "$(id -u)" = "0" ]; then
    echo "🕐 Starting cron daemon..."
    
    # Ensure crontab directories exist with correct permissions
    mkdir -p /var/spool/cron/crontabs
    chown root:crontab /var/spool/cron/crontabs
    chmod 1730 /var/spool/cron/crontabs
    
    # Allow clawlite user to use crontab
    touch /var/spool/cron/crontabs/clawlite
    chown clawlite:crontab /var/spool/cron/crontabs/clawlite
    chmod 600 /var/spool/cron/crontabs/clawlite
    
    # Setup reminder daemon cron job (runs every minute)
    # Export required env vars to cron (cron doesn't inherit container env)
    ENV_VARS=""
    [ -n "$TELEGRAM_TOKEN" ] && ENV_VARS="${ENV_VARS}TELEGRAM_TOKEN=$TELEGRAM_TOKEN "
    [ -n "$WHATSAPP_PHONE" ] && ENV_VARS="${ENV_VARS}WHATSAPP_PHONE=$WHATSAPP_PHONE "
    ENV_VARS="${ENV_VARS}WORKSPACE_DIR=/workspace"
    
    # Build cron entry
    REMINDER_CRON="* * * * * cd /app && $ENV_VARS /usr/local/bin/python /app/scripts/reminder-daemon.py >> /tmp/reminder-daemon.log 2>&1"
    
    # Install cron (remove old entry first if exists, then add new)
    EXISTING=$(crontab -u clawlite -l 2>/dev/null | grep -v "reminder-daemon" || true)
    echo "${EXISTING}
${REMINDER_CRON}" | crontab -u clawlite -
    echo "✓ Reminder daemon cron installed"
    
    service cron start || cron
    echo "✓ Cron daemon started"
fi

# Bootstrap workspace if empty
if [ ! -f "$WORKSPACE/SOUL.md" ]; then
    echo "🦎 First run detected - bootstrapping workspace..."
    
    # Copy templates
    if [ -d "$TEMPLATES" ]; then
        cp -n "$TEMPLATES/SOUL.md" "$WORKSPACE/" 2>/dev/null || true
        cp -n "$TEMPLATES/AGENTS.md" "$WORKSPACE/" 2>/dev/null || true
        cp -n "$TEMPLATES/TOOLS.md" "$WORKSPACE/" 2>/dev/null || true
        echo "✓ Copied templates to workspace"
    fi
    
    # Create directories
    mkdir -p "$WORKSPACE/users"
    mkdir -p "$WORKSPACE/uploads"
    
    # Set ownership
    chown -R "$RUN_USER:$RUN_USER" "$WORKSPACE"
    
    echo "✓ Bootstrap complete!"
    echo ""
fi

# Ensure workspace ownership
chown -R "$RUN_USER:$RUN_USER" "$WORKSPACE" 2>/dev/null || true

# Copy template binaries if present (e.g., krasan, krasan-admin)
if [ -d "$TEMPLATE_BIN" ] && [ "$(ls -A $TEMPLATE_BIN 2>/dev/null)" ]; then
    echo "📦 Installing template binaries..."
    cp -f "$TEMPLATE_BIN"/* /usr/local/bin/ 2>/dev/null || true
    chmod +x /usr/local/bin/* 2>/dev/null || true
    echo "✓ Template binaries installed"
fi

# Ensure owner file is writable by app (for first-user-as-admin)
if [ -f "/app/.owner" ]; then
    chown "$RUN_USER:$RUN_USER" /app/.owner 2>/dev/null || true
fi

# Run the main application as non-root user
# Note: cd /app is required for Python module loading (src.main)
# Container working_dir can be /workspace for shell commands
if [ "$(id -u)" = "0" ]; then
    echo "🚀 Starting ClawLite as $RUN_USER..."
    exec gosu "$RUN_USER" bash -c "cd /app && python -m src.main $*"
else
    # Already running as non-root (e.g., docker run --user)
    cd /app && exec python -m src.main "$@"
fi
