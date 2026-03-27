"""Tests for Function Calling Harness (Phases 1-3).

Run with: pytest tests/test_harness.py -v
"""

import pytest
import json
from src.tool_validator import (
    strip_markdown_and_chatter,
    fix_common_json_issues,
    coerce_types,
    unwrap_stringified_objects,
    lenient_parse,
    validate_against_schema,
    format_validation_feedback,
    parse_and_validate_tool_call,
)
from src.tools.schemas import TOOL_SCHEMAS, get_schema


class TestLenientParsing:
    """Phase 2: Lenient JSON parsing tests."""
    
    def test_strip_markdown_code_block(self):
        raw = '```json\n{"tool": "read_file", "args": {"path": "/etc/hosts"}}\n```'
        result, err = lenient_parse(raw)
        assert err is None
        assert result["tool"] == "read_file"
    
    def test_strip_markdown_without_language(self):
        raw = '```\n{"tool": "exec", "args": {"command": "ls"}}\n```'
        result, err = lenient_parse(raw)
        assert err is None
        assert result["tool"] == "exec"
    
    def test_strip_prefix_chatter(self):
        raw = "I'll help you with that! Here's the tool call:\n{\"tool\": \"read_file\", \"args\": {\"path\": \"test.txt\"}}"
        result, err = lenient_parse(raw)
        assert err is None
        assert result["tool"] == "read_file"
    
    def test_fix_trailing_comma(self):
        raw = '{"tool": "read_file", "args": {"path": "test.txt",}}'
        result, err = lenient_parse(raw)
        assert err is None
        assert result["args"]["path"] == "test.txt"
    
    def test_fix_single_quotes(self):
        raw = "{'tool': 'read_file', 'args': {'path': 'test.txt'}}"
        result, err = lenient_parse(raw)
        assert err is None
        assert result["tool"] == "read_file"
    
    def test_fix_incomplete_keywords(self):
        raw = '{"tool": "list_dir", "args": {"recursive": tru}}'
        result, err = lenient_parse(raw)
        assert err is None
        assert result["args"]["recursive"] == True
    
    def test_fix_unclosed_brace(self):
        raw = '{"tool": "exec", "args": {"command": "ls -la"}'
        result, err = lenient_parse(raw)
        assert err is None
        assert result["tool"] == "exec"
    
    def test_type_coercion_string_to_int(self):
        schema = {"properties": {"limit": {"type": "integer"}}}
        data = {"limit": "100"}
        result = coerce_types(data, schema)
        assert result["limit"] == 100
        assert isinstance(result["limit"], int)
    
    def test_type_coercion_string_to_bool(self):
        schema = {"properties": {"recursive": {"type": "boolean"}}}
        data = {"recursive": "true"}
        result = coerce_types(data, schema)
        assert result["recursive"] == True
    
    def test_type_coercion_int_to_string(self):
        schema = {"properties": {"path": {"type": "string"}}}
        data = {"path": 123}
        result = coerce_types(data, schema)
        assert result["path"] == "123"
    
    def test_unwrap_stringified_object(self):
        # Qwen 3.5 quirk: double-stringify objects
        schema = {"properties": {"config": {"type": "object"}}}
        data = {"config": '{"key": "value"}'}
        result = unwrap_stringified_objects(data, schema)
        assert result["config"] == {"key": "value"}
    
    def test_unwrap_stringified_array(self):
        schema = {"properties": {"items": {"type": "array"}}}
        data = {"items": '["a", "b", "c"]'}
        result = unwrap_stringified_objects(data, schema)
        assert result["items"] == ["a", "b", "c"]


