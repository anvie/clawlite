"""ClawLite AutoImprove Analyzer Module

Parses conversations and detects performance issues.
"""

from .parser import load_conversations, Conversation, Exchange
from .detector import analyze_conversation, analyze_conversations, Issue
from .patterns import ISSUE_PATTERNS

__all__ = [
    'load_conversations',
    'Conversation',
    'Exchange',
    'analyze_conversation',
    'analyze_conversations',
    'Issue',
    'ISSUE_PATTERNS',
]
