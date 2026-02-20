#!/bin/bash
# ClawLite - Docker Entrypoint
# Auto-bootstraps workspace on first run

set -e

WORKSPACE="/workspace"
TEMPLATES="/app/templates"

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
    echo "✓ Created workspace directories"
    
    echo "✓ Bootstrap complete!"
    echo ""
fi

# Run the main application
exec python -m src.main "$@"
