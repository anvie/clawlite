"""Tool call validation and feedback generation.

Phase 2-3 of Function Calling Harness implementation.

Provides:
1. Lenient JSON parsing (Typia-style)
2. Schema-based type coercion
3. Validation with precise error feedback
4. LLM-readable error formatting
"""

import json
import re
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger("clawlite.tool_validator")


# =============================================================================
# Phase 2: Lenient JSON Parsing
# =============================================================================

def strip_markdown_and_chatter(text: str) -> str:
    """Strip markdown code blocks and prefix chatter from LLM output.
    
    Handles:
    - ```json ... ``` blocks
    - "I'll help you with that!" prefix
    - Leading/trailing whitespace
    """
    if not text:
        return ""
    
    # Strip markdown code blocks
    text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    
    # Find first JSON-like structure
    match = re.search(r'[\{\[]', text)
    if match:
        text = text[match.start():]
    
    return text.strip()


def fix_common_json_issues(text: str) -> str:
    """Fix common JSON issues from LLM output.
    
    Fixes:
    1. Trailing commas before } or ]
    2. Single quotes → double quotes (when no double quotes present)
    3. Incomplete keywords (tru → true, fals → false, nul → null)
    4. Unquoted keys
    5. Unclosed brackets/braces
    """
    if not text:
        return text
    
    # Fix trailing commas
    text = re.sub(r',\s*([}\]])', r'\1', text)
    
    # Fix single quotes (only if no double quotes - clearly wrong format)
    if '"' not in text and "'" in text:
        text = text.replace("'", '"')
    
    # Fix incomplete boolean/null keywords
    text = re.sub(r'\btru\b', 'true', text)
    text = re.sub(r'\bfals\b', 'false', text)
    text = re.sub(r'\bnul\b', 'null', text)
    
    # Fix unquoted keys (simple cases: word followed by colon)
    # Be careful not to break URLs
    text = re.sub(r'(?<!["\w])(\w+)\s*:', r'"\1":', text)
    
    # Count and fix unclosed brackets
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')
    
    if open_braces > 0:
        text += '}' * open_braces
        logger.debug(f"Added {open_braces} closing braces")
    
    if open_brackets > 0:
        text += ']' * open_brackets
        logger.debug(f"Added {open_brackets} closing brackets")
    
    return text


