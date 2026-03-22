"""Conversation parser for ClawLite AutoImprove.

Parses JSONL conversation logs into structured data.
"""

import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import glob
import re

logger = logging.getLogger('autoimprove.analyzer.parser')


@dataclass
class ToolCall:
    """Represents a tool call made by the agent."""
    name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    duration_ms: Optional[int] = None


@dataclass
class Exchange:
    """Represents a single user→assistant exchange."""
    user_message: str
    assistant_response: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    duration_ms: Optional[int] = None
    user_id: str = ""
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
    
    def get_tool_sequence(self) -> List[str]:
        """Return sequence of tool names called."""
        return [tc.name for tc in self.tool_calls]


@dataclass
class Conversation:
    """Represents a full conversation session."""
    user_id: str
    date: str
    exchanges: List[Exchange] = field(default_factory=list)
    source_file: str = ""
    
    @property
    def exchange_count(self) -> int:
        return len(self.exchanges)
    
    @property
    def total_tool_calls(self) -> int:
        return sum(len(ex.tool_calls) for ex in self.exchanges)


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime."""
    if not ts_str:
        return None
    try:
        # Handle various formats
        ts_str = ts_str.replace('Z', '+00:00')
        return datetime.fromisoformat(ts_str)
    except ValueError:
        logger.warning(f"Could not parse timestamp: {ts_str}")
        return None


def extract_tool_calls(content: str) -> List[ToolCall]:
    """Extract tool calls from assistant message content."""
    tool_calls = []
    
    # Pattern for <tool_call> XML format
    tool_pattern = re.compile(
        r'<tool_call>\s*(\w+)\s*\((.*?)\)\s*</tool_call>',
        re.DOTALL
    )
    
    # Also check for JSON tool call format
    json_pattern = re.compile(
        r'\{"tool":\s*"(\w+)",\s*"args":\s*(\{.*?\})\}',
        re.DOTALL
    )
    
    for match in tool_pattern.finditer(content):
        name = match.group(1)
        args_str = match.group(2)
        try:
            args = json.loads(f'{{{args_str}}}') if args_str else {}
        except json.JSONDecodeError:
            args = {'raw': args_str}
        tool_calls.append(ToolCall(name=name, arguments=args))
    
    for match in json_pattern.finditer(content):
        name = match.group(1)
        args_str = match.group(2)
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {'raw': args_str}
        tool_calls.append(ToolCall(name=name, arguments=args))
    
    return tool_calls


def parse_jsonl_file(filepath: Path) -> List[Dict[str, Any]]:
    """Parse a JSONL file into list of message dicts."""
    messages = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    messages.append(msg)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON at {filepath}:{line_num}: {e}")
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
    return messages


def parse_structured_tool_calls(tool_calls_data: List[Dict[str, Any]]) -> List[ToolCall]:
    """Parse structured tool_calls from JSONL format."""
    tool_calls = []
    for tc in tool_calls_data:
        # Handle both "tool" and "name" keys for tool name
        name = tc.get('tool') or tc.get('name', 'unknown')
        # Handle both "args" and "arguments" keys
        args = tc.get('args') or tc.get('arguments', {})
        result = tc.get('result')
        duration = tc.get('duration_ms')
        
        tool_calls.append(ToolCall(
            name=name,
            arguments=args,
            result=result,
            duration_ms=duration,
        ))
    return tool_calls


def messages_to_exchanges(messages: List[Dict[str, Any]], user_id: str) -> List[Exchange]:
    """Convert raw messages to Exchange objects."""
    exchanges = []
    current_user_msg = None
    current_user_ts = None
    
    for msg in messages:
        role = msg.get('role', '')
        content = msg.get('content', '')
        ts = parse_timestamp(msg.get('ts', ''))
        
        if role == 'user':
            current_user_msg = content
            current_user_ts = ts
        elif role == 'assistant' and current_user_msg:
            # Calculate duration if timestamps available
            duration_ms = None
            if current_user_ts and ts:
                delta = ts - current_user_ts
                duration_ms = int(delta.total_seconds() * 1000)
            
            # First check for structured tool_calls field, then fall back to text extraction
            structured_tc = msg.get('tool_calls', [])
            if structured_tc:
                tool_calls = parse_structured_tool_calls(structured_tc)
            else:
                tool_calls = extract_tool_calls(content)
            
            exchange = Exchange(
                user_message=current_user_msg,
                assistant_response=content,
                tool_calls=tool_calls,
                timestamp=current_user_ts,
                duration_ms=duration_ms,
                user_id=user_id,
            )
            exchanges.append(exchange)
            current_user_msg = None
            current_user_ts = None
    
    return exchanges


def get_file_hash(filepath: Path) -> str:
    """Get a hash of file path + modification time + size."""
    stat = filepath.stat()
    content = f"{filepath}:{stat.st_mtime}:{stat.st_size}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def load_conversations(
    workspace_path: str,
    since: Optional[datetime] = None,
    min_exchanges: int = 2,
    processed_files: Optional[List[str]] = None,
) -> Tuple[List[Conversation], List[str]]:
    """Load all conversations from workspace.
    
    Args:
        workspace_path: Path to ClawLite workspace
        since: Only load conversations since this datetime
        min_exchanges: Skip conversations with fewer exchanges
        processed_files: List of file hashes already processed (skip these)
        
    Returns:
        Tuple of (List of Conversation objects, List of new file hashes)
    """
    conversations = []
    new_file_hashes = []
    workspace = Path(workspace_path)
    processed_set = set(processed_files or [])
    
    # Find all conversation files
    pattern = str(workspace / "users" / "*" / "conversations" / "convo-*.jsonl")
    convo_files = glob.glob(pattern)
    
    logger.info(f"Found {len(convo_files)} conversation files")
    
    for filepath in convo_files:
        filepath = Path(filepath)
        
        # Check if already processed (by file hash)
        file_hash = get_file_hash(filepath)
        if file_hash in processed_set:
            logger.debug(f"Skipping already processed: {filepath}")
            continue
        
        # Extract user_id from path
        # workspace/users/{user_id}/conversations/convo-YYYY-MM-DD.jsonl
        parts = filepath.parts
        try:
            users_idx = parts.index('users')
            user_id = parts[users_idx + 1]
        except (ValueError, IndexError):
            logger.warning(f"Could not extract user_id from {filepath}")
            continue
        
        # Extract date from filename
        filename = filepath.name  # convo-YYYY-MM-DD.jsonl
        date_match = re.search(r'convo-(\d{4}-\d{2}-\d{2})\.jsonl', filename)
        if not date_match:
            logger.warning(f"Could not extract date from {filename}")
            continue
        
        date_str = date_match.group(1)
        
        # Filter by date if since is provided
        if since:
            file_date = datetime.strptime(date_str, '%Y-%m-%d')
            if file_date.date() < since.date():
                continue
        
        # Parse the file
        messages = parse_jsonl_file(filepath)
        exchanges = messages_to_exchanges(messages, user_id)
        
        if len(exchanges) < min_exchanges:
            logger.debug(f"Skipping {filepath}: only {len(exchanges)} exchanges")
            continue
        
        convo = Conversation(
            user_id=user_id,
            date=date_str,
            exchanges=exchanges,
            source_file=str(filepath),
        )
        conversations.append(convo)
        new_file_hashes.append(file_hash)
        logger.info(f"Loaded {len(exchanges)} exchanges from {filepath} (hash: {file_hash})")
    
    return conversations, new_file_hashes


def get_conversations_since(
    workspace_path: str,
    hours: int = 24,
    min_exchanges: int = 2,
) -> List[Conversation]:
    """Convenience function to load recent conversations.
    
    Args:
        workspace_path: Path to ClawLite workspace
        hours: Load conversations from the last N hours
        min_exchanges: Skip conversations with fewer exchanges
        
    Returns:
        List of Conversation objects
    """
    since = datetime.now() - timedelta(hours=hours)
    return load_conversations(workspace_path, since=since, min_exchanges=min_exchanges)
