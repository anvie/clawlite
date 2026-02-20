#!/bin/bash
# ClawLite - First-time Setup Script

set -e

echo "🦎 ClawLite Setup"
echo "================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env from .env.example...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env${NC}"
    echo ""
    echo "⚠️  Please edit .env and set your configuration:"
    echo "   - TELEGRAM_TOKEN (required for Telegram)"
    echo "   - LLM_PROVIDER and related settings"
    echo ""
else
    echo -e "${GREEN}✓ .env already exists${NC}"
fi

# Create workspace directories
echo "Creating workspace directories..."
mkdir -p workspace/users
mkdir -p workspace/uploads
echo -e "${GREEN}✓ Created workspace/users and workspace/uploads${NC}"

# Copy templates if workspace is empty
if [ ! -f workspace/SOUL.md ]; then
    echo "Copying templates to workspace..."
    cp templates/SOUL.md workspace/
    cp templates/AGENTS.md workspace/
    cp templates/TOOLS.md workspace/
    echo -e "${GREEN}✓ Copied templates to workspace${NC}"
else
    echo -e "${GREEN}✓ Workspace already configured${NC}"
fi

# Create data directories for WhatsApp
mkdir -p data/whatsapp
echo -e "${GREEN}✓ Created data/whatsapp${NC}"

echo ""
echo "================="
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your configuration"
echo "  2. Customize workspace/SOUL.md for bot personality"
echo "  3. Run with Docker:"
echo "       docker compose up -d"
echo "  4. Or run with Python:"
echo "       pip install -r requirements.txt"
echo "       python -m src.main"
echo ""