def coerce_types(data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce values to match schema types.
    
    Handles common LLM mistakes:
    - "123" → 123 (string to int)
    - "12.5" → 12.5 (string to float)
    - "true" → True (string to bool)
    - 123 → "123" (number to string)
    """
    if not schema or "properties" not in schema:
        return data
    
    properties = schema.get("properties", {})
    result = dict(data)
    
    for key, prop_schema in properties.items():
        if key not in result:
            continue
        
        value = result[key]
        expected_type = prop_schema.get("type")
        
        if expected_type == "integer" and isinstance(value, str):
            try:
                result[key] = int(value)
                logger.debug(f"Coerced {key}: str '{value}' → int {result[key]}")
            except ValueError:
                pass
        
        elif expected_type == "number" and isinstance(value, str):
            try:
                result[key] = float(value)
                logger.debug(f"Coerced {key}: str '{value}' → float {result[key]}")
            except ValueError:
                pass
        
        elif expected_type == "boolean":
            if isinstance(value, str):
                result[key] = value.lower() in ("true", "1", "yes", "on")
                logger.debug(f"Coerced {key}: str '{value}' → bool {result[key]}")
            elif isinstance(value, (int, float)):
                result[key] = bool(value)
        
        elif expected_type == "string":
            if isinstance(value, (int, float, bool)):
                result[key] = str(value)
                logger.debug(f"Coerced {key}: {type(value).__name__} → str '{result[key]}'")
        
        elif expected_type == "integer" and isinstance(value, float):
            # Float to int (if it's a whole number)
            if value == int(value):
                result[key] = int(value)
                logger.debug(f"Coerced {key}: float {value} → int {result[key]}")
    
    return result


def unwrap_stringified_objects(data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap double-stringified objects (Qwen 3.5 quirk on anyOf/oneOf).
    
    When LLM returns {"config": "{\"key\": \"value\"}"} but schema expects object,
    this unwraps it to {"config": {"key": "value"}}.
    """
    if not schema or "properties" not in schema:
        return data
    
    properties = schema.get("properties", {})
    result = dict(data)
    
    for key, prop_schema in properties.items():
        if key not in result:
            continue
        
        value = result[key]
        expected_type = prop_schema.get("type")
        
        # String that should be object
        if expected_type == "object" and isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    result[key] = parsed
                    logger.debug(f"Unwrapped stringified object: {key}")
            except json.JSONDecodeError:
                pass
        
        # String that should be array
        elif expected_type == "array" and isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    result[key] = parsed
                    logger.debug(f"Unwrapped stringified array: {key}")
            except json.JSONDecodeError:
                pass
        
        # Recursively handle nested objects
        elif expected_type == "object" and isinstance(value, dict):
            nested_schema = prop_schema.get("properties")
            if nested_schema:
                result[key] = unwrap_stringified_objects(
                    value, 
                    {"properties": nested_schema}
                )
    
    return result


def lenient_parse(raw: str, schema: Dict[str, Any] = None) -> Tuple[Optional[Dict], Optional[str]]:
    """Parse broken JSON with lenient handling (Typia-style).
    
    Args:
        raw: Raw LLM output text
        schema: Optional JSON Schema for type coercion
    
    Returns:
        (parsed_data, error_message)
        - On success: (dict, None)
        - On failure: (None, error_string)
    """
    if not raw:
        return None, "Empty input"
    
    # Step 1: Strip markdown and chatter
    text = strip_markdown_and_chatter(raw)
    
    if not text:
        return None, "No JSON content found after stripping markdown"
    
    # Step 2: Fix common issues
    text = fix_common_json_issues(text)
    
    # Step 3: Try to parse
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # Try raw_decode (handles trailing content)
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(text.lstrip())
        except (json.JSONDecodeError, ValueError):
            return None, f"JSON parse error: {e}"
    
    if not isinstance(data, dict):
        return None, f"Expected object, got {type(data).__name__}"
    
    # Step 4: Type coercion if schema provided
    if schema:
        data = coerce_types(data, schema)
        data = unwrap_stringified_objects(data, schema)
    
    return data, None


# =============================================================================
# Phase 3: Schema Validation
# =============================================================================

def validate_against_schema(
    data: Dict[str, Any],
    schema: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Validate data against JSON Schema.
    
    Returns:
        (is_valid, errors)
        errors = [{"path": "...", "expected": "...", "got": "...", "message": "..."}]
    """
    errors = []
    
    if not schema:
        return True, []
    
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    # Check required fields
    for field in required:
        if field not in data:
            errors.append({
                "path": field,
                "expected": "required field",
                "got": "missing",
                "message": f"Missing required field: {field}"
            })
    
    # Validate each field
    for key, value in data.items():
        if key not in properties:
            continue  # Allow extra fields
        
        prop_schema = properties[key]
        field_errors = _validate_field(key, value, prop_schema)
        errors.extend(field_errors)
    
    return len(errors) == 0, errors


def _validate_field(
    path: str,
    value: Any,
    schema: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Validate a single field against its schema."""
    errors = []
    expected_type = schema.get("type")
    
    # Type check
    if expected_type:
        type_valid, type_error = _check_type(value, expected_type)
        if not type_valid:
            errors.append({
                "path": path,
                "expected": expected_type,
                "got": type(value).__name__,
                "value": repr(value)[:50],
                "message": type_error
            })
            return errors  # Skip other checks if type is wrong
    
    # String constraints
    if expected_type == "string" and isinstance(value, str):
        min_len = schema.get("minLength")
        max_len = schema.get("maxLength")
        pattern = schema.get("pattern")
        
        if min_len is not None and len(value) < min_len:
            errors.append({
                "path": path,
                "expected": f"string with minLength {min_len}",
                "got": f"string of length {len(value)}",
                "message": f"String too short (min {min_len} chars)"
            })
        
        if max_len is not None and len(value) > max_len:
            errors.append({
                "path": path,
                "expected": f"string with maxLength {max_len}",
                "got": f"string of length {len(value)}",
                "message": f"String too long (max {max_len} chars)"
            })
        
        if pattern and not re.match(pattern, value):
            errors.append({
                "path": path,
                "expected": f"string matching pattern {pattern}",
                "got": repr(value)[:30],
                "message": f"String doesn't match required pattern"
            })
    
    # Number constraints
    if expected_type in ("integer", "number") and isinstance(value, (int, float)):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        
        if minimum is not None and value < minimum:
            errors.append({
                "path": path,
                "expected": f"{expected_type} >= {minimum}",
                "got": str(value),
                "message": f"Value {value} is below minimum {minimum}"
            })
        
        if maximum is not None and value > maximum:
            errors.append({
                "path": path,
                "expected": f"{expected_type} <= {maximum}",
                "got": str(value),
                "message": f"Value {value} is above maximum {maximum}"
            })
    
    # Enum check
    enum_values = schema.get("enum")
    if enum_values and value not in enum_values:
        errors.append({
            "path": path,
            "expected": f"one of {enum_values}",
            "got": repr(value)[:30],
            "message": f"Value must be one of: {', '.join(map(str, enum_values))}"
        })
    
    return errors


def _check_type(value: Any, expected: str) -> Tuple[bool, str]:
    """Check if value matches expected JSON Schema type."""
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    
    expected_python = type_map.get(expected)
    if expected_python is None:
        return True, ""  # Unknown type, allow
    
    if isinstance(expected_python, tuple):
        if isinstance(value, expected_python):
            # Special case: float should not be int for "integer" type
            if expected == "integer" and isinstance(value, float) and value != int(value):
                return False, f"Expected integer, got float {value}"
            return True, ""
    else:
        if isinstance(value, expected_python):
            return True, ""
    
    return False, f"Expected {expected}, got {type(value).__name__}"


# =============================================================================
# Feedback Formatting
# =============================================================================

def format_validation_feedback(
    original_json: str,
    errors: List[Dict[str, Any]],
    tool_name: str = None
) -> str:
    """Format validation errors for LLM self-correction (Typia-style).
    
    Returns a formatted string that shows the original JSON with inline
    error comments, making it easy for the LLM to understand what to fix.
    """
    if not errors:
        return ""
    
    lines = []
    
    # Header
    lines.append("❌ **Tool call validation failed**\n")
    if tool_name:
        lines.append(f"Tool: `{tool_name}`\n")
    
    # Error summary
    lines.append(f"Found {len(errors)} error(s):\n")
    
    for i, err in enumerate(errors, 1):
        path = err.get("path", "?")
        expected = err.get("expected", "?")
        got = err.get("got", "?")
        message = err.get("message", "")
        
        lines.append(f"{i}. **{path}**: {message}")
        lines.append(f"   - Expected: `{expected}`")
        lines.append(f"   - Got: `{got}`")
        lines.append("")
    
    # Show original with annotations
    lines.append("Your output:")
    lines.append("```json")
    
    try:
        # Pretty print and annotate
        data = json.loads(original_json)
        pretty = json.dumps(data, indent=2)
        
        # Add inline comments for errors
        for err in errors:
            path = err.get("path", "")
            if path:
                # Find the line with this key and add comment
                pattern = rf'("{path}"\s*:\s*[^,\n]+)'
                replacement = rf'\1  // ❌ {err.get("message", "error")}'
                pretty = re.sub(pattern, replacement, pretty, count=1)
        
        lines.append(pretty)
    except:
        lines.append(original_json)
    
    lines.append("```")
    lines.append("\nPlease fix the errors and try again.")
    
    return "\n".join(lines)


def format_parse_error_feedback(raw_text: str, error: str) -> str:
    """Format parse error for LLM self-correction."""
    lines = [
        "❌ **Could not parse tool call**\n",
        f"Error: {error}\n",
        "Your output:",
        "```",
        raw_text[:500] + ("..." if len(raw_text) > 500 else ""),
        "```\n",
        "Please format your tool call as:",
        "```",
        '<tool_call>{"tool": "tool_name", "args": {"param": "value"}}</tool_call>',
        "```"
    ]
    return "\n".join(lines)


# =============================================================================
# Main Entry Points
# =============================================================================

def validate_tool_call(
    tool_name: str,
    args: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Validate tool arguments against schema.
    
    Args:
        tool_name: Name of the tool
        args: Arguments to validate
    
    Returns:
        (is_valid, errors)
    """
    from .tools.schemas import get_schema
    
    schema = get_schema(tool_name)
    if not schema:
        return True, []  # No schema = allow all
    
    return validate_against_schema(args, schema)


def parse_and_validate_tool_call(
    raw_text: str,
    tool_name: str = None
) -> Tuple[Optional[Dict], Optional[str], List[Dict]]:
    """Parse and validate a tool call in one step.
    
    Args:
        raw_text: Raw LLM output containing tool call JSON
        tool_name: Optional tool name (extracted from JSON if not provided)
    
    Returns:
        (parsed_data, parse_error, validation_errors)
        - On parse failure: (None, error_string, [])
        - On validation failure: (data, None, [errors])
        - On success: (data, None, [])
    """
    from .tools.schemas import get_schema
    
    # First, try to determine tool name from the raw text if not provided
    schema = None
    if tool_name:
        schema = get_schema(tool_name)
    
    # Parse with lenient handling
    # For args, we need to extract just the args part
    data, parse_error = lenient_parse(raw_text, schema)
    
    if parse_error:
        return None, parse_error, []
    
    # Extract tool name and args
    extracted_tool = data.get("tool") or data.get("name")
    extracted_args = data.get("args") or data.get("arguments") or data.get("parameters") or {}
    
    if not extracted_tool:
        return None, "No tool name found in JSON", []
    
    # Get schema for the actual tool
    tool_schema = get_schema(extracted_tool)
    
    # Apply type coercion to args
    if tool_schema:
        extracted_args = coerce_types(extracted_args, tool_schema)
        extracted_args = unwrap_stringified_objects(extracted_args, tool_schema)
    
    # Validate
    is_valid, errors = validate_against_schema(extracted_args, tool_schema)
    
    # Return normalized structure
    normalized = {
        "tool": extracted_tool,
        "args": extracted_args
    }
    
    if not is_valid:
        return normalized, None, errors
    
    return normalized, None, []
