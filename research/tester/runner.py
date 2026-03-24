"""Test runner for ClawLite AutoImprove.

Runs test cases against live vLLM and evaluates results.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

import requests

from .generator import TestCase, load_test_cases

logger = logging.getLogger('autoimprove.tester.runner')


@dataclass
class TestResult:
    """Result of running a single test case."""
    test_id: str
    passed: bool
    response: str = ""
    tool_calls: List[str] = field(default_factory=list)
    duration_ms: int = 0
    failure_reason: str = ""
    violations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'test_id': self.test_id,
            'passed': self.passed,
            'response': self.response[:500] if self.response else "",
            'tool_calls': self.tool_calls,
            'duration_ms': self.duration_ms,
            'failure_reason': self.failure_reason,
            'violations': self.violations,
        }


def load_config() -> Dict[str, Any]:
    """Load AutoImprove configuration."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        import yaml
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


def call_vllm(
    prompt: str,
    config: Dict[str, Any],
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Call vLLM API and return response.
    
    Args:
        prompt: User message
        config: Configuration dict with vllm settings
        system_prompt: Optional system prompt
        
    Returns:
        Dict with response, tool_calls, duration_ms
    """
    vllm_config = config.get('vllm', {})
    url = vllm_config.get('url', 'http://192.168.1.7:8000/v1')
    model = vllm_config.get('model', 'Qwen/Qwen3.5-27B-NVFP4')
    timeout = vllm_config.get('timeout', 120)
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{url}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.7,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        
        duration_ms = int((time.time() - start_time) * 1000)
        content = data['choices'][0]['message']['content']
        
        # Extract tool calls from response
        tool_calls = extract_tool_calls(content)
        
        return {
            'response': content,
            'tool_calls': tool_calls,
            'duration_ms': duration_ms,
        }
    except requests.RequestException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"vLLM API error: {e}")
        return {
            'response': '',
            'tool_calls': [],
            'duration_ms': duration_ms,
            'error': str(e),
        }


def extract_tool_calls(content: str) -> List[str]:
    """Extract tool call names from response content."""
    tool_calls = []
    
    # Pattern for <tool_call> XML format
    tool_pattern = re.compile(r'<tool_call>\s*(\w+)', re.DOTALL)
    for match in tool_pattern.finditer(content):
        tool_calls.append(match.group(1))
    
    # Pattern for JSON format
    json_pattern = re.compile(r'\{"tool":\s*"(\w+)"', re.DOTALL)
    for match in json_pattern.finditer(content):
        tool_calls.append(match.group(1))
    
    return tool_calls


def load_system_prompt(workspace_path: str) -> str:
    """Load ClawLite system prompt."""
    prompt_file = Path(workspace_path).parent / "prompts" / "system.md"
    if prompt_file.exists():
        return prompt_file.read_text()
    
    # Fallback to AGENTS.md
    agents_file = Path(workspace_path) / "AGENTS.md"
    if agents_file.exists():
        return agents_file.read_text()
    
    return ""


def evaluate_response(test_case: TestCase, response: str, tool_calls: List[str], duration_ms: int) -> TestResult:
    """Evaluate a response against test case criteria.
    
    Args:
        test_case: The test case to evaluate against
        response: Agent's response
        tool_calls: List of tool names called
        duration_ms: Response duration in milliseconds
        
    Returns:
        TestResult object
    """
    violations = []
    passed = True
    
    # Check forbidden patterns
    for pattern in test_case.forbidden_patterns:
        try:
            if re.search(pattern, response, re.MULTILINE | re.IGNORECASE):
                violations.append(f"Forbidden pattern found: {pattern}")
                passed = False
        except re.error:
            logger.warning(f"Invalid regex pattern: {pattern}")
    
    # Check required patterns
    for pattern in test_case.required_patterns:
        try:
            if not re.search(pattern, response, re.MULTILINE | re.IGNORECASE):
                violations.append(f"Required pattern missing: {pattern}")
                passed = False
        except re.error:
            logger.warning(f"Invalid regex pattern: {pattern}")
    
    # Check max tool calls
    if test_case.max_tool_calls is not None:
        if len(tool_calls) > test_case.max_tool_calls:
            violations.append(f"Too many tool calls: {len(tool_calls)} > {test_case.max_tool_calls}")
            passed = False
    
    # Check max duration
    if test_case.max_duration_ms is not None:
        if duration_ms > test_case.max_duration_ms:
            violations.append(f"Too slow: {duration_ms}ms > {test_case.max_duration_ms}ms")
            passed = False
    
    failure_reason = "; ".join(violations) if violations else ""
    
    return TestResult(
        test_id=test_case.id,
        passed=passed,
        response=response,
        tool_calls=tool_calls,
        duration_ms=duration_ms,
        failure_reason=failure_reason,
        violations=violations,
    )


def run_test(
    test_case: TestCase,
    config: Dict[str, Any],
    workspace_path: str,
) -> TestResult:
    """Run a single test case.
    
    Args:
        test_case: TestCase to run
        config: Configuration dict
        workspace_path: Path to ClawLite workspace
        
    Returns:
        TestResult object
    """
    logger.info(f"Running test: {test_case.id}")
    
    # Load system prompt
    system_prompt = load_system_prompt(workspace_path)
    
    # Call vLLM
    result = call_vllm(
        prompt=test_case.user_message,
        config=config,
        system_prompt=system_prompt,
    )
    
    if 'error' in result:
        return TestResult(
            test_id=test_case.id,
            passed=False,
            failure_reason=f"API error: {result['error']}",
            duration_ms=result.get('duration_ms', 0),
        )
    
    # Evaluate response
    return evaluate_response(
        test_case=test_case,
        response=result['response'],
        tool_calls=result['tool_calls'],
        duration_ms=result['duration_ms'],
    )


def run_tests(
    test_cases: List[TestCase],
    config: Dict[str, Any],
    workspace_path: str,
    stop_on_failure: bool = False,
) -> Dict[str, Any]:
    """Run multiple test cases.
    
    Args:
        test_cases: List of TestCase objects to run
        config: Configuration dict
        workspace_path: Path to ClawLite workspace
        stop_on_failure: Stop running after first failure
        
    Returns:
        Dict with results summary
    """
    results = []
    passed = 0
    failed = 0
    
    for tc in test_cases:
        result = run_test(tc, config, workspace_path)
        results.append(result)
        
        if result.passed:
            passed += 1
            logger.info(f"✓ {tc.id} passed")
        else:
            failed += 1
            logger.warning(f"✗ {tc.id} failed: {result.failure_reason}")
            
            if stop_on_failure:
                break
    
    return {
        'total': len(results),
        'passed': passed,
        'failed': failed,
        'pass_rate': (passed / len(results) * 100) if results else 0,
        'results': results,
    }


def run_tests_from_dir(
    cases_dir: str,
    config: Dict[str, Any],
    workspace_path: str,
    filter_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Run all test cases from a directory.
    
    Args:
        cases_dir: Directory containing test_cases.json
        config: Configuration dict
        workspace_path: Path to ClawLite workspace
        filter_type: Only run tests of this issue type
        
    Returns:
        Dict with results summary
    """
    test_cases = load_test_cases(cases_dir)
    
    if filter_type:
        test_cases = [tc for tc in test_cases if tc.issue_type == filter_type]
    
    if not test_cases:
        logger.warning("No test cases found")
        return {'total': 0, 'passed': 0, 'failed': 0, 'results': []}
    
    logger.info(f"Running {len(test_cases)} test cases")
    return run_tests(test_cases, config, workspace_path)
