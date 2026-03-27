"""LLM-powered conversation analyzer for ClawLite AutoImprove.

Uses LLM to analyze conversations and discover issues dynamically,
not limited to predefined patterns.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import requests

from .parser import Conversation, Exchange
from .detector import Issue

logger = logging.getLogger('autoimprove.analyzer.llm_analyzer')

# Analysis prompt template
ANALYSIS_PROMPT = """You are analyzing a conversation between a user and an AI assistant (ClawLite).
Your job is to identify ANY issues, mistakes, or areas for improvement.

## Conversation:
{conversation}

## Your Task:
Analyze this conversation and identify ALL issues. Don't limit yourself to known patterns.
Look for:
1. Factual errors or hallucinations
2. Misunderstanding user intent
3. Poor response quality (too verbose, too brief, off-topic)
4. Tool usage problems (unnecessary calls, missing calls, wrong tools)
5. User frustration indicators (corrections, repeated requests)
6. Any other problems you notice

## Output Format (JSON):
{{
  "issues": [
    {{
      "type": "issue_type_name",  // snake_case, be specific
      "severity": "low|medium|high|critical",
      "description": "What went wrong",
      "evidence": "Quote from conversation showing the issue",
      "suggestion": "How to fix this",
      "is_new_type": true/false  // Is this a new issue type not seen before?
    }}
  ],
  "overall_quality": 1-10,
  "summary": "Brief summary of main problems"
}}

Be thorough but precise. Only report real issues, not minor style preferences.

CRITICAL: Output ONLY the JSON object. No explanation, no thinking, no markdown - just raw JSON starting with {{ and ending with }}"""

PATTERN_GENERATION_PROMPT = """Based on this issue type, generate regex patterns to detect similar issues automatically.

Issue Type: {issue_type}
Description: {description}
Examples from conversations:
{examples}

Generate 2-5 regex patterns that would catch this type of issue.
Output as JSON array of pattern strings:
["pattern1", "pattern2", ...]

