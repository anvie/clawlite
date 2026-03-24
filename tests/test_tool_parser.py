"""Tests for tool_parser module."""

import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tool_parser import (
    extract_tool_call,
    extract_between_tags,
    find_json_object,
    fix_broken_json,
    has_pending_tool_call,
)


def test_simple_tool_call():
    """Basic tool call with tags."""
    text = '<tool_call>\n{"tool": "exec", "args": {"command": "ls -la"}}\n</tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "exec"
    assert result["args"]["command"] == "ls -la"
    print("✅ test_simple_tool_call")


def test_write_file_with_python_code():
    """write_file with Python code containing nested braces — THE main bug."""
    python_code = '''#!/usr/bin/env python3
"""Invoice CRUD System"""

import sqlite3
import json

def create_invoice(data):
    """Create a new invoice."""
    conn = sqlite3.connect('invoice.db')
    cursor = conn.cursor()
    defaults = {'status': 'draft', 'items': []}
    merged = {**defaults, **data}
    cursor.execute(
        "INSERT INTO invoices (customer, data) VALUES (?, ?)",
        (merged['customer'], json.dumps(merged))
    )
    conn.commit()
    result = {'id': cursor.lastrowid, 'status': 'created'}
    conn.close()
    return result

def read_invoice(invoice_id=None):
    """Read invoices."""
    conn = sqlite3.connect('invoice.db')
    if invoice_id:
        row = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        return {'id': row[0], 'data': json.loads(row[1])} if row else {}
    rows = conn.execute("SELECT * FROM invoices").fetchall()
    return [{'id': r[0], 'data': json.loads(r[1])} for r in rows]

def update_invoice(invoice_id, **kwargs):
    """Update an invoice."""
    existing = read_invoice(invoice_id)
    if not existing:
        return {'error': 'not found'}
    updated = {**existing['data'], **kwargs}
    conn = sqlite3.connect('invoice.db')
    conn.execute("UPDATE invoices SET data=? WHERE id=?", (json.dumps(updated), invoice_id))
    conn.commit()
    return {'status': 'updated', 'id': invoice_id}

if __name__ == "__main__":
    print(create_invoice({'customer': 'Test', 'total': 100000}))
'''
    
    # Build the tool call as the model would
    tool_obj = {"tool": "write_file", "args": {"path": "invoice.py", "content": python_code}}
    tool_json = json.dumps(tool_obj)
    text = f"Baik, saya buatkan script invoice.py:\n\n<tool_call>\n{tool_json}\n</tool_call>"
    
    result = extract_tool_call(text)
    assert result is not None, f"Failed to extract tool call from write_file with Python code"
    assert result["tool"] == "write_file"
    assert result["args"]["path"] == "invoice.py"
    assert "def create_invoice" in result["args"]["content"]
    assert "def read_invoice" in result["args"]["content"]
    assert "{'id': cursor.lastrowid" in result["args"]["content"]
    print("✅ test_write_file_with_python_code")


def test_nested_dicts_in_content():
    """Content with multiple nested dict literals."""
    content = 'data = {"name": "test", "config": {"key": "val", "nested": {"deep": true}}}\nprint(data)'
    tool_obj = {"tool": "write_file", "args": {"path": "test.py", "content": content}}
    tool_json = json.dumps(tool_obj)
    text = f"<tool_call>\n{tool_json}\n</tool_call>"
    
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "write_file"
    assert '{"name": "test"' in result["args"]["content"]
    print("✅ test_nested_dicts_in_content")


def test_empty_args():
    """Tool with empty args."""
    text = '<tool_call>\n{"tool": "list_dir", "args": {}}\n</tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "list_dir"
    assert result["args"] == {}
    print("✅ test_empty_args")


def test_no_closing_tag():
    """Tool call without closing tag but complete JSON."""
    text = '<tool_call>\n{"tool": "exec", "args": {"command": "pwd"}}'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "exec"
    print("✅ test_no_closing_tag")


def test_incomplete_tool_call():
    """Incomplete tool call (still streaming) — should return None."""
    text = '<tool_call>\n{"tool": "write_file", "args": {"path": "test.py", "content": "def foo():'
    result = extract_tool_call(text)
    # JSON fixer might recover this — check if it does
    if result is not None:
        # Fixer managed to close it — that's acceptable
        assert result["tool"] == "write_file"
        print("✅ test_incomplete_tool_call (recovered by fixer)")
    else:
        print("✅ test_incomplete_tool_call (correctly returned None)")


