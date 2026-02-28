"""Robust tool call parser with JSON fixer for LLM outputs.

Handles common issues with LLM-generated tool calls:
- Nested braces inside string content (e.g., Python dicts in code)
- Truncated/incomplete JSON from streaming
- Malformed JSON (trailing commas, single quotes, etc.)
- Various tag formats (<tool_call>, <toolcall>, self-closing, etc.)
"""

import json
import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger("clawlite.tool_parser")


def extract_between_tags(text: str) -> Optional[str]:
    """Extract content between <tool_call> and </tool_call> tags.
    
    Uses simple string search, not regex, to avoid issues with
    special characters in JSON content.
    
    Returns:
        The text between tags, or None if no complete tag pair found.
    """
    # Normalize: case-insensitive search for opening tag
    text_lower = text.lower()
    
    # Try multiple tag formats
    open_tags = ['<tool_call>', '<toolcall>']
    close_tags = ['</tool_call>', '</toolcall>']
    
    for open_tag in open_tags:
        start_idx = text_lower.find(open_tag)
        if start_idx == -1:
            continue
        
        content_start = start_idx + len(open_tag)
        
        # Find closing tag
        for close_tag in close_tags:
            end_idx = text_lower.find(close_tag, content_start)
            if end_idx != -1:
                return text[content_start:end_idx].strip()
        
        # No closing tag found — check if we have a complete JSON object
        # (model might omit closing tag)
        remaining = text[content_start:].strip()
        if remaining.startswith('{'):
            logger.debug("Found opening tag without closing tag, attempting JSON extraction")
            return remaining
    
    return None


def find_json_object(text: str) -> Optional[str]:
    """Extract a complete JSON object from text using bracket counting.
    
    Properly handles:
    - Nested braces inside string values (e.g., Python code with dicts)
    - Escaped quotes inside strings
    - Multi-line strings with \\n
    
    Returns:
        The complete JSON object string, or None if not found.
    """
    # Find the first '{'
    start = text.find('{')
    if start == -1:
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    i = start
    
    while i < len(text):
        char = text[i]
        
        if escape_next:
            escape_next = False
            i += 1
            continue
        
        if char == '\\' and in_string:
            escape_next = True
            i += 1
            continue
        
        if char == '"':
            in_string = not in_string
            i += 1
            continue
        
        if in_string:
            i += 1
            continue
        
        # Outside string
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        
        i += 1
    
    # Incomplete — depth never reached 0
    return None


def fix_broken_json(text: str) -> Optional[str]:
    """Attempt to fix common JSON issues from LLM output.
    
    Fixes applied (in order):
    1. Trailing commas before } or ]
    2. Single quotes → double quotes (outside strings)
    3. Unterminated strings → close them
    4. Missing closing brackets → add them
    5. Unescaped control characters inside strings
    
    Returns:
        Fixed JSON string, or None if unfixable.
    """
    if not text or not text.strip():
        return None
    
    text = text.strip()
    
    # Ensure it starts with {
    brace_start = text.find('{')
    if brace_start == -1:
        return None
    text = text[brace_start:]
    
    # Fix 1: Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    
    # Fix 2: Replace single quotes with double quotes (careful with strings)
    # Only do this if the text has no double quotes at all (clearly wrong format)
    if '"' not in text and "'" in text:
        text = text.replace("'", '"')
    
    # Fix 3: Unescaped newlines/tabs inside strings
    # Walk through and escape raw control chars inside string literals
    fixed_chars = []
    in_str = False
    esc = False
    for ch in text:
        if esc:
            fixed_chars.append(ch)
            esc = False
            continue
        if ch == '\\' and in_str:
            fixed_chars.append(ch)
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            fixed_chars.append(ch)
            continue
        if in_str:
            if ch == '\n':
                fixed_chars.append('\\n')
                continue
            elif ch == '\r':
                fixed_chars.append('\\r')
                continue
            elif ch == '\t':
                fixed_chars.append('\\t')
                continue
        fixed_chars.append(ch)
    text = ''.join(fixed_chars)
    
    # Fix 4: Check bracket balance and close if needed
    # Use bracket counting (skip inside strings)
    depth_brace = 0  # {}
    depth_bracket = 0  # []
    in_string = False
    escape_next = False
    last_valid_pos = 0
    string_open = False  # Track if we're in an unterminated string
    
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            string_open = in_string
            last_valid_pos = i
            continue
        if in_string:
            continue
        
        if ch == '{':
            depth_brace += 1
        elif ch == '}':
            depth_brace -= 1
        elif ch == '[':
            depth_bracket += 1
        elif ch == ']':
            depth_bracket -= 1
        
        last_valid_pos = i
    
    # If string is still open, close it
    if string_open:
        text += '"'
        logger.debug("Fixed unterminated string")
    
    # Remove any trailing comma after fixing string
    text = re.sub(r',\s*$', '', text)
    
    # Add missing closing brackets
    if depth_bracket > 0:
        text += ']' * depth_bracket
        logger.debug(f"Added {depth_bracket} missing ']'")
    if depth_brace > 0:
        text += '}' * depth_brace
        logger.debug(f"Added {depth_brace} missing '}}'")
    
    return text