Output valid JSON only."""


@dataclass
class LLMIssue:
    """Issue discovered by LLM analysis."""
    type: str
    severity: str
    description: str
    evidence: str
    suggestion: str
    is_new_type: bool
    exchange: Optional[Exchange] = None
    source_file: str = ""
    
    def to_detector_issue(self) -> Issue:
        """Convert to standard Issue format."""
        return Issue(
            type=self.type,
            severity=self.severity,
            description=self.description,
            exchange=self.exchange,
            context={
                'evidence': self.evidence,
                'suggestion': self.suggestion,
                'llm_discovered': True,
                'is_new_type': self.is_new_type,
            },
            source_file=self.source_file,
        )


class LLMAnalyzer:
    """Analyzes conversations using LLM to discover issues dynamically."""
    
    def __init__(self, base_url: str, model: str, timeout: int = 120):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.known_issue_types = self._load_known_types()
    
    def _load_known_types(self) -> set:
        """Load known issue types from patterns."""
        # Start with built-in types
        known = {
            'loop_behavior', 'thinking_leak', 'empty_response',
            'user_correction', 'hallucination', 'server_error',
            'context_bloat', 'slow_response',
        }
        # TODO: Load dynamically discovered types from storage
        return known
    
    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM API and return response."""
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            
            msg = data['choices'][0]['message']
            content = msg.get('content', '')
            reasoning = msg.get('reasoning_content', '')
            
            # For reasoning models: content has the final answer, reasoning has thinking
            # We want content (the JSON), but if empty, try to extract from reasoning
            if content:
                return content
            elif reasoning:
                # Try to find JSON in reasoning content
                logger.debug("Using reasoning_content as fallback")
                return reasoning
            
            return None
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None
    
    def _format_conversation(self, exchanges: List[Exchange], limit: int = 10) -> str:
        """Format exchanges for LLM analysis."""
        lines = []
        for ex in exchanges[-limit:]:  # Last N exchanges
            lines.append(f"USER: {ex.user_message}")
            
            # Include tool calls if any
            if ex.tool_calls:
                tool_summary = ", ".join([f"{tc.name}()" for tc in ex.tool_calls])
                lines.append(f"[Tools used: {tool_summary}]")
            
            lines.append(f"ASSISTANT: {ex.assistant_response[:500]}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _parse_llm_response(self, response: str) -> Optional[Dict]:
        """Parse JSON from LLM response."""
        if not response:
            return None
        
        def extract_balanced_json(text: str) -> Optional[str]:
            """Extract balanced JSON object from text by matching braces."""
            start = text.find('{')
            if start == -1:
                return None
            
            depth = 0
            in_string = False
            escape_next = False
            
            for i, c in enumerate(text[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                if c == '\\' and in_string:
                    escape_next = True
                    continue
                if c == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                    
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        return text[start:i+1]
            return None
            
        # Try multiple extraction strategies
        strategies = [
            # 1. Try direct parse
            lambda r: json.loads(r.strip()),
            # 2. Extract from ```json block
            lambda r: json.loads(re.search(r'```json\s*(.*?)\s*```', r, re.DOTALL).group(1)) if "```json" in r else None,
            # 3. Extract from ``` block
            lambda r: json.loads(re.search(r'```\s*(.*?)\s*```', r, re.DOTALL).group(1)) if "```" in r else None,
            # 4. Find balanced JSON object containing "issues"
            lambda r: json.loads(extract_balanced_json(r)) if '"issues"' in r and extract_balanced_json(r) else None,
            # 5. Find any balanced JSON object
            lambda r: json.loads(extract_balanced_json(r)) if extract_balanced_json(r) else None,
        ]
        
        for i, strategy in enumerate(strategies):
            try:
                result = strategy(response)
                if result and isinstance(result, dict):
                    logger.debug(f"JSON parsed with strategy {i+1}")
                    return result
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue
        
        logger.warning(f"Failed to parse LLM response as JSON")
        logger.debug(f"Response was: {response[:500]}")
        return None
    
    def analyze_conversation(self, conversation: Conversation) -> List[LLMIssue]:
        """Analyze a conversation using LLM and return discovered issues."""
        if not conversation.exchanges:
            return []
        
        # Format conversation for analysis
        conv_text = self._format_conversation(conversation.exchanges)
        prompt = ANALYSIS_PROMPT.format(conversation=conv_text)
        
        # Call LLM
        logger.info(f"Analyzing conversation {conversation.user_id}/{conversation.date} with LLM")
        response = self._call_llm(prompt)
        
        if not response:
            logger.warning("No response from LLM")
            return []
        
        # Parse response
        data = self._parse_llm_response(response)
        if not data or 'issues' not in data:
            logger.warning("Could not parse issues from LLM response")
            return []
        
        # Convert to LLMIssue objects
        issues = []
        for issue_data in data['issues']:
            try:
                # Check if this is a new issue type
                issue_type = issue_data.get('type', 'unknown').lower().replace(' ', '_')
                is_new = issue_type not in self.known_issue_types
                
                issue = LLMIssue(
                    type=issue_type,
                    severity=issue_data.get('severity', 'medium'),
                    description=issue_data.get('description', ''),
                    evidence=issue_data.get('evidence', ''),
                    suggestion=issue_data.get('suggestion', ''),
                    is_new_type=is_new or issue_data.get('is_new_type', False),
                    exchange=conversation.exchanges[-1] if conversation.exchanges else None,
                    source_file=conversation.source_file,
                )
                issues.append(issue)
                
                # Track new issue types
                if issue.is_new_type:
                    logger.info(f"Discovered new issue type: {issue_type}")
                    self.known_issue_types.add(issue_type)
                    
            except Exception as e:
                logger.warning(f"Failed to parse issue: {e}")
                continue
        
        logger.info(f"LLM found {len(issues)} issues (quality: {data.get('overall_quality', '?')}/10)")
        return issues
    
    def generate_detection_patterns(self, issue_type: str, description: str, 
                                     examples: List[str]) -> List[str]:
        """Generate regex patterns to detect a new issue type."""
        prompt = PATTERN_GENERATION_PROMPT.format(
            issue_type=issue_type,
            description=description,
            examples="\n".join(f"- {ex}" for ex in examples[:5]),
        )
        
        response = self._call_llm(prompt)
        if not response:
            return []
        
        try:
            patterns = json.loads(response.strip())
            if isinstance(patterns, list):
                # Validate patterns
                valid_patterns = []
                for p in patterns:
                    try:
                        re.compile(p)
                        valid_patterns.append(p)
                    except re.error:
                        logger.warning(f"Invalid pattern generated: {p}")
                return valid_patterns
        except:
            pass
        
        return []


def analyze_with_llm(conversations: List[Conversation], config: Dict) -> List[Issue]:
    """Analyze conversations using LLM and return all discovered issues."""
    llm_config = config.get('vllm', {})
    analyzer = LLMAnalyzer(
        base_url=llm_config.get('url', 'http://localhost:8080/v1'),
        model=llm_config.get('model', 'default'),
        timeout=llm_config.get('timeout', 120),
    )
    
    all_issues = []
    new_issue_types = {}
    
    for conv in conversations:
        llm_issues = analyzer.analyze_conversation(conv)
        
        for issue in llm_issues:
            # Convert to standard Issue format
            all_issues.append(issue.to_detector_issue())
            
            # Track new issue types for pattern generation
            if issue.is_new_type:
                if issue.type not in new_issue_types:
                    new_issue_types[issue.type] = {
                        'description': issue.description,
                        'examples': [],
                    }
                new_issue_types[issue.type]['examples'].append(issue.evidence)
    
    # Generate patterns for new issue types
    for issue_type, data in new_issue_types.items():
        logger.info(f"Generating patterns for new issue type: {issue_type}")
        patterns = analyzer.generate_detection_patterns(
            issue_type, 
            data['description'],
            data['examples'],
        )
        if patterns:
            logger.info(f"Generated {len(patterns)} patterns for {issue_type}")
            # TODO: Save patterns to patterns.py or a dynamic patterns file
    
    return all_issues
