"""Fix applier for ClawLite AutoImprove.

Applies proposed fixes and commits changes.
"""

import logging
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .proposer import FixProposal

logger = logging.getLogger('autoimprove.fixer.applier')


def backup_file(file_path: str) -> str:
    """Create a backup of a file before modification.
    
    Args:
        file_path: Path to file to backup
        
    Returns:
        Path to backup file
    """
    src = Path(file_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Create backup with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = src.parent / f"{src.stem}.backup_{timestamp}{src.suffix}"
    shutil.copy2(src, backup_path)
    
    logger.info(f"Created backup: {backup_path}")
    return str(backup_path)


def restore_from_backup(backup_path: str, original_path: str) -> bool:
    """Restore a file from backup.
    
    Args:
        backup_path: Path to backup file
        original_path: Path to restore to
        
    Returns:
        True if successful
    """
    try:
        shutil.copy2(backup_path, original_path)
        logger.info(f"Restored {original_path} from backup")
        return True
    except Exception as e:
        logger.error(f"Failed to restore from backup: {e}")
        return False


def apply_text_replacement(file_path: str, old_content: str, new_content: str) -> bool:
    """Apply a text replacement to a file.
    
    Args:
        file_path: Path to file
        old_content: Text to find
        new_content: Text to replace with
        
    Returns:
        True if successful
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return False
    
    content = path.read_text()
    
    if old_content not in content:
        logger.warning(f"Old content not found in {file_path}")
        return False
    
    new_file_content = content.replace(old_content, new_content, 1)
    path.write_text(new_file_content)
    
    logger.info(f"Applied replacement to {file_path}")
    return True


def git_commit(project_root: str, message: str, files: List[str]) -> bool:
    """Commit changes to git.
    
    Args:
        project_root: Path to git repo root
        message: Commit message
        files: List of files to commit
        
    Returns:
        True if successful
    """
    try:
        # Stage files
        for f in files:
            subprocess.run(
                ['git', 'add', f],
                cwd=project_root,
                check=True,
                capture_output=True,
            )
        
        # Commit
        result = subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            # Get commit hash
            hash_result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
            commit_hash = hash_result.stdout.strip()
            logger.info(f"Committed: {commit_hash} - {message}")
            return True
        else:
            logger.warning(f"Git commit failed: {result.stderr}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Git error: {e}")
        return False


def apply_fix(
    proposal: FixProposal,
    project_root: str,
    auto_commit: bool = True,
    commit_prefix: str = "autoimprove:",
) -> Dict[str, Any]:
    """Apply a single fix proposal.
    
    Args:
        proposal: FixProposal to apply
        project_root: Path to project root
        auto_commit: Whether to auto-commit changes
        commit_prefix: Prefix for commit messages
        
    Returns:
        Dict with status and details
    """
    result = {
        'proposal_id': proposal.id,
        'applied': False,
        'committed': False,
        'backup_path': None,
        'error': None,
    }
    
    # Check if requires review
    if proposal.requires_review:
        result['error'] = "Fix requires human review"
        logger.info(f"Skipping {proposal.id}: requires review")
        return result
    
    # Validate we have content to replace
    if not proposal.old_content or not proposal.new_content:
        result['error'] = "Missing old_content or new_content"
        return result
    
    file_path = proposal.file_path
    
    try:
        # Create backup
        backup_path = backup_file(file_path)
        result['backup_path'] = backup_path
        
        # Apply the fix
        if apply_text_replacement(file_path, proposal.old_content, proposal.new_content):
            result['applied'] = True
            
            # Commit if enabled
            if auto_commit:
                commit_msg = f"{commit_prefix} {proposal.description}"
                if git_commit(project_root, commit_msg, [file_path]):
                    result['committed'] = True
        else:
            result['error'] = "Text replacement failed"
            # Restore from backup
            restore_from_backup(backup_path, file_path)
            
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"Error applying fix: {e}")
        
        # Try to restore from backup
        if result.get('backup_path'):
            restore_from_backup(result['backup_path'], file_path)
    
    return result


def apply_fixes(
    proposals: List[FixProposal],
    project_root: str,
    auto_commit: bool = True,
    commit_prefix: str = "autoimprove:",
    stop_on_failure: bool = True,
) -> Dict[str, Any]:
    """Apply multiple fix proposals.
    
    Args:
        proposals: List of FixProposal objects
        project_root: Path to project root
        auto_commit: Whether to auto-commit changes
        commit_prefix: Prefix for commit messages
        stop_on_failure: Stop after first failure
        
    Returns:
        Dict with summary of results
    """
    results = []
    applied = 0
    committed = 0
    failed = 0
    skipped = 0
    
    for proposal in proposals:
        if proposal.requires_review:
            skipped += 1
            results.append({
                'proposal_id': proposal.id,
                'skipped': True,
                'reason': 'requires_review',
            })
            continue
        
        result = apply_fix(proposal, project_root, auto_commit, commit_prefix)
        results.append(result)
        
        if result['applied']:
            applied += 1
            if result.get('committed'):
                committed += 1
        else:
            failed += 1
            if stop_on_failure:
                break
    
    return {
        'total': len(proposals),
        'applied': applied,
        'committed': committed,
        'failed': failed,
        'skipped': skipped,
        'results': results,
    }


def rollback_fix(backup_path: str, original_path: str, project_root: str) -> bool:
    """Rollback a fix by restoring from backup and reverting commit.
    
    Args:
        backup_path: Path to backup file
        original_path: Path to restore to
        project_root: Path to git repo
        
    Returns:
        True if successful
    """
    # Restore file
    if not restore_from_backup(backup_path, original_path):
        return False
    
    # Stage the restored file
    try:
        subprocess.run(
            ['git', 'add', original_path],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        
        # Commit the rollback
        subprocess.run(
            ['git', 'commit', '-m', f'autoimprove: rollback {original_path}'],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        
        logger.info(f"Rolled back changes to {original_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Rollback commit failed: {e}")
        return False
