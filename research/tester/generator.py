"""Test case generator for ClawLite AutoImprove.

Creates test cases from detected issues.
"""

import json
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer.detector import Issue

logger = logging.getLogger('autoimprove.tester.generator')


@dataclass
class TestCase:
    """Represents a test case for ClawLite agent."""
    id: str
    issue_type: str
    user_message: str
    expected_behavior: str
    forbidden_patterns: List[str] = field(default_factory=list)
    required_patterns: List[str] = field(default_factory=list)
    max_tool_calls: Optional[int] = None
    max_duration_ms: Optional[int] = None
    context_files: Dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    created_from: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestCase':
        return cls(**data)


def generate_test_id(issue: Issue) -> str:
    """Generate unique test ID from issue."""
    content = f"{issue.type}:{issue.exchange.user_message}:{issue.exchange.assistant_response[:100]}"
    hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"test_{issue.type}_{hash_val}"


def infer_expected_behavior(issue: Issue) -> str:
    """Infer what the correct behavior should be based on issue type."""
    behaviors = {
        'thinking_leak': 'Response should not contain thinking/reasoning text like <think>, "Actually,", "Let me", numbered steps, etc.',
        'empty_response': 'Response should provide meaningful content, not just "Done!" or acknowledgments.',
        'user_correction': 'Agent should correctly understand and respond to the user request without needing correction.',
        'loop_behavior': 'Agent should not call the same tool more than 2 times consecutively.',
        'context_bloat': 'Agent should not re-read the same file multiple times in one exchange.',
        'slow_response': 'Response should complete within 30 seconds.',
        'hallucination': 'Agent should only claim actions that are backed by actual tool calls.',
    }
    return behaviors.get(issue.type, 'Agent should respond correctly.')


def get_forbidden_patterns(issue: Issue) -> List[str]:
    """Get patterns that should NOT appear in response."""
    patterns = {
        'thinking_leak': [
            '<think>',
            '</think>',
            '^Actually,',
            '^Let me ',
            "^I'll ",
            '^First,',
            '^\\d+\\.',
            '^Hmm,',
            '^Wait,',
        ],
        'empty_response': [
            '^Done!?$',
            '^Selesai!?$',
            '^OK!?$',
        ],
    }
    return patterns.get(issue.type, [])


def get_required_patterns(issue: Issue) -> List[str]:
    """Get patterns that MUST appear in response."""
    # For empty_response issues, require some substantive content
    if issue.type == 'empty_response':
        return ['.{20,}']  # At least 20 chars
    return []


def get_max_tool_calls(issue: Issue) -> Optional[int]:
    """Get maximum allowed tool calls based on issue type."""
    if issue.type == 'loop_behavior':
        return 5  # Reasonable limit
    return None


def generate_test_case(issue: Issue) -> TestCase:
    """Generate a test case from a detected issue.
    
    Args:
        issue: The Issue object to create a test from
        
    Returns:
        TestCase object
    """
    test_id = generate_test_id(issue)
    
    test_case = TestCase(
        id=test_id,
        issue_type=issue.type,
        user_message=issue.exchange.user_message,
        expected_behavior=infer_expected_behavior(issue),
        forbidden_patterns=get_forbidden_patterns(issue),
        required_patterns=get_required_patterns(issue),
        max_tool_calls=get_max_tool_calls(issue),
        max_duration_ms=30000 if issue.type == 'slow_response' else None,
        created_at=datetime.now().isoformat(),
        created_from=issue.source_file,
    )
    
    logger.info(f"Generated test case: {test_id}")
    return test_case


def save_test_cases(test_cases: List[TestCase], output_dir: str) -> str:
    """Save test cases to JSON file.
    
    Args:
        test_cases: List of TestCase objects
        output_dir: Directory to save test cases
        
    Returns:
        Path to saved file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load existing test cases
    cases_file = output_path / "test_cases.json"
    existing_cases = {}
    if cases_file.exists():
        with open(cases_file, 'r') as f:
            data = json.load(f)
            existing_cases = {tc['id']: tc for tc in data.get('test_cases', [])}
    
    # Merge with new test cases (new ones override existing)
    for tc in test_cases:
        existing_cases[tc.id] = tc.to_dict()
    
    # Save merged cases
    output_data = {
        'version': 1,
        'updated_at': datetime.now().isoformat(),
        'test_cases': list(existing_cases.values()),
    }
    
    with open(cases_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    logger.info(f"Saved {len(existing_cases)} test cases to {cases_file}")
    return str(cases_file)


def load_test_cases(cases_dir: str) -> List[TestCase]:
    """Load test cases from directory.
    
    Args:
        cases_dir: Directory containing test_cases.json
        
    Returns:
        List of TestCase objects
    """
    cases_file = Path(cases_dir) / "test_cases.json"
    if not cases_file.exists():
        return []
    
    with open(cases_file, 'r') as f:
        data = json.load(f)
    
    test_cases = []
    for tc_data in data.get('test_cases', []):
        try:
            tc = TestCase.from_dict(tc_data)
            test_cases.append(tc)
        except Exception as e:
            logger.error(f"Error loading test case: {e}")
    
    return test_cases
