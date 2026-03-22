"""ClawLite AutoImprove Fixer Module

Proposes and applies fixes based on test failures.
"""

from .proposer import propose_fix, FixProposal
from .applier import apply_fix, apply_fixes
from .clawlite_fixer import (
    apply_to_production,
    apply_to_dev,
    add_section_to_agents_md,
    update_agent_py_constant,
    add_thinking_pattern,
    git_commit_and_push,
    fix_issue,
)

__all__ = [
    'propose_fix',
    'FixProposal',
    'apply_fix',
    'apply_fixes',
    'apply_to_production',
    'apply_to_dev',
    'add_section_to_agents_md',
    'update_agent_py_constant',
    'add_thinking_pattern',
    'git_commit_and_push',
    'fix_issue',
]