def test_trailing_comma():
    """JSON with trailing comma."""
    text = '<tool_call>\n{"tool": "exec", "args": {"command": "ls",}}\n</tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "exec"
    assert result["args"]["command"] == "ls"
    print("✅ test_trailing_comma")


def test_self_closing_tag():
    """Self-closing <tool_call/> format."""
    text = 'Let me check.\n<tool_call/>\n{"tool": "exec", "args": {"command": "ls"}}'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "exec"
    print("✅ test_self_closing_tag")


def test_standalone_json():
    """Standalone JSON without any tags."""
    text = 'Sure, let me run that.\n{"tool": "exec", "args": {"command": "ls -la"}}\n'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "exec"
    print("✅ test_standalone_json")


def test_openai_format():
    """OpenAI-style format with "name" and "arguments"."""
    text = '<tool_call>\n{"name": "read_file", "arguments": {"path": "README.md"}}\n</tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "read_file"
    assert result["args"]["path"] == "README.md"
    print("✅ test_openai_format")


def test_case_insensitive_tags():
    """Tags should be case-insensitive."""
    text = '<Tool_Call>\n{"tool": "exec", "args": {"command": "pwd"}}\n</Tool_Call>'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "exec"
    print("✅ test_case_insensitive_tags")


def test_toolcall_variant():
    """<toolcall> without underscore."""
    text = '<toolcall>\n{"tool": "exec", "args": {"command": "date"}}\n</toolcall>'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "exec"
    print("✅ test_toolcall_variant")


def test_thinking_then_tool_call():
    """Thinking content followed by tool call."""
    text = '''<think>
I need to read the file first to understand the structure.
Let me check what's in the workspace.
</think>

Sure, let me check that.

<tool_call>
{"tool": "read_file", "args": {"path": "config.yaml"}}
</tool_call>'''
    
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "read_file"
    assert result["args"]["path"] == "config.yaml"
    print("✅ test_thinking_then_tool_call")


def test_multiline_script():
    """run_bash with multiline script containing special chars."""
    script = "#!/bin/bash\nset -e\nfor f in *.py; do\n  echo \"Processing: $f\"\n  python3 \"$f\" || { echo \"Failed: $f\"; exit 1; }\ndone\necho \"All done!\""
    tool_obj = {"tool": "run_bash", "args": {"script": script}}
    tool_json = json.dumps(tool_obj)
    text = f"<tool_call>\n{tool_json}\n</tool_call>"
    
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "run_bash"
    assert "for f in *.py" in result["args"]["script"]
    print("✅ test_multiline_script")


def test_escaped_quotes_in_content():
    """Content with lots of escaped quotes."""
    content = 'print("Hello \\"World\\"")\ndata = {"key": "value with \\"quotes\\""}'
    tool_obj = {"tool": "write_file", "args": {"path": "test.py", "content": content}}
    tool_json = json.dumps(tool_obj)
    text = f"<tool_call>\n{tool_json}\n</tool_call>"
    
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "write_file"
    print("✅ test_escaped_quotes_in_content")


def test_text_before_and_after():
    """Tool call surrounded by natural language."""
    text = '''Halo Kak! Baik, saya buatkan file tersebut.

<tool_call>
{"tool": "write_file", "args": {"path": "hello.py", "content": "print('hello')"}}
</tool_call>

File sudah dibuat!'''
    
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "write_file"
    assert result["args"]["content"] == "print('hello')"
    print("✅ test_text_before_and_after")


def test_no_tool_call():
    """Plain text with no tool call at all."""
    text = "Halo! Saya bisa membantu Anda. Apa yang perlu saya lakukan?"
    result = extract_tool_call(text)
    assert result is None
    print("✅ test_no_tool_call")


def test_missing_closing_braces():
    """JSON with missing closing braces — fixer should handle."""
    text = '<tool_call>\n{"tool": "exec", "args": {"command": "ls -la"}\n</tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "exec"
    assert result["args"]["command"] == "ls -la"
    print("✅ test_missing_closing_braces")


def test_multiple_closing_braces():
    """Content that generates many closing braces at end."""
    content = "x = {'a': {'b': {'c': 1}}}"
    tool_obj = {"tool": "write_file", "args": {"path": "t.py", "content": content}}
    tool_json = json.dumps(tool_obj)
    text = f"<tool_call>\n{tool_json}\n</tool_call>"
    
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "write_file"
    assert result["args"]["content"] == content
    print("✅ test_multiple_closing_braces")


def test_raw_script_fallback():
    """Model outputs raw {"script": "..."} with tool tag."""
    text = '<tool_call>\n{"script": "ls -la /workspace"}\n</tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    assert result["tool"] == "run_bash"
    assert result["args"]["script"] == "ls -la /workspace"
    print("✅ test_raw_script_fallback")