def _try_parse_json(text: str) -> Optional[dict]:
    """Try to parse JSON, with raw_decode fallback."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try raw_decode — handles trailing content after valid JSON
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(text.lstrip())
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    
    return None


def _normalize_tool_call(data: dict) -> Optional[dict]:
    """Normalize various tool call formats to standard {tool, args}.
    
    Handles:
    - {"tool": "name", "args": {...}}  — standard
    - {"name": "name", "arguments": {...}}  — OpenAI style
    - {"tool_name": ..., "parameters": ...}  — alternative
    """
    # Standard format
    tool_name = data.get("tool") or data.get("name") or data.get("tool_name")
    tool_args = data.get("args") or data.get("arguments") or data.get("parameters") or {}
    
    if not tool_name:
        return None
    
    if not isinstance(tool_args, dict):
        return None
    
    return {"tool": tool_name, "args": tool_args}


def extract_tool_call(text: str) -> Optional[dict]:
    """Extract and parse a tool call from LLM output text.
    
    Strategy (in order):
    1. Extract content between <tool_call> tags
    2. Find JSON object using bracket counting
    3. Parse JSON directly
    4. If parse fails, apply JSON fixer and retry
    5. Fallback: regex patterns for non-standard formats
    
    Returns:
        Normalized {"tool": "name", "args": {...}} dict, or None.
    """
    if not text:
        return None
    
    # =========================================================
    # Step 1: Try tag-based extraction
    # =========================================================
    tag_content = extract_between_tags(text)
    
    if tag_content:
        # Step 2: Extract JSON object with bracket counting
        json_str = find_json_object(tag_content)
        
        if json_str:
            # Step 3: Try direct parse
            data = _try_parse_json(json_str)
            if data:
                result = _normalize_tool_call(data)
                if result:
                    logger.debug(f"Parsed tool call via tag+bracket: {result['tool']}")
                    return result
            
            # Step 4: Try JSON fixer
            fixed = fix_broken_json(json_str)
            if fixed:
                data = _try_parse_json(fixed)
                if data:
                    result = _normalize_tool_call(data)
                    if result:
                        logger.info(f"Parsed tool call via JSON fixer: {result['tool']}")
                        return result
        
        # Bracket counting failed — try the raw tag content directly
        data = _try_parse_json(tag_content)
        if data:
            result = _normalize_tool_call(data)
            if result:
                logger.debug(f"Parsed tool call via direct tag content: {result['tool']}")
                return result
        
        # Try fixing raw tag content
        fixed = fix_broken_json(tag_content)
        if fixed:
            data = _try_parse_json(fixed)
            if data:
                result = _normalize_tool_call(data)
                if result:
                    logger.info(f"Parsed tool call via fixed tag content: {result['tool']}")
                    return result
    
    # =========================================================
    # Step 5: No tags found — try standalone JSON patterns
    # =========================================================
    
    # Self-closing tag format: <tool_call/> followed by JSON
    sc_match = re.search(
        r'<tool_?call\s*/>\s*(\{)',
        text,
        re.IGNORECASE,
    )
    if sc_match:
        json_start = sc_match.start(1)
        json_str = find_json_object(text[json_start:])
        if json_str:
            data = _try_parse_json(json_str)
            if not data:
                fixed = fix_broken_json(json_str)
                if fixed:
                    data = _try_parse_json(fixed)
            if data:
                result = _normalize_tool_call(data)
                if result:
                    logger.debug(f"Parsed tool call via self-closing tag: {result['tool']}")
                    return result
    
    # Standalone JSON with "tool" key (no tags at all)
    tool_json_match = re.search(r'\{"tool"\s*:', text)
    if tool_json_match:
        json_str = find_json_object(text[tool_json_match.start():])
        if json_str:
            data = _try_parse_json(json_str)
            if not data:
                fixed = fix_broken_json(json_str)
                if fixed:
                    data = _try_parse_json(fixed)
            if data:
                result = _normalize_tool_call(data)
                if result:
                    logger.debug(f"Parsed tool call via standalone JSON: {result['tool']}")
                    return result
    
    # =========================================================
    # Step 6: Fallback — raw arg patterns (model forgot format entirely)
    # =========================================================
    
    # {"script": "..."} → run_bash
    if '"script"' in text and '<tool' in text.lower():
        match = re.search(r'\{"script"\s*:\s*', text)
        if match:
            json_str = find_json_object(text[match.start():])
            if json_str:
                data = _try_parse_json(json_str)
                if not data:
                    fixed = fix_broken_json(json_str)
                    if fixed:
                        data = _try_parse_json(fixed)
                if data and "script" in data:
                    logger.warning("Recovered raw script JSON → run_bash")
                    return {"tool": "run_bash", "args": data}
    
    # {"command": "..."} → exec
    if '"command"' in text and '<tool' in text.lower():
        match = re.search(r'\{"command"\s*:\s*', text)
        if match:
            json_str = find_json_object(text[match.start():])
            if json_str:
                data = _try_parse_json(json_str)
                if not data:
                    fixed = fix_broken_json(json_str)
                    if fixed:
                        data = _try_parse_json(fixed)
                if data and "command" in data:
                    logger.warning("Recovered raw command JSON → exec")
                    return {"tool": "exec", "args": data}
    
    return None


def has_pending_tool_call(text: str) -> bool:
    """Check if text contains an incomplete/in-progress tool call.
    
    Used to determine if we should hide streaming content from user
    (tool call is being generated but not yet complete).
    
    Returns:
        True if there's an opening <tool_call> tag without a closing tag.
    """
    text_lower = text.lower()
    
    for open_tag in ['<tool_call>', '<toolcall>']:
        if open_tag in text_lower:
            # Check for any closing tag
            has_close = any(
                ct in text_lower
                for ct in ['</tool_call>', '</toolcall>']
            )
            if not has_close:
                return True
    
    return False
