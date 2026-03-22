"""ClawLite AutoImprove Fixer Module

Proposes and applies fixes based on test failures.
"""

from .proposer import propose_fix, FixProposal
from .applier import apply_fix, apply_fixes

__all__ = [
    'propose_fix',
    'FixProposal',
    'apply_fix',
    'apply_fixes',
]
