#!/bin/bash
# ClawLite - Docker Entrypoint
# - Starts cron daemon (as root)
# - Bootstraps workspace on first run
# - Runs main app as clawlite user

set -e

WORKSPACE="/workspace"
TEMPLATES="/app/templates"
RUN_USER="clawlite"

# Start cron daemon (requires root)
if [ "$(id -u)" = "0" ]; then
    echo "🕐 Starting cron daemon..."
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

# Run the main application as non-root user
if [ "$(id -u)" = "0" ]; then
    echo "🚀 Starting ClawLite as $RUN_USER..."
    exec gosu "$RUN_USER" python -m src.main "$@"
else
    # Already running as non-root (e.g., docker run --user)
    exec python -m src.main "$@"
fi