# =========================================================
# Test helper functions directly
# =========================================================

def test_find_json_object_simple():
    """find_json_object with simple JSON."""
    text = '  {"key": "value", "num": 42}  '
    result = find_json_object(text)
    assert result == '{"key": "value", "num": 42}'
    print("✅ test_find_json_object_simple")


def test_find_json_object_nested():
    """find_json_object with deeply nested content."""
    text = '{"outer": {"inner": {"deep": "val"}}, "other": "x"}'
    result = find_json_object(text)
    assert result == text
    data = json.loads(result)
    assert data["outer"]["inner"]["deep"] == "val"
    print("✅ test_find_json_object_nested")


def test_find_json_object_braces_in_string():
    """find_json_object with braces inside string values."""
    text = '{"tool": "write_file", "args": {"path": "t.py", "content": "x = {1: {2: 3}}"}}'
    result = find_json_object(text)
    assert result == text
    data = json.loads(result)
    assert data["args"]["content"] == "x = {1: {2: 3}}"
    print("✅ test_find_json_object_braces_in_string")


def test_find_json_object_incomplete():
    """find_json_object with incomplete JSON."""
    text = '{"tool": "write_file", "args": {"content": "hello'
    result = find_json_object(text)
    assert result is None
    print("✅ test_find_json_object_incomplete")


def test_fix_broken_json_trailing_comma():
    """fix_broken_json removes trailing commas."""
    text = '{"key": "value",}'
    result = fix_broken_json(text)
    assert result is not None
    data = json.loads(result)
    assert data["key"] == "value"
    print("✅ test_fix_broken_json_trailing_comma")


def test_fix_broken_json_unclosed():
    """fix_broken_json closes unclosed brackets."""
    text = '{"tool": "exec", "args": {"command": "ls"}'
    result = fix_broken_json(text)
    assert result is not None
    data = json.loads(result)
    assert data["tool"] == "exec"
    print("✅ test_fix_broken_json_unclosed")


def test_fix_broken_json_unterminated_string():
    """fix_broken_json closes unterminated string."""
    text = '{"tool": "exec", "args": {"command": "ls -la'
    result = fix_broken_json(text)
    assert result is not None
    data = json.loads(result)
    assert data["tool"] == "exec"
    assert "ls -la" in data["args"]["command"]
    print("✅ test_fix_broken_json_unterminated_string")


def test_has_pending_tool_call():
    """has_pending_tool_call detection."""
    assert has_pending_tool_call('<tool_call>\n{"tool": "exec') is True
    assert has_pending_tool_call('<tool_call>\n{"tool": "exec"}\n</tool_call>') is False
    assert has_pending_tool_call('Hello world') is False
    assert has_pending_tool_call('<TOOL_CALL>\npartial...') is True
    print("✅ test_has_pending_tool_call")


def test_large_python_script():
    """Stress test: very large Python script with many nested structures."""
    lines = [
        "#!/usr/bin/env python3",
        '"""Large module with many nested structures."""',
        "",
        "import json",
        "import sqlite3",
        "from typing import Dict, List, Optional",
        "",
    ]
    
    # Generate a bunch of functions with nested dicts
    for i in range(20):
        lines.extend([
            f"def function_{i}(data: dict) -> dict:",
            f'    """Function {i} docstring."""',
            f"    config = {{'key_{i}': {{'nested': True, 'value': {i}}}}}",
            f"    result = {{**config, **data}}",
            f"    mapping = {{",
            f"        'a': {{'x': 1, 'y': 2}},",
            f"        'b': {{'x': 3, 'y': 4}},",
            f"    }}",
            f"    return {{'status': 'ok', 'data': result, 'mapping': mapping}}",
            "",
        ])
    
    content = "\n".join(lines)
    tool_obj = {"tool": "write_file", "args": {"path": "big_module.py", "content": content}}
    tool_json = json.dumps(tool_obj)
    text = f"<tool_call>\n{tool_json}\n</tool_call>"
    
    result = extract_tool_call(text)
    assert result is not None, "Failed to parse large Python script tool call"
    assert result["tool"] == "write_file"
    assert "function_0" in result["args"]["content"]
    assert "function_19" in result["args"]["content"]
    assert "'key_19'" in result["args"]["content"]
    print("✅ test_large_python_script")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    
    passed = 0
    failed = 0
    
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ {test_fn.__name__}: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    
    if failed > 0:
        sys.exit(1)
