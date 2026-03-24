"""Fix proposer for ClawLite AutoImprove.

Analyzes test failures and proposes code/prompt fixes.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tester.runner import TestResult
from tester.generator import TestCase

logger = logging.getLogger('autoimprove.fixer.proposer')


@dataclass
class FixProposal:
    """Represents a proposed fix for a test failure."""
    id: str
    test_id: str
    issue_type: str
    file_path: str
    fix_type: str  # 'pattern_add', 'config_change', 'prompt_update'
    description: str
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    line_number: Optional[int] = None
    confidence: float = 0.8  # 0-1 confidence score
    requires_review: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'test_id': self.test_id,
            'issue_type': self.issue_type,
            'file_path': self.file_path,
            'fix_type': self.fix_type,
            'description': self.description,
            'old_content': self.old_content,
            'new_content': self.new_content,
            'confidence': self.confidence,
            'requires_review': self.requires_review,
        }


def get_fix_targets(issue_type: str) -> Dict[str, str]:
    """Get file paths to modify based on issue type."""
    return {
        'thinking_leak': 'src/agent.py',
        'empty_response': 'src/agent.py',
        'loop_behavior': 'src/agent.py',
        'context_bloat': 'src/agent.py',
        'slow_response': 'src/agent.py',
        'user_correction': 'prompts/system.md',
        'hallucination': 'prompts/system.md',
    }


def propose_thinking_leak_fix(result: TestResult, test_case: TestCase, project_root: str) -> Optional[FixProposal]:
    """Propose fix for thinking leak issues."""
    # Find the pattern that was detected
    response = result.response
    
    # Try to identify the specific pattern
    patterns_to_add = []
    
    # Check for common patterns not yet handled
    new_patterns = [
        (r'^Actually,', "^Actually,"),
        (r'^Let me ', "^Let me "),
        (r'^Hmm,', "^Hmm,"),
        (r'^\d+\.', r"^\\d+\\."),
    ]
    
    for regex, pattern_str in new_patterns:
        if re.search(regex, response, re.MULTILINE):
            patterns_to_add.append(pattern_str)
    
    if not patterns_to_add:
        return None
    
    agent_path = Path(project_root) / "src" / "agent.py"
    if not agent_path.exists():
        logger.warning(f"Agent file not found: {agent_path}")
        return None
    
    agent_content = agent_path.read_text()
    
    # Find THINKING_PATTERNS in agent.py
    pattern_match = re.search(
        r'(THINKING_PATTERNS\s*=\s*\[[\s\S]*?\])',
        agent_content,
    )
    
    if not pattern_match:
        # Try to find PROSE_PATTERNS
        pattern_match = re.search(
            r'(PROSE_PATTERNS\s*=\s*\[[\s\S]*?\])',
            agent_content,
        )
    
    if not pattern_match:
        return FixProposal(
            id=f"fix_thinking_{result.test_id}",
            test_id=result.test_id,
            issue_type='thinking_leak',
            file_path=str(agent_path),
            fix_type='pattern_add',
            description=f"Add thinking patterns: {patterns_to_add}",
            confidence=0.5,
            requires_review=True,  # Can't auto-apply without finding pattern list
        )
    
    old_content = pattern_match.group(1)
    
    # Add new patterns to the list
    # Find the closing bracket and insert before it
    insert_point = old_content.rfind(']')
    new_patterns_str = ',\n    '.join([f'r"{p}"' for p in patterns_to_add])
    new_content = old_content[:insert_point] + f',\n    {new_patterns_str}\n' + old_content[insert_point:]
    
    return FixProposal(
        id=f"fix_thinking_{result.test_id}",
        test_id=result.test_id,
        issue_type='thinking_leak',
        file_path=str(agent_path),
        fix_type='pattern_add',
        description=f"Add thinking patterns to strip: {patterns_to_add}",
        old_content=old_content,
        new_content=new_content,
        confidence=0.8,
    )


def propose_loop_behavior_fix(result: TestResult, test_case: TestCase, project_root: str) -> Optional[FixProposal]:
    """Propose fix for loop behavior issues."""
    agent_path = Path(project_root) / "src" / "agent.py"
    if not agent_path.exists():
        return None
    
    agent_content = agent_path.read_text()
    
    # Find MAX_CONSECUTIVE_SAME_TOOL setting
    match = re.search(
        r'(MAX_CONSECUTIVE_SAME_TOOL\s*=\s*)(\d+)',
        agent_content,
    )
    
    if match:
        current_value = int(match.group(2))
        new_value = max(2, current_value - 1)  # Reduce by 1, minimum 2
        
        old_content = match.group(0)
        new_content = f"{match.group(1)}{new_value}"
        
        return FixProposal(
            id=f"fix_loop_{result.test_id}",
            test_id=result.test_id,
            issue_type='loop_behavior',
            file_path=str(agent_path),
            fix_type='config_change',
            description=f"Reduce MAX_CONSECUTIVE_SAME_TOOL from {current_value} to {new_value}",
            old_content=old_content,
            new_content=new_content,
            confidence=0.7,
        )
    
    return FixProposal(
        id=f"fix_loop_{result.test_id}",
        test_id=result.test_id,
        issue_type='loop_behavior',
        file_path=str(agent_path),
        fix_type='config_change',
        description="Add MAX_CONSECUTIVE_SAME_TOOL limit",
        confidence=0.5,
        requires_review=True,
    )


def propose_empty_response_fix(result: TestResult, test_case: TestCase, project_root: str) -> Optional[FixProposal]:
    """Propose fix for empty response issues."""
    agent_path = Path(project_root) / "src" / "agent.py"
    
    return FixProposal(
        id=f"fix_empty_{result.test_id}",
        test_id=result.test_id,
        issue_type='empty_response',
        file_path=str(agent_path),
        fix_type='prompt_update',
        description="Improve tool result handling to show actual results",
        confidence=0.6,
        requires_review=True,  # Complex fix, needs human review
    )


def propose_prompt_fix(result: TestResult, test_case: TestCase, project_root: str) -> Optional[FixProposal]:
    """Propose fix for prompt-related issues (user_correction, hallucination)."""
    prompt_path = Path(project_root) / "prompts" / "system.md"
    
    if not prompt_path.exists():
        prompt_path = Path(project_root) / "workspace" / "AGENTS.md"
    
    if not prompt_path.exists():
        return None
    
    return FixProposal(
        id=f"fix_prompt_{result.test_id}",
        test_id=result.test_id,
        issue_type=test_case.issue_type,
        file_path=str(prompt_path),
        fix_type='prompt_update',
        description=f"Update system prompt to address {test_case.issue_type}",
        confidence=0.5,
        requires_review=True,  # Prompt changes always need review
    )


def propose_fix(result: TestResult, test_case: TestCase, project_root: str) -> Optional[FixProposal]:
    """Propose a fix for a failing test.
    
    Args:
        result: The failing test result
        test_case: The test case that failed
        project_root: Path to ClawLite project root
        
    Returns:
        FixProposal or None if no fix can be proposed
    """
    if result.passed:
        return None
    
    proposers = {
        'thinking_leak': propose_thinking_leak_fix,
        'loop_behavior': propose_loop_behavior_fix,
        'empty_response': propose_empty_response_fix,
        'user_correction': propose_prompt_fix,
        'hallucination': propose_prompt_fix,
    }
    
    proposer = proposers.get(test_case.issue_type)
    if proposer:
        return proposer(result, test_case, project_root)
    
    logger.warning(f"No proposer for issue type: {test_case.issue_type}")
    return None


def propose_fixes(
    results: List[TestResult],
    test_cases: Dict[str, TestCase],
    project_root: str,
) -> List[FixProposal]:
    """Propose fixes for all failing tests.
    
    Args:
        results: List of test results
        test_cases: Dict mapping test_id to TestCase
        project_root: Path to ClawLite project root
        
    Returns:
        List of FixProposal objects
    """
    proposals = []
    
    for result in results:
        if result.passed:
            continue
        
        test_case = test_cases.get(result.test_id)
        if not test_case:
            logger.warning(f"Test case not found: {result.test_id}")
            continue
        
        proposal = propose_fix(result, test_case, project_root)
        if proposal:
            proposals.append(proposal)
    
    return proposals
