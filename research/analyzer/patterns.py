"""Issue detection patterns for ClawLite AutoImprove.

Each pattern defines what constitutes a performance issue.
"""

import re
from typing import List, Dict, Any

# Thinking leak patterns - text that indicates reasoning leaked into response
THINKING_PATTERNS: List[re.Pattern] = [
    re.compile(r'<think>', re.IGNORECASE),
    re.compile(r'</think>', re.IGNORECASE),
    re.compile(r'^Actually,', re.MULTILINE),
    re.compile(r'^Let me ', re.MULTILINE),
    re.compile(r"^I'll ", re.MULTILINE),
    re.compile(r'^First,', re.MULTILINE),
    re.compile(r'^Second,', re.MULTILINE),
    re.compile(r'^Third,', re.MULTILINE),
    re.compile(r'^\d+\.\s+(?:First|Next|Then|Finally)', re.MULTILINE),
    re.compile(r'^Hmm,', re.MULTILINE),
    re.compile(r'^Wait,', re.MULTILINE),
    re.compile(r'^So,\s+(?:I|let|we)', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^Okay,\s+(?:I|let|so)', re.MULTILINE | re.IGNORECASE),
    re.compile(r"^I think ", re.MULTILINE),
    re.compile(r"^I need to ", re.MULTILINE),
    re.compile(r"^I should ", re.MULTILINE),
]

# Empty/non-informative response patterns
EMPTY_RESPONSE_PATTERNS: List[re.Pattern] = [
    re.compile(r'^Done!?$', re.IGNORECASE),
    re.compile(r'^Selesai!?$', re.IGNORECASE),
    re.compile(r'^OK!?$', re.IGNORECASE),
    re.compile(r'^Oke!?$', re.IGNORECASE),
    re.compile(r'^✓$'),
    re.compile(r'^✅$'),
]

# User correction patterns - indicates agent made a mistake
USER_CORRECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(no|wrong|salah|bukan|tidak|jangan)\b', re.IGNORECASE),
    re.compile(r'\b(incorrect|error|mistake)\b', re.IGNORECASE),
    re.compile(r'\b(itu bukan|yang benar)\b', re.IGNORECASE),
    re.compile(r'\b(coba lagi|ulangi)\b', re.IGNORECASE),
    re.compile(r'\b(try again|redo)\b', re.IGNORECASE),
]

# Hallucination indicators - claims without evidence
HALLUCINATION_PATTERNS: List[re.Pattern] = [
    re.compile(r'(sudah|already)\s+(di|done|selesai)', re.IGNORECASE),
    re.compile(r'(file|folder)\s+(created|dibuat)', re.IGNORECASE),
    re.compile(r'(sent|terkirim|kirim)', re.IGNORECASE),
]


def get_issue_patterns() -> Dict[str, Any]:
    """Return all issue patterns with their metadata."""
    return {
        'thinking_leak': {
            'description': '<think> tags or prose reasoning patterns',
            'patterns': THINKING_PATTERNS,
            'severity': 'medium',
            'fix_target': 'agent.py',
        },
        'empty_response': {
            'description': "Agent replies 'Done!' without content",
            'patterns': EMPTY_RESPONSE_PATTERNS,
            'severity': 'high',
            'fix_target': 'agent.py',
        },
        'user_correction': {
            'description': 'User corrects the agent',
            'patterns': USER_CORRECTION_PATTERNS,
            'severity': 'high',
            'fix_target': 'prompts/system.md',
        },
        'hallucination': {
            'description': 'Claims action without tool call evidence',
            'patterns': HALLUCINATION_PATTERNS,
            'severity': 'critical',
            'fix_target': 'prompts/system.md',
        },
        'loop_behavior': {
            'description': 'Same tool called 3+ times consecutively',
            'threshold': 3,
            'severity': 'high',
            'fix_target': 'agent.py',
        },
        'context_bloat': {
            'description': 'Re-reading same files unnecessarily',
            'threshold': 2,  # Same file read 2+ times
            'severity': 'low',
            'fix_target': 'agent.py',
        },
        'slow_response': {
            'description': 'Response took >30 seconds',
            'threshold_seconds': 30,
            'severity': 'medium',
            'fix_target': 'agent.py',
        },
    }


ISSUE_PATTERNS = get_issue_patterns()