class TestSchemaValidation:
    """Phase 3: Schema validation tests."""
    
    def test_valid_read_file(self):
        schema = get_schema("read_file")
        args = {"path": "test.txt", "offset": 1, "limit": 100}
        is_valid, errors = validate_against_schema(args, schema)
        assert is_valid
        assert len(errors) == 0
    
    def test_missing_required_field(self):
        schema = get_schema("read_file")
        args = {"offset": 1}  # missing 'path'
        is_valid, errors = validate_against_schema(args, schema)
        assert not is_valid
        assert any(e["path"] == "path" for e in errors)
    
    def test_wrong_type(self):
        schema = get_schema("read_file")
        args = {"path": 123}  # should be string
        is_valid, errors = validate_against_schema(args, schema)
        assert not is_valid
        assert any(e["expected"] == "string" for e in errors)
    
    def test_below_minimum(self):
        schema = get_schema("read_file")
        args = {"path": "test.txt", "offset": 0}  # minimum is 1
        is_valid, errors = validate_against_schema(args, schema)
        assert not is_valid
        assert any("minimum" in e.get("message", "") for e in errors)
    
    def test_above_maximum(self):
        schema = get_schema("read_file")
        args = {"path": "test.txt", "limit": 1000}  # maximum is 500
        is_valid, errors = validate_against_schema(args, schema)
        assert not is_valid
        assert any("maximum" in e.get("message", "") for e in errors)
    
    def test_string_too_short(self):
        schema = get_schema("memory_log")
        args = {"content": "hi"}  # minLength is 10
        is_valid, errors = validate_against_schema(args, schema)
        assert not is_valid
        assert any("too short" in e.get("message", "") for e in errors)
    
    def test_enum_validation(self):
        schema = get_schema("find_files")
        args = {"name_pattern": "*.py", "type": "invalid"}  # should be file/dir/all
        is_valid, errors = validate_against_schema(args, schema)
        assert not is_valid
        assert any("must be one of" in e.get("message", "") for e in errors)
    
    def test_pattern_validation(self):
        schema = get_schema("web_fetch")
        args = {"url": "not-a-url"}  # should start with http
        is_valid, errors = validate_against_schema(args, schema)
        assert not is_valid
        assert any("pattern" in e.get("message", "") for e in errors)
    
    def test_valid_url(self):
        schema = get_schema("web_fetch")
        args = {"url": "https://example.com"}
        is_valid, errors = validate_against_schema(args, schema)
        assert is_valid


class TestFeedbackFormatting:
    """Test error feedback formatting."""
    
    def test_format_validation_feedback(self):
        errors = [
            {"path": "path", "expected": "string", "got": "integer", "message": "Expected string, got integer"}
        ]
        feedback = format_validation_feedback('{"path": 123}', errors, "read_file")
        assert "❌" in feedback
        assert "read_file" in feedback
        assert "Expected string" in feedback
    
    def test_format_multiple_errors(self):
        errors = [
            {"path": "path", "expected": "string", "got": "integer", "message": "Error 1"},
            {"path": "limit", "expected": "integer", "got": "string", "message": "Error 2"},
        ]
        feedback = format_validation_feedback('{"path": 123, "limit": "abc"}', errors)
        assert "2 error(s)" in feedback


class TestIntegration:
    """End-to-end integration tests."""
    
    def test_parse_and_validate_success(self):
        raw = '{"tool": "read_file", "args": {"path": "test.txt", "limit": 100}}'
        result, parse_err, val_errors = parse_and_validate_tool_call(raw)
        assert parse_err is None
        assert len(val_errors) == 0
        assert result["tool"] == "read_file"
        assert result["args"]["path"] == "test.txt"
    
    def test_parse_and_validate_with_coercion(self):
        # limit is string but should be coerced to int
        raw = '{"tool": "read_file", "args": {"path": "test.txt", "limit": "50"}}'
        result, parse_err, val_errors = parse_and_validate_tool_call(raw)
        assert parse_err is None
        assert len(val_errors) == 0
        assert result["args"]["limit"] == 50
        assert isinstance(result["args"]["limit"], int)
    
    def test_parse_and_validate_markdown_wrapped(self):
        raw = '''```json
{"tool": "web_search", "args": {"query": "python tutorial", "max_results": 5}}
```'''
        result, parse_err, val_errors = parse_and_validate_tool_call(raw)
        assert parse_err is None
        assert len(val_errors) == 0
        assert result["tool"] == "web_search"
    
    def test_parse_and_validate_with_validation_error(self):
        raw = '{"tool": "read_file", "args": {"path": ""}}'  # empty path (minLength 1)
        result, parse_err, val_errors = parse_and_validate_tool_call(raw)
        assert parse_err is None
        assert len(val_errors) > 0  # Should have validation error
    
    def test_parse_failure(self):
        raw = 'This is not JSON at all'
        result, parse_err, val_errors = parse_and_validate_tool_call(raw)
        assert result is None
        assert parse_err is not None


class TestSchemaCompleteness:
    """Verify all expected tools have schemas."""
    
    def test_core_tools_have_schemas(self):
        core_tools = [
            "read_file", "write_file", "edit_file", "list_dir",
            "exec", "run_bash",
            "grep", "find_files",
            "web_search", "web_fetch",
        ]
        for tool in core_tools:
            schema = get_schema(tool)
            assert schema, f"Missing schema for {tool}"
            assert "properties" in schema, f"Schema for {tool} has no properties"
    
    def test_all_schemas_have_required_field(self):
        for name, schema in TOOL_SCHEMAS.items():
            assert "required" in schema, f"Schema {name} missing 'required' field"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
