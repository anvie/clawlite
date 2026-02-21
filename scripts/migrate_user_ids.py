#!/usr/bin/env python3
"""
Migrate existing user folders to prefixed format.

Before: workspace/users/123456/
After:  workspace/users/tg_123456/

Usage:
    python scripts/migrate_user_ids.py [--dry-run] [--prefix tg]
"""

import os
import sys
import shutil
import argparse
from pathlib import Path


def get_workspace_path() -> Path:
    """Get workspace path from env or default."""
    return Path(os.getenv("WORKSPACE_PATH", "/workspace"))


def migrate_users(prefix: str, dry_run: bool = False) -> None:
    """Migrate user folders to prefixed format."""
    workspace = get_workspace_path()
    users_dir = workspace / "users"
    
    if not users_dir.exists():
        print(f"Users directory not found: {users_dir}")
        return
    
    # Find folders that need migration (not already prefixed)
    to_migrate = []
    for folder in users_dir.iterdir():
        if not folder.is_dir():
            continue
        
        name = folder.name
        # Skip if already prefixed
        if name.startswith(f"{prefix}_") or name.startswith("tg_") or name.startswith("wa_"):
            print(f"  ✓ {name} (already prefixed)")
            continue
        
        to_migrate.append(folder)
    
    if not to_migrate:
        print("No folders need migration.")
        return
    
    print(f"\nFolders to migrate ({len(to_migrate)}):")
    for folder in to_migrate:
        new_name = f"{prefix}_{folder.name}"
        new_path = users_dir / new_name
        print(f"  {folder.name} → {new_name}")
        
        if not dry_run:
            if new_path.exists():
                print(f"    ⚠️  Target already exists, skipping")
                continue
            
            shutil.move(str(folder), str(new_path))
            print(f"    ✓ Migrated")
    
    if dry_run:
        print("\n[DRY RUN] No changes made. Remove --dry-run to apply.")


def main():
    parser = argparse.ArgumentParser(description="Migrate user folders to prefixed format")
    parser.add_argument(
        "--prefix",
        default="tg",
        help="Prefix to add (default: tg for Telegram)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    print(f"ClawLite User ID Migration")
    print(f"Workspace: {get_workspace_path()}")
    print(f"Prefix: {args.prefix}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    migrate_users(args.prefix, args.dry_run)


if __name__ == "__main__":
    main()
