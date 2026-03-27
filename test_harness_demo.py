#!/usr/bin/env python3
"""Demo harness flow with simulated Qwen output."""

import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

from src.tools.schemas import get_schema
from src.tool_validator import coerce_types, validate_tool_call, format_validation_feedback
from src.tool_parser import extract_tool_call
import json

print("=" * 70)
print("ClawLite Harness Demo - Simulated Qwen 3.5 Output")
print("=" * 70)
print()

# Simulated Qwen outputs (common patterns)
test_cases = [
    {
        "name": "✅ Perfect call",
        "content": '{"tool": "read_file", "args": {"path": "README.md", "limit": 10}}'
    },
    {
        "name": "⚡ Type coercion needed",
        "content": '{"tool": "read_file", "args": {"path": "README.md", "limit": "10"}}'
    },
    {
        "name": "🧹 Markdown wrapped",
        "content": '```json\n{"tool": "read_file", "args": {"path": "README.md"}}\n```'
    },
    {
        "name": "❌ Invalid - empty path",
        "content": '{"tool": "read_file", "args": {"path": ""}}'
    },
    {
        "name": "❌ Invalid - limit too high",
        "content": '{"tool": "read_file", "args": {"path": "README.md", "limit": 1000}}'
    },
]

for tc in test_cases:
    print(f'\n{tc["name"]}')
    print("-" * 60)
    print(f'Input: {tc["content"][:60]}...')
    print()
    
    # Step 1: Extract/parse
    parsed = extract_tool_call(tc["content"])
    if not parsed:
        print("❌ Parse failed")
        continue
    
    print(f'✅ Parsed: tool={parsed["tool"]}, args={parsed["args"]}')
    
    # Step 2: Get schema
    schema = get_schema(parsed["tool"])
    
    # Step 3: Coerce types
    if schema:
        original_args = parsed["args"].copy()
        parsed["args"] = coerce_types(parsed["args"], schema)
        if original_args != parsed["args"]:
            print(f'⚡ Coerced: {original_args} → {parsed["args"]}')
    
    # Step 4: Validate
    is_valid, errors = validate_tool_call(parsed["tool"], parsed["args"])
    
    if is_valid:
        print(f'✅ VALID - Ready to execute!')
    else:
        print(f'❌ INVALID - {len(errors)} error(s):')
        for e in errors:
            print(f'   - {e["path"]}: {e["message"]}')
        
        # Show feedback format
        feedback = format_validation_feedback(
            json.dumps(parsed, indent=2),
            errors,
            parsed["tool"]
        )
        print(f'\n📝 Feedback to LLM:\n{feedback[:200]}...')

print("\n" + "=" * 70)
print("Demo complete!")
print("=" * 70)
