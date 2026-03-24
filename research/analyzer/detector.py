"""Issue detector for ClawLite AutoImprove.

Analyzes conversations to detect performance issues.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from collections import Counter

from .parser import Conversation, Exchange
from .patterns import (
    THINKING_PATTERNS,
    EMPTY_RESPONSE_PATTERNS,
    USER_CORRECTION_PATTERNS,
    HALLUCINATION_PATTERNS,
    SERVER_ERROR_PATTERNS,
    ISSUE_PATTERNS,
)

logger = logging.getLogger('autoimprove.analyzer.detector')


@dataclass
class Issue:
    """Represents a detected performance issue."""
    type: str
    severity: str
    description: str
    exchange: Exchange
    context: Dict[str, Any] = field(default_factory=dict)
    source_file: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type,
            'severity': self.severity,
            'description': self.description,
            'user_message': self.exchange.user_message,
            'assistant_response': self.exchange.assistant_response[:500],
            'tool_calls': self.exchange.get_tool_sequence(),
            'context': self.context,
            'source_file': self.source_file,
        }


def detect_thinking_leak(exchange: Exchange) -> Optional[Issue]:
    """Detect thinking/reasoning text leaked into response."""
    response = exchange.assistant_response
    
    for pattern in THINKING_PATTERNS:
        if pattern.search(response):
            return Issue(
                type='thinking_leak',
                severity='medium',
                description=f'Pattern matched: {pattern.pattern}',
                exchange=exchange,
                context={'pattern': pattern.pattern},
            )
    return None


def detect_empty_response(exchange: Exchange) -> Optional[Issue]:
    """Detect empty or non-informative responses."""
    response = exchange.assistant_response.strip()
    
    # Check if response is very short
    if len(response) < 10:
        for pattern in EMPTY_RESPONSE_PATTERNS:
            if pattern.match(response):
                return Issue(
                    type='empty_response',
                    severity='high',
                    description=f'Empty response: "{response}"',
                    exchange=exchange,
                )
    return None


def detect_user_correction(exchange: Exchange, next_exchange: Optional[Exchange]) -> Optional[Issue]:
    """Detect if user corrects the agent in the next message."""
    if not next_exchange:
        return None
    
    user_msg = next_exchange.user_message.lower()
    
    for pattern in USER_CORRECTION_PATTERNS:
        if pattern.search(user_msg):
            return Issue(
                type='user_correction',
                severity='high',
                description=f'User correction detected: "{next_exchange.user_message[:100]}"',
                exchange=exchange,
                context={
                    'correction_message': next_exchange.user_message,
                    'pattern': pattern.pattern,
                },
            )
    return None


def detect_loop_behavior(exchanges: List[Exchange], index: int) -> Optional[Issue]:
    """Detect if agent gets stuck in a tool call loop."""
    exchange = exchanges[index]
    tool_sequence = exchange.get_tool_sequence()
    
    if len(tool_sequence) < 3:
        return None
    
    # Count consecutive same tool calls
    max_consecutive = 1
    current_consecutive = 1
    current_tool = tool_sequence[0] if tool_sequence else None
    
    for tool in tool_sequence[1:]:
        if tool == current_tool:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_tool = tool
            current_consecutive = 1
    
    threshold = ISSUE_PATTERNS['loop_behavior'].get('threshold', 3)
    if max_consecutive >= threshold:
        return Issue(
            type='loop_behavior',
            severity='high',
            description=f'Tool "{current_tool}" called {max_consecutive} times consecutively',
            exchange=exchange,
            context={
                'tool': current_tool,
                'count': max_consecutive,
                'sequence': tool_sequence,
            },
        )
    return None


def detect_context_bloat(exchange: Exchange) -> Optional[Issue]:
    """Detect if agent re-reads the same files unnecessarily."""
    tool_calls = exchange.tool_calls
    
    # Count file reads
    file_reads: Counter = Counter()
    for tc in tool_calls:
        if tc.name in ('read_file', 'read'):
            filepath = tc.arguments.get('path', tc.arguments.get('file', ''))
            if filepath:
                file_reads[filepath] += 1
    
    # Check for duplicates
    threshold = ISSUE_PATTERNS['context_bloat'].get('threshold', 2)
    for filepath, count in file_reads.items():
        if count >= threshold:
            return Issue(
                type='context_bloat',
                severity='low',
                description=f'File "{filepath}" read {count} times',
                exchange=exchange,
                context={
                    'file': filepath,
                    'count': count,
                },
            )
    return None


def detect_slow_response(exchange: Exchange) -> Optional[Issue]:
    """Detect slow responses."""
    if exchange.duration_ms is None:
        return None
    
    threshold_ms = ISSUE_PATTERNS['slow_response'].get('threshold_seconds', 30) * 1000
    if exchange.duration_ms > threshold_ms:
        return Issue(
            type='slow_response',
            severity='medium',
            description=f'Response took {exchange.duration_ms / 1000:.1f}s',
            exchange=exchange,
            context={
                'duration_ms': exchange.duration_ms,
                'threshold_ms': threshold_ms,
            },
        )
    return None


# Tools that provide evidence for action claims
EVIDENCE_TOOLS = {
    'write_file', 'exec', 'send_message', 'edit_file',
    'send_file',  # ClawLite's file sending tool
    'memory_update', 'user_update', 'memory_log',  # Memory operations
    'add_cron', 'remove_cron',  # Cron operations
    'add_reminder', 'edit_reminder', 'delete_reminder',  # Reminder operations
    'web_search', 'web_fetch',  # Web operations (evidence for "searched" claims)
    'run_bash',  # Shell execution
}


def detect_hallucination(exchange: Exchange) -> Optional[Issue]:
    """Detect potential hallucinations (claims without tool evidence)."""
    response = exchange.assistant_response
    tool_calls = exchange.tool_calls
    
    # Check for action claims without corresponding tool calls
    for pattern in HALLUCINATION_PATTERNS:
        if pattern.search(response):
            # Check if there's a relevant tool call
            has_evidence = False
            for tc in tool_calls:
                # Check against expanded evidence tools list
                if tc.name in EVIDENCE_TOOLS:
                    has_evidence = True
                    break
            
            if not has_evidence and len(tool_calls) == 0:
                return Issue(
                    type='hallucination',
                    severity='critical',
                    description=f'Potential hallucination: claims action without tool call',
                    exchange=exchange,
                    context={
                        'pattern': pattern.pattern,
                        'claim': pattern.search(response).group(0),
                    },
                )
    return None


def detect_server_error(exchange: Exchange) -> Optional[Issue]:
    """Detect server connection or processing errors."""
    response = exchange.assistant_response
    
    for pattern in SERVER_ERROR_PATTERNS:
        if pattern.search(response):
            return Issue(
                type='server_error',
                severity='critical',
                description=f'Server error: "{response[:100]}"',
                exchange=exchange,
                context={
                    'pattern': pattern.pattern,
                    'error_msg': pattern.search(response).group(0),
                },
            )
    return None


def analyze_exchange(
    exchange: Exchange,
    next_exchange: Optional[Exchange] = None,
    all_exchanges: Optional[List[Exchange]] = None,
    index: int = 0,
) -> List[Issue]:
    """Analyze a single exchange for issues."""
    issues = []
    
    # Run all detectors
    detectors = [
        lambda: detect_thinking_leak(exchange),
        lambda: detect_empty_response(exchange),
        lambda: detect_user_correction(exchange, next_exchange),
        lambda: detect_context_bloat(exchange),
        lambda: detect_slow_response(exchange),
        lambda: detect_hallucination(exchange),
        lambda: detect_server_error(exchange),
    ]
    
    # Add loop detection if we have all exchanges
    if all_exchanges:
        detectors.append(lambda: detect_loop_behavior(all_exchanges, index))
    
    for detector in detectors:
        try:
            issue = detector()
            if issue:
                issues.append(issue)
        except Exception as e:
            logger.error(f"Detector error: {e}")
    
    return issues


def analyze_conversation(conversation: Conversation) -> List[Issue]:
    """Analyze a full conversation for issues.
    
    Args:
        conversation: Conversation object to analyze
        
    Returns:
        List of detected Issues
    """
    all_issues = []
    exchanges = conversation.exchanges
    
    for i, exchange in enumerate(exchanges):
        next_exchange = exchanges[i + 1] if i + 1 < len(exchanges) else None
        
        issues = analyze_exchange(
            exchange=exchange,
            next_exchange=next_exchange,
            all_exchanges=exchanges,
            index=i,
        )
        
        # Add source file to each issue
        for issue in issues:
            issue.source_file = conversation.source_file
        
        all_issues.extend(issues)
    
    logger.info(f"Found {len(all_issues)} issues in conversation {conversation.user_id}/{conversation.date}")
    return all_issues


def analyze_conversations(conversations: List[Conversation]) -> Dict[str, Any]:
    """Analyze multiple conversations and return summary.
    
    Args:
        conversations: List of Conversation objects
        
    Returns:
        Dictionary with analysis results and metrics
    """
    all_issues = []
    total_exchanges = 0
    
    for convo in conversations:
        issues = analyze_conversation(convo)
        all_issues.extend(issues)
        total_exchanges += convo.exchange_count
    
    # Aggregate by issue type
    issue_counts: Counter = Counter()
    for issue in all_issues:
        issue_counts[issue.type] += 1
    
    # Calculate metrics
    metrics = calculate_metrics(all_issues, total_exchanges)
    
    return {
        'conversations_analyzed': len(conversations),
        'total_exchanges': total_exchanges,
        'total_issues': len(all_issues),
        'issues_by_type': dict(issue_counts),
        'issues': all_issues,
        'metrics': metrics,
    }


def calculate_metrics(issues: List[Issue], total_exchanges: int) -> Dict[str, float]:
    """Calculate performance metrics from issues."""
    if total_exchanges == 0:
        return {
            'loop_rate': 0.0,
            'thinking_leak_rate': 0.0,
            'error_rate': 0.0,
            'user_correction_rate': 0.0,
        }
    
    # Count issues by type
    counts = Counter(issue.type for issue in issues)
    
    return {
        'loop_rate': (counts['loop_behavior'] / total_exchanges) * 100,
        'thinking_leak_rate': (counts['thinking_leak'] / total_exchanges) * 100,
        'error_rate': ((counts['empty_response'] + counts['hallucination'] + counts['server_error']) / total_exchanges) * 100,
        'user_correction_rate': (counts['user_correction'] / total_exchanges) * 100,
    }
