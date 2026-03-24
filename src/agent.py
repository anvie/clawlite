"""Agent loop with tool calling."""

import json
import re
import os
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, List, Dict, Any

from .llm import (
    stream_generate, 
    supports_native_tools, 
    stream_with_tools,
    convert_tools_to_anthropic_format,
    build_tool_result_message,
    ToolResult as LLMToolResult,
    is_vision_enabled,
)
from .tools import get_tool, format_tools_for_prompt, list_tools, SKILL_TOOLS
from .tool_parser import extract_tool_call, has_pending_tool_call
from .translation import translate_to_english, translate_to_indonesian, is_translation_enabled
from .context import load_full_context, ensure_user_dir, is_bot_unconfigured, load_conversation_history
from .config import get as config_get
from .errors import sanitize_error, format_user_error
from .loop_detector import LoopDetector

logger = logging.getLogger("clawlite.agent")


def get_history_limit() -> int:
    """Get max history messages from config (default: 10)."""
    return int(config_get("agent.history_limit", 10))


def strip_thinking_tags(text: str) -> str:
    """Strip thinking/reasoning content from response, keeping only actual response.
    
    Handles multiple formats:
    1. Qwen3.5/vLLM: "Thinking Process:\n...\n</think>\n\nActual response"
       (No opening <think> tag, just content ending with </think>)
    2. Standard: "<think>...</think>Actual response"
    3. Wrapped: "<response>Actual response</response>"
    4. Fallback: Regex patterns for prose-style thinking leaks
    """
    if not text:
        return ""
    
    # PRIMARY: Qwen3.5/vLLM format - extract content AFTER </think>
    # This handles the case where vLLM returns "Thinking Process:\n...\n</think>\n\nResponse"
    think_end_match = re.search(r'</think>\s*', text, flags=re.IGNORECASE)
    if think_end_match:
        after_think = text[think_end_match.end():].strip()
        if after_think:
            # Successfully extracted response after thinking
            return after_think
    
    # SECOND: Check if response is wrapped in <response> tags - extract only that
    response_match = re.search(r'<response>([\s\S]*?)</response>', text, flags=re.IGNORECASE)
    if response_match:
        # Model wrapped the actual response - use only that content
        text = response_match.group(1).strip()
    
    # FALLBACK: Remove complete thinking blocks (various tag formats)
    text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<thought>[\s\S]*?</thought>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<thinking>[\s\S]*?</thinking>', '', text, flags=re.IGNORECASE)
    
    # Remove orphaned/incomplete tags (opening or closing)
    text = re.sub(r'<think>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</think>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<thought>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</thought>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<thinking>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</thinking>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<response>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</response>', '', text, flags=re.IGNORECASE)
    
    # Remove leaked <toolcall> blocks in various formats
    text = re.sub(r'<toolcall>[\s\S]*?</toolcall>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', text, flags=re.IGNORECASE)
    # Self-closing tag followed by JSON on same or next line
    text = re.sub(r'<toolcall\s*/>\s*\{[^}]*\}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<tool_call\s*/>\s*\{[^}]*\}', '', text, flags=re.IGNORECASE)
    # Just the self-closing tags
    text = re.sub(r'<toolcall\s*/>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<tool_call\s*/>', '', text, flags=re.IGNORECASE)
    
    # Remove raw JSON tool calls that leaked ({"tool": ...} patterns)
    text = re.sub(r'\{"tool":\s*"[^"]*"[^}]*\}', '', text)
    text = re.sub(r'\{"name":\s*"[^"]*"[^}]*\}', '', text)
    
    # Remove prose-style internal thinking (common patterns)
    # These are internal monologue that shouldn't be shown to users
    prose_thinking_patterns = [
        # Start of response patterns
        r'^The user is asking[^\n]*\n*',
        r'^I need to [^\n]*\n*',
        r'^Let me [^\n]*\n*',
        r'^Looking at [^\n]*\n*',
        r'^Based on the (tool|previous)[^\n]*\n*',
        r'^I should [^\n]*\n*',
        r'^First,? I (will|should|need)[^\n]*\n*',
        r'^Now I (will|should|need|can)[^\n]*\n*',
        # Numbered list reasoning (e.g., "1. User sent a photo")
        r'^1\.\s+(User|I|The)[^\n]*\n(?:\d+\.[^\n]*\n)*',
        # Mid-response reasoning patterns
        r'^Actually,? (looking|I|the|this)[^\n]*\n*',
        r'^Wait,? (I need|let me|this)[^\n]*\n*',
        r'^This (is confusing|might be|seems)[^\n]*\n*',
        r'^So the (photo|file|image)[^\n]*\n*',
    ]
    for pattern in prose_thinking_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # Remove blocks that look like step-by-step internal reasoning
    # Pattern: multiple lines starting with numbers or "Step"
    text = re.sub(r'(?:^(?:\d+\.|Step \d+:)[^\n]*\n){3,}', '', text, flags=re.MULTILINE)
    
    # Clean up excessive whitespace left behind
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


# Load system prompt
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

# Configuration (from config/clawlite.yaml with defaults)
TOOL_TIMEOUT = config_get('agent.tool_timeout', 30)
LLM_MAX_RETRIES = config_get('agent.retry_attempts', 3)
LLM_RETRY_DELAY = 2  # base delay for exponential backoff
TOTAL_TIME_LIMIT = config_get('agent.total_timeout', 300)
SHOW_TOOL_CALLS = config_get('agent.show_tool_calls', False)  # Show raw tool_call in stream (debug)
DEBUG_TOOL_ERRORS = config_get('agent.debug_tool_errors', True)  # Send failed tool calls as separate message

# Per-tool output limits (chars) - larger for code reading tools
TOOL_OUTPUT_LIMITS = {
    "read_file": 6000,      # Larger for code reading
    "run_bash": 4000,       # Scripts may have longer output
    "run_python": 4000,     # Python output
    "exec": 2000,           # Simple commands
    "grep": 3000,           # Search results
    "find_files": 2000,     # File listings
    "list_dir": 1500,       # Directory listings
    "web_fetch": 5000,      # Web content
    "default": 2000         # Default limit
}


def truncate_tool_output(output: str, tool_name: str) -> str:
    """Truncate tool output with smart notice based on tool type."""
    limit = TOOL_OUTPUT_LIMITS.get(tool_name, TOOL_OUTPUT_LIMITS["default"])
    
    if len(output) <= limit:
        return output
    
    truncated = output[:limit]
    remaining = len(output) - limit
    
    # Smart truncation notice based on tool
    if tool_name == "read_file":
        notice = (
            f"\n\n[TRUNCATED - Showing {limit}/{len(output)} chars]\n"
            f"[File read complete. Use offset parameter to read specific sections if needed]\n"
            f"[⚠️ DO NOT re-read this file - you already have the content above]"
        )
    elif tool_name in ("run_bash", "run_python", "exec"):
        notice = (
            f"\n\n[OUTPUT TRUNCATED - {limit}/{len(output)} chars shown]\n"
            f"[Command executed successfully. {remaining} chars omitted]"
        )
    else:
        notice = f"\n\n[TRUNCATED - {remaining} more chars. Output limit: {limit}]"
    
    return truncated + notice


def format_skill_prompts() -> str:
    """Format skill prompts for inclusion in system prompt."""
    if not SKILL_TOOLS:
        return ""
    
    lines = ["\n## Available Skills\n"]
    for tool_name, tool in SKILL_TOOLS.items():
        skill_data = tool.skill_data
        prompt = skill_data.get('prompt', '').strip()
        if prompt:
            lines.append(f"### {tool_name}")
            lines.append(prompt)
            lines.append("")
    
    return "\n".join(lines) if len(lines) > 1 else ""


def load_system_prompt(user_id: Optional[str] = None) -> str:
    """Load system prompt from file, with onboarding if bot unconfigured.
    
    Args:
        user_id: User ID for filtering tools by access level
    """
    prompt_file = os.path.join(PROMPTS_DIR, "system.md")
    try:
        with open(prompt_file, "r") as f:
            prompt = f.read()
    except FileNotFoundError:
        prompt = get_default_system_prompt(user_id)
    
    # Inject dynamic tools section based on user access level
    tools_section = format_tools_for_prompt(user_id)
    prompt += f"\n\n## Available Tools\n\n{tools_section}"
    
    # Add skill prompts if any skills loaded
    skill_prompts = format_skill_prompts()
    if skill_prompts:
        prompt += "\n" + skill_prompts
    
    # Add onboarding instructions if bot not configured yet
    if is_bot_unconfigured():
        onboarding_file = os.path.join(PROMPTS_DIR, "onboarding.md")
        try:
            with open(onboarding_file, "r") as f:
                prompt += "\n\n" + f.read()
        except FileNotFoundError:
            pass
    
    return prompt


def get_default_system_prompt(user_id: Optional[str] = None) -> str:
    """Default system prompt if file not found.
    
    Args:
        user_id: User ID for filtering tools by access level
    """
    skill_section = format_skill_prompts()
    return f"""You are ClawLite, an agentic AI assistant running in a sandboxed Docker container.
You can use tools to interact with the workspace filesystem and execute commands.

{format_tools_for_prompt(user_id)}
{skill_section}

## Tool Calling Format

When you need to use a tool, output a tool_call block:

<tool_call>
{{"tool": "tool_name", "args": {{"param1": "value1"}}}}
</tool_call>

Wait for the tool result before continuing. You can chain multiple tool calls.

## Rules
1. All file paths are relative to /workspace
2. User-specific files are in users/{{user_id}}/ (memory, USER.md, etc.)
3. Only allowed shell commands can be executed
4. After completing a task, briefly summarize what you did

## Reasoning (CRITICAL)
Before answering ANY question involving logic, physical actions, or real-world scenarios:
1. STOP and think: What is actually being asked?
2. Consider physical requirements (e.g., "to wash a car, the car must BE there")
3. Trace through the scenario step-by-step
4. Ask yourself: "Does my answer make practical sense?"
5. If unsure, reason out loud before giving final answer

Example: "Go to car wash 50m away - walk or drive?"
- Goal: wash the CAR
- Requirement: car must be at car wash
- Walking = car stays home = CANNOT wash it
- Answer: DRIVE (even though 50m is short)

## Response Style
- Keep responses brief and to the point
- Simple questions: 1-2 sentences
- Complex questions: structured but not verbose
- Avoid unnecessary filler phrases like "Ada yang bisa saya bantu lagi?"

## Batch Operations
When processing multiple items (files, images, etc.):
1. Track all items to process
2. Process each one completely
3. Verify all items done before final response
4. Explicitly mention any failures

## Efficiency
Before searching or re-analyzing files:
1. Check if you already have the information (from previous tool results, memory, or description files)
2. Read existing documentation files first (e.g., photo-description.md)
3. Only use analyze_image if no description exists
4. Don't repeat tool calls you've already made

## Preventing Duplicates (IMPORTANT)
Before appending to USER.md or any file:
1. READ the file first to check existing content
2. DO NOT add information that already exists
3. Use edit_file with old_text/new_text to update existing entries
4. Never append the same preference/info twice

Be helpful, concise, and careful with file operations.
"""


async def execute_tool_with_timeout(tool, args: dict, timeout: int = TOOL_TIMEOUT):
    """Execute a tool with timeout protection."""
    try:
        return await asyncio.wait_for(tool.execute(**args), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Tool {tool.name} timed out after {timeout}s")
        from .tools.base import ToolResult
        return ToolResult(False, "", f"Tool execution timed out after {timeout} seconds")
    except Exception as e:
        logger.exception(f"Tool {tool.name} raised exception")
        from .tools.base import ToolResult
        return ToolResult(False, "", f"Tool error: {str(e)}")


async def stream_with_retry(prompt: str, images: list = None, max_retries: int = LLM_MAX_RETRIES):
    """Stream LLM response with retry logic for transient errors."""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            async for token, is_thinking, thinking_content in stream_generate(prompt, images=images):
                yield token, is_thinking, thinking_content
            return  # Success, exit
        except Exception as e:
            last_error = e
            error_name = type(e).__name__
            
            # Check if it's a retryable error
            retryable = any(x in error_name.lower() or x in str(e).lower() for x in [
                'timeout', 'connection', 'network', 'temporary', '503', '502', '429',
                'disconnect', 'remote', 'protocol', '500', 'server error',
            ])
            
            if retryable and attempt < max_retries - 1:
                delay = LLM_RETRY_DELAY * (2 ** attempt)
                logger.warning(f"LLM request failed ({error_name}), retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                logger.error(f"LLM request failed permanently: {e}")
                raise
    
    # Should not reach here, but just in case
    if last_error:
        raise last_error


@dataclass
class AgentResult:
    """Result from agent run."""
    response: str
    history: list[dict]
    file_data: Optional[dict] = None  # For single file (legacy, deprecated)
    files: Optional[list] = None  # For multiple file responses from skills


async def _run_agent_native_tools(
    user_message: str,
    history: list[dict],
    system_prompt: str,
    user_id: Optional[str] = None,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    debug_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    max_iterations: int = 10,
    images: list[str] = None,
    start_time: float = None,
) -> AgentResult:
    """
    Run agent loop with native tool calling (Anthropic Claude).
    
    Uses structured tool_use/tool_result content blocks.
    """
    start_time = start_time or time.time()
    logger.info(f"Running agent with native tools for user {user_id}")
    
    # Translate user message if translation is enabled
    processed_message = user_message
    if is_translation_enabled():
        try:
            processed_message = await translate_to_english(user_message)
            logger.debug(f"Translated user message: {user_message[:50]}... -> {processed_message[:50]}...")
        except Exception as e:
            logger.warning(f"User message translation failed, using original: {e}")
    
    # Get available tools and convert to Anthropic format
    available_tools = list_tools(user_id)
    anthropic_tools = convert_tools_to_anthropic_format(available_tools)
    logger.debug(f"Converted {len(anthropic_tools)} tools to Anthropic format")
    
    # Build initial messages from history (limit to prevent context overflow)
    messages: List[Dict[str, Any]] = []
    history_limit = get_history_limit()
    for msg in history[-history_limit:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })
    
    # Add current user message (with images if provided)
    # Use processed_message (translated if enabled) for LLM
    # Skip images if vision is disabled in config
    if images and not is_vision_enabled():
        logger.info("Vision disabled in config, skipping image data for native tools")
        images = None
    
    if images:
        content = []
        for img_base64 in images:
            # Detect MIME type
            if img_base64.startswith("/9j/"):
                mime = "image/jpeg"
            elif img_base64.startswith("iVBOR"):
                mime = "image/png"
            else:
                mime = "image/jpeg"
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": img_base64}
            })
        content.append({"type": "text", "text": processed_message})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": processed_message})
    
    iterations = 0
    accumulated_text = ""
    thinking_buffer = ""
    pending_files = []  # Track file data from skills (supports multiple files)
    last_tool_result = None
    all_tool_interactions = []  # Collect all tool calls + results for conversation log
    
    while iterations < max_iterations:
        iterations += 1
        
        # Check total time limit
        elapsed = time.time() - start_time
        if elapsed > TOTAL_TIME_LIMIT:
            logger.warning(f"Agent exceeded time limit ({TOTAL_TIME_LIMIT}s), aborting")
            if accumulated_text:
                accumulated_text += "\n\n[Response truncated: time limit exceeded]"
            else:
                accumulated_text = "I'm sorry, the request took too long to process."
            break
        
        logger.debug(f"Native tools iteration {iterations}/{max_iterations}")
        
        # Collect tool calls and text from this turn
        turn_text = ""
        turn_tool_calls: List[Any] = []  # List of ToolCall
        last_update = 0
        
        try:
            async for event in stream_with_tools(
                messages=messages,
                system=system_prompt,
                tools=anthropic_tools,
            ):
                event_type = event.get("type")
                
                if event_type == "text":
                    text = event.get("text", "")
                    turn_text += text
                    
                    # Status update
                    current_time = asyncio.get_event_loop().time()
                    if status_callback and (current_time - last_update > 1.0):
                        try:
                            if turn_text:
                                # Strip thinking tags before streaming to user
                                clean_text = strip_thinking_tags(turn_text)
                                if clean_text:
                                    await status_callback(f"{clean_text[:1500]}▌")
                        except Exception as e:
                            logger.warning(f"Status callback failed: {e}")
                        last_update = current_time
                
                elif event_type == "thinking":
                    thinking_buffer = event.get("thinking", "")
                    
                    # Status update for thinking
                    current_time = asyncio.get_event_loop().time()
                    if status_callback and (current_time - last_update > 1.0):
                        try:
                            preview = thinking_buffer[-400:] if len(thinking_buffer) > 400 else thinking_buffer
                            await status_callback(f"🧠 _Thinking..._\n```\n{preview}▌\n```")
                        except Exception as e:
                            logger.warning(f"Status callback failed: {e}")
                        last_update = current_time
                
                elif event_type == "tool_use":
                    tool_call = event.get("tool_call")
                    if tool_call:
                        turn_tool_calls.append(tool_call)
                        logger.info(f"Tool call: {tool_call.name} with args: {list(tool_call.arguments.keys())}")
                        
                        if status_callback:
                            try:
                                await status_callback(f"🔧 Calling: `{tool_call.name}`\n```json\n{json.dumps(tool_call.arguments, indent=2)}\n```")
                            except Exception as e:
                                logger.warning(f"Status callback failed: {e}")
                
                elif event_type == "done":
                    stop_reason = event.get("stop_reason", "")
                    logger.debug(f"Stream done, stop_reason: {stop_reason}")
                    break
        
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            error_msg = sanitize_error(e)
            if accumulated_text:
                accumulated_text += f"\n\n❌ {error_msg}"
            else:
                accumulated_text = f"❌ {error_msg}"
            break
        
        # Accumulate text
        accumulated_text += turn_text
        
        # If no tool calls, we're done
        if not turn_tool_calls:
            logger.debug("No tool calls, finishing agent loop")
            break
        
        # Build assistant message with text + tool_use blocks
        assistant_content = []
        if turn_text:
            assistant_content.append({"type": "text", "text": turn_text})
        
        for tc in turn_tool_calls:
            assistant_content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.arguments,
            })
        
        messages.append({"role": "assistant", "content": assistant_content})
        
        # Execute tools and collect results
        tool_results: List[LLMToolResult] = []
        
        for tc in turn_tool_calls:
            tool = get_tool(tc.name, user_id=user_id)
            
            if tool:
                tool_start = time.time()
                result = await execute_tool_with_timeout(tool, tc.arguments)
                tool_duration_ms = int((time.time() - tool_start) * 1000)
                
                # Check for file data
                if result.file_data:
                    pending_files.append(result.file_data)
                    result_text = f"File ready: {result.file_data.get('filename', 'file')}"
                    logger.info(f"Tool {tc.name} returned file: {result.file_data.get('filename')}")
                elif result.success:
                    result_text = result.output[:4000]  # Anthropic allows larger results
                    logger.info(f"Tool {tc.name} succeeded, output length: {len(result.output)}")
                else:
                    result_text = f"Error: {result.error}"
                    logger.warning(f"Tool {tc.name} failed: {result.error}")
                
                last_tool_result = {"tool": tc.name, "result": result_text, "success": result.success}
                
                # Collect tool interaction for conversation log
                interaction = {
                    "tool": tc.name,
                    "args": tc.arguments,
                    "result": result_text[:2000],  # Cap result size in log
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "duration_ms": tool_duration_ms,
                }
                all_tool_interactions.append(interaction)
                
                # Fire debug callback on failure
                if not result.success and DEBUG_TOOL_ERRORS and debug_callback:
                    try:
                        await debug_callback(user_id, interaction)
                    except Exception as e:
                        logger.warning(f"Debug callback failed: {e}")
                
                # Smart loop detection (check after we have result)
                should_allow, loop_warning = loop_detector.check(tool_name, tool_args, result_text)
                if loop_warning:
                    logger.info(f"Loop detector ({loop_detector.loop_score}): {loop_warning[:100]}")
                if not should_allow:
                    # Block and inject intervention message
                    full_prompt += f"\n\n{loop_warning}\n"
                    logger.warning("Loop detector blocked tool call")
                    break  # Exit tool loop, force LLM to try different approach
                
                tool_results.append(LLMToolResult(
                    tool_use_id=tc.id,
                    content=result_text,
                    is_error=not result.success,
                ))
            else:
                logger.warning(f"Unknown tool: {tc.name}")
                interaction = {
                    "tool": tc.name,
                    "args": tc.arguments if hasattr(tc, 'arguments') else {},
                    "result": f"Unknown tool: {tc.name}",
                    "success": False,
                    "exit_code": None,
                    "duration_ms": 0,
                }
                all_tool_interactions.append(interaction)
                
                if DEBUG_TOOL_ERRORS and debug_callback:
                    try:
                        await debug_callback(user_id, interaction)
                    except Exception as e:
                        logger.warning(f"Debug callback failed: {e}")
                
                tool_results.append(LLMToolResult(
                    tool_use_id=tc.id,
                    content=f"Unknown tool: {tc.name}",
                    is_error=True,
                ))
        
        # Add tool results as user message
        messages.append(build_tool_result_message(tool_results))
    
    # Finalize response
    raw_response = accumulated_text.strip()  # Keep original with thinking for debug
    
    # Extract thinking content before stripping (for conversation log)
    thinking_content = None
    thought_match = re.search(r'<(?:thought|thinking|think)>([\s\S]*?)</(?:thought|thinking|think)>', raw_response, re.IGNORECASE)
    if thought_match:
        thinking_content = thought_match.group(1).strip()
    elif thinking_buffer:  # Use buffered thinking if available
        thinking_content = thinking_buffer.strip()
    
    # Strip thinking tags for user-facing response
    final_response = strip_thinking_tags(raw_response)
    
    # Fallback if empty
    if not final_response and last_tool_result:
        logger.info("Response was empty, falling back to last tool result")
        if last_tool_result["success"]:
            final_response = f"Result:\n```\n{last_tool_result['result']}\n```"
        else:
            final_response = f"Error: {last_tool_result['result']}"
    
    # Translate if enabled
    if is_translation_enabled():
        try:
            final_response = await translate_to_indonesian(final_response)
        except Exception as e:
            logger.warning(f"Response translation failed: {e}")
    
    # Update history
    new_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_response},
    ]
    
    if len(new_history) > 20:
        new_history = new_history[-20:]
    
    # Save conversation
    if user_id:
        try:
            from .conversation import append_message, is_enabled
            if is_enabled():
                append_message(user_id, "user", user_message)
                append_message(
                    user_id, "assistant", final_response,
                    thinking=thinking_content,
                    tool_calls=all_tool_interactions if all_tool_interactions else None,
                )
        except Exception as e:
            logger.warning(f"Failed to save conversation: {e}")
    
    elapsed = time.time() - start_time
    logger.info(f"Agent (native tools) completed in {elapsed:.2f}s, iterations: {iterations}")
    
    return AgentResult(
        response=final_response,
        history=new_history,
        files=pending_files if pending_files else None,
    )


async def run_agent(
    user_message: str,
    history: list[dict],
    user_id: Optional[str] = None,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    debug_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    max_iterations: int = 10,
    images: list[str] = None,  # List of base64 encoded images
) -> AgentResult:
    """
    Run the agent loop.
    
    Args:
        user_message: The user's input
        history: Conversation history
        user_id: Prefixed user ID (e.g., "tg_123456", "wa_628xxx")
        status_callback: Async callback for status updates
        debug_callback: Async callback for debug tool error alerts (user_id, tool_info)
        max_iterations: Maximum tool call iterations
        images: List of base64 encoded images for multimodal input
    
    Returns:
        (final_response, updated_history)
    """
    start_time = time.time()
    logger.info(f"Agent run started for user {user_id}, message length: {len(user_message)}")
    
    # First-user-as-admin: claim ownership on first message
    if user_id:
        try:
            from .access import claim_ownership
            if claim_ownership(user_id):
                logger.info(f"First user {user_id} claimed ownership (admin)")
        except Exception as e:
            logger.warning(f"Failed to claim ownership: {e}")
    
    # Load persisted conversation history if none provided
    if not history and user_id:
        history = load_conversation_history(user_id)
        if history:
            logger.info(f"Loaded {len(history)} persisted messages for {user_id}")
    
    # Load system prompt (with onboarding if bot unconfigured)
    # Pass user_id to filter tools by access level
    system_prompt = load_system_prompt(user_id)
    
    # Load user-specific context if user_id provided
    if user_id:
        ensure_user_dir(user_id)
        user_context = load_full_context(user_id)
        
        # Add runtime context with user_id and current datetime
        from datetime import datetime
        import pytz
        
        # Get current time in WIB (UTC+7)
        try:
            tz = pytz.timezone('Asia/Jakarta')
            now = datetime.now(tz)
        except:
            now = datetime.now()
        
        datetime_str = now.strftime("%Y-%m-%d %H:%M:%S %Z")
        day_name = now.strftime("%A")
        
        # Check admin/owner status
        from .access import is_admin, is_owner
        user_is_owner = is_owner(user_id)
        user_is_admin = is_admin(user_id)
        
        admin_status = ""
        role_emphasis = ""
        if user_is_owner:
            admin_status = "- User role: **OWNER** (full admin privileges, can access all tools)"
            role_emphasis = "\n⚠️ **THIS USER IS THE OWNER** - Treat them with full trust and access.\n"
        elif user_is_admin:
            admin_status = "- User role: **Admin** (full privileges)"
            role_emphasis = "\n⚠️ **THIS USER IS AN ADMIN** - Full access granted.\n"
        else:
            admin_status = "- User role: Regular user (limited access)"
        
        runtime_context = f"""## Runtime Info
{role_emphasis}
- Current datetime: `{datetime_str}` ({day_name})
- Current user ID: `{user_id}`
{admin_status}
"""
        
        if user_context:
            system_prompt += f"\n\n# Context\n\n{runtime_context}\n{user_context}"
        else:
            system_prompt += f"\n\n# Context\n\n{runtime_context}"
    
    # Check if provider supports native tools
    if supports_native_tools():
        logger.info("Using native tool calling (Anthropic)")
        return await _run_agent_native_tools(
            user_message=user_message,
            history=history,
            system_prompt=system_prompt,
            user_id=user_id,
            status_callback=status_callback,
            debug_callback=debug_callback,
            max_iterations=max_iterations,
            images=images,
            start_time=start_time,
        )
    
    # Fall through to XML-based tool calling for Ollama/OpenRouter
    logger.debug("Using XML-based tool calling")
    
    # Translate user message if translation is enabled
    processed_message = user_message
    if is_translation_enabled():
        try:
            processed_message = await translate_to_english(user_message)
        except Exception as e:
            logger.warning(f"Translation failed, using original message: {e}")
    
    # Build conversation (limit to prevent context overflow)
    history_limit = get_history_limit()
    conversation = ""
    for msg in history[-history_limit:]:
        role = msg["role"]
        content = msg["content"]
        conversation += f"{role}\n{content}\n\n"
    
    conversation += f"user\n{processed_message}\n\nassistant\n"
    
    full_prompt = f"{system_prompt}\n\n{conversation}"
    
    iterations = 0
    accumulated_response = ""
    thinking_shown = False
    last_tool_result = None  # Track last tool result for fallback
    pending_files = []  # Track file data from skills (supports multiple files)
    pending_images = []  # Track images from tool results (analyze_image)
    json_parse_failures = 0  # Track consecutive JSON parse failures
    MAX_JSON_FAILURES = 3  # Stop after this many consecutive failures
    all_tool_interactions = []  # Collect all tool calls + results for conversation log
    executed_tool_calls = set()  # Track executed calls to prevent duplicates
    loop_detector = LoopDetector()  # Smart loop detection
    file_moves = {}  # Track file movements: old_path -> new_path
    
    while iterations < max_iterations:
        iterations += 1
        
        # Check total time limit
        elapsed = time.time() - start_time
        if elapsed > TOTAL_TIME_LIMIT:
            logger.warning(f"Agent exceeded time limit ({TOTAL_TIME_LIMIT}s), aborting")
            if accumulated_response:
                accumulated_response += "\n\n[Response truncated: time limit exceeded]"
            else:
                accumulated_response = "I'm sorry, the request took too long to process. Please try a simpler query."
            break
        
        logger.debug(f"Agent iteration {iterations}/{max_iterations}")
        
        # Stream LLM response with retry
        current_response = ""
        current_thinking = ""
        last_update = 0
        
        try:
            # Pass images: user images on first iteration + any pending images from tools
            current_images = []
            if iterations == 1 and images:
                current_images.extend(images)
            if pending_images:
                current_images.extend(pending_images)
                pending_images = []  # Clear after use
            
            async for token, is_thinking, thinking_content in stream_with_retry(full_prompt, images=current_images if current_images else None):
                current_response += token
                
                if thinking_content:
                    current_thinking = thinking_content
                
                # Status updates
                current_time = asyncio.get_event_loop().time()
                if status_callback and (current_time - last_update > 1.0):
                    try:
                        if is_thinking and thinking_content:
                            preview = thinking_content[-400:] if len(thinking_content) > 400 else thinking_content
                            await status_callback(f"🧠 _Thinking..._\n```\n{preview}▌\n```")
                            thinking_shown = True
                        elif not is_thinking and current_response:
                            # Show response progress (strip thinking tags before showing)
                            clean = current_response.split("</think>")[-1].strip() if "</think>" in current_response else current_response.strip()
                            clean = strip_thinking_tags(clean)
                            if clean:
                                # Hide in-progress tool call content from user (unless debug mode)
                                if not SHOW_TOOL_CALLS and has_pending_tool_call(clean):
                                    # Tool call being generated — show only text before it
                                    for tag in ['<tool_call>', '<toolcall>', '<Tool_Call>']:
                                        tag_lower_idx = clean.lower().find(tag.lower())
                                        if tag_lower_idx != -1:
                                            clean = clean[:tag_lower_idx].strip()
                                            break
                                    if clean:
                                        await status_callback(f"{clean}\n\n🔧 _Preparing tool call..._")
                                    else:
                                        await status_callback("🔧 _Preparing tool call..._")
                                else:
                                    await status_callback(f"{clean[:1500]}▌")
                    except Exception as e:
                        logger.warning(f"Status callback failed: {e}")
                    last_update = current_time
                    
        except Exception as e:
            logger.error(f"LLM streaming failed after retries: {e}")
            error_msg = sanitize_error(e)
            if accumulated_response:
                accumulated_response += f"\n\n❌ {error_msg}"
            else:
                accumulated_response = f"❌ {error_msg}"
            break
        
        # Extract response after thinking
        if "</think>" in current_response:
            response_part = current_response.split("</think>")[-1].strip()
        else:
            response_part = current_response.strip()
        
        # Check for tool calls using robust parser (bracket-counting, not regex)
        search_text = current_response  # Search full response to catch all formats
        
        parsed_tool = extract_tool_call(search_text)
        
        if parsed_tool:
            tool_name = parsed_tool["tool"]
            tool_args = parsed_tool["args"]
            
            # Validate: tools that typically need args should have non-empty args
            TOOLS_REQUIRING_ARGS = {
                "run_bash": ["script"],
                "run_python": ["script"],
                "exec": ["command"],
                "read_file": ["path"],
                "write_file": ["path", "content"],
                "edit_file": ["path"],
                "replace_in_file": ["path", "start_line", "end_line", "new_content"],
                "memory_update": ["content"],
                "memory_log": ["content"],
                "user_update": ["data"],
            }
            
            required_args = TOOLS_REQUIRING_ARGS.get(tool_name, [])
            missing_args = [arg for arg in required_args if arg not in tool_args or not tool_args[arg]]
            
            if missing_args:
                logger.warning(f"Tool {tool_name} missing required args: {missing_args}, skipping execution")
                json_parse_failures += 1
                
                if json_parse_failures >= MAX_JSON_FAILURES:
                    logger.error(f"Too many parse failures ({MAX_JSON_FAILURES}), aborting agent loop")
                    accumulated_response = (
                        "Maaf, saya mengalami kesulitan teknis dalam memformat perintah. "
                        "Silakan coba lagi dengan permintaan yang lebih sederhana, "
                        "atau pecah menjadi langkah-langkah kecil."
                    )
                    break
                
                full_prompt += f"{response_part}\n\n<tool_result>\nError: Tool '{tool_name}' requires arguments: {', '.join(required_args)}. Please provide complete arguments.\n</tool_result>\n\nassistant\n"
                continue
            
            logger.info(f"Executing tool: {tool_name} with args: {list(tool_args.keys())}")
            
            # Check for duplicate tool call (same tool + same args)
            try:
                call_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            except:
                call_key = f"{tool_name}:{str(tool_args)}"
            
            if call_key in executed_tool_calls:
                logger.info(f"Skipping duplicate tool call: {tool_name}")
                full_prompt += f"{response_part}\n\n<tool_result>\n(Skipped: duplicate call - already executed)\n</tool_result>\n\nassistant\n"
                continue
            executed_tool_calls.add(call_key)
            
            # Smart loop detection (multi-factor: args, result, gradual intervention)
            # Check AFTER execution when we have result
            
            # Reset failure counter on successful parse
            json_parse_failures = 0
            
            if status_callback:
                try:
                    # Truncate large args for display (e.g., file content)
                    display_args = {}
                    for k, v in tool_args.items():
                        if isinstance(v, str) and len(v) > 200:
                            display_args[k] = v[:200] + f"... ({len(v)} chars)"
                        else:
                            display_args[k] = v
                    await status_callback(f"🔧 Calling: `{tool_name}`\n```json\n{json.dumps(display_args, indent=2)}\n```")
                except Exception as e:
                    logger.warning(f"Status callback failed: {e}")
            
            tool = get_tool(tool_name, user_id=user_id)
            if tool:
                tool_start = time.time()
                result = await execute_tool_with_timeout(tool, tool_args)
                tool_duration_ms = int((time.time() - tool_start) * 1000)
                
                # Check for file data (from skills) or image data (from analyze_image)
                if result.file_data:
                    if result.file_data.get("__image__"):
                        # Image to be included in next LLM call
                        pending_images.append(result.file_data.get("data"))
                        result_text = result.output or f"Image loaded: {result.file_data.get('filename', 'image')}"
                        logger.info(f"Tool {tool_name} returned image for analysis: {result.file_data.get('filename')}")
                    else:
                        # Regular file to be sent to user
                        pending_files.append(result.file_data)
                        result_text = f"File ready: {result.file_data.get('filename', 'file')}"
                        logger.info(f"Tool {tool_name} returned file: {result.file_data.get('filename')}")
                elif result.success:
                    result_text = truncate_tool_output(result.output, tool_name)
                    logger.info(f"Tool {tool_name} succeeded, output length: {len(result.output)}, truncated to: {len(result_text)}")
                else:
                    result_text = f"Error: {result.error}"
                    logger.warning(f"Tool {tool_name} failed: {result.error}")
                
                # Track last tool result for fallback
                last_tool_result = {"tool": tool_name, "result": result_text, "success": result.success}
                
                # Collect tool interaction for conversation log
                interaction = {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result_text[:2000],
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "duration_ms": tool_duration_ms,
                }
                all_tool_interactions.append(interaction)
                
                # Track file movements from run_bash mv commands
                if tool_name == "run_bash" and result.success:
                    script = tool_args.get("script", "")
                    # Parse mv commands: mv source dest
                    import shlex
                    for line in script.split("\n"):
                        line = line.strip()
                        if line.startswith("mv "):
                            try:
                                parts = shlex.split(line)
                                if len(parts) >= 3:
                                    src, dst = parts[1], parts[2]
                                    # If dst is a directory, append filename
                                    if dst.endswith("/"):
                                        dst = dst + os.path.basename(src)
                                    file_moves[src] = dst
                                    logger.info(f"Tracked file move: {src} -> {dst}")
                            except:
                                pass
                
                # Fire debug callback on failure
                if not result.success and DEBUG_TOOL_ERRORS and debug_callback:
                    try:
                        await debug_callback(user_id, interaction)
                    except Exception as e:
                        logger.warning(f"Debug callback failed: {e}")
                
                # Add file move context if any files were moved
                file_move_context = ""
                if file_moves:
                    moves_str = "\n".join([f"  - {src} → {dst}" for src, dst in file_moves.items()])
                    file_move_context = f"\n[FILE MOVES - use new paths:\n{moves_str}]\n"
                
                # Add to prompt for next iteration (LLM will interpret this)
                full_prompt += f"{response_part}\n\n<tool_result>\n{result_text}{file_move_context}\n</tool_result>\n\nassistant\n"
                
            else:
                error_text = f"Unknown tool: {tool_name}"
                logger.warning(error_text)
                
                interaction = {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": error_text,
                    "success": False,
                    "exit_code": None,
                    "duration_ms": 0,
                }
                all_tool_interactions.append(interaction)
                
                if DEBUG_TOOL_ERRORS and debug_callback:
                    try:
                        await debug_callback(user_id, interaction)
                    except Exception as e:
                        logger.warning(f"Debug callback failed: {e}")
                
                full_prompt += f"{response_part}\n\n<tool_result>\n{error_text}\n</tool_result>\n\nassistant\n"
        else:
            # No tool call, this is the final response
            logger.debug("No tool call found, finishing agent loop")
            accumulated_response = response_part  # Use final response, don't accumulate previous iterations
            break
    
    # Translate response back to Indonesian if translation is enabled
    raw_response_text = accumulated_response
    
    # Extract thinking content before stripping (for conversation log)
    # Support multiple tag formats: <thought>, <thinking>, <think>
    thinking_content_text = None
    thought_match = re.search(r'<(?:thought|thinking|think)>([\s\S]*?)</(?:thought|thinking|think)>', raw_response_text, re.IGNORECASE)
    if thought_match:
        thinking_content_text = thought_match.group(1).strip()
        logger.debug(f"Extracted thinking from tags: {len(thinking_content_text)} chars")
    elif current_thinking:  # Use accumulated thinking if available
        thinking_content_text = current_thinking.strip()
        logger.debug(f"Using accumulated thinking: {len(thinking_content_text)} chars")
    
    # DEBUG: Log if thinking tags present but not captured
    if not thinking_content_text and ('<think' in raw_response_text.lower() or '<thought' in raw_response_text.lower()):
        logger.warning(f"Thinking tags detected but not captured. raw_response sample: {raw_response_text[:300]}")
    
    # Strip all thinking tags and tool call leaks
    final_response = strip_thinking_tags(raw_response_text)
    
    # Additional cleanup for tool-related tags
    final_response = re.sub(r'</?tool_?result>', '', final_response, flags=re.IGNORECASE)
    final_response = final_response.strip()
    
    # Forced continuation: if response is empty after tool execution, force LLM to interpret
    if not final_response and last_tool_result:
        logger.info("Response was empty after tool execution, forcing continuation...")
        
        # Build continuation prompt with explicit instruction
        continuation_instruction = (
            "\n\n[System: You just executed a tool and received the result above. "
            "Now you MUST interpret this result and respond to the user in plain language. "
            "Summarize what the tool found or did. Do NOT call any more tools. "
            "Do NOT output empty response. Respond naturally as if explaining to the user.]"
        )
        continuation_prompt = full_prompt + continuation_instruction + "\n\nassistant\n"
        
        try:
            # Run one more LLM call to get interpretation
            continuation_response = ""
            async for token, is_thinking, _ in stream_with_retry(continuation_prompt):
                if not is_thinking:
                    continuation_response += token
            
            # Clean up the continuation response
            continuation_response = strip_thinking_tags(continuation_response)
            continuation_response = re.sub(r'</?tool_?result>', '', continuation_response, flags=re.IGNORECASE)
            continuation_response = continuation_response.strip()
            
            if continuation_response:
                logger.info(f"Forced continuation succeeded, got {len(continuation_response)} chars")
                final_response = continuation_response
            else:
                # Still empty, fall back to raw result
                logger.warning("Forced continuation still empty, falling back to raw result")
                if last_tool_result["success"]:
                    final_response = f"Result:\n```\n{last_tool_result['result']}\n```"
                else:
                    final_response = f"Error: {last_tool_result['result']}"
                    
        except Exception as e:
            logger.error(f"Forced continuation failed: {e}")
            # Fall back to raw result
            if last_tool_result["success"]:
                final_response = f"Result:\n```\n{last_tool_result['result']}\n```"
            else:
                final_response = f"Error: {last_tool_result['result']}"
    
    # Ultimate fallback: if still empty but we have tool interactions, summarize them
    if not final_response and all_tool_interactions:
        logger.warning(f"Response still empty, generating summary from {len(all_tool_interactions)} tool interactions")
        successful = [t for t in all_tool_interactions if t.get("success")]
        failed = [t for t in all_tool_interactions if not t.get("success")]
        
        summary_parts = []
        if successful:
            summary_parts.append(f"✅ Berhasil menjalankan {len(successful)} operasi:")
            for t in successful[:5]:  # Limit to 5
                summary_parts.append(f"  - {t['tool']}")
        if failed:
            summary_parts.append(f"❌ {len(failed)} operasi gagal")
        
        if summary_parts:
            final_response = "\n".join(summary_parts)
        else:
            final_response = "Operasi selesai."
    
    if is_translation_enabled():
        try:
            final_response = await translate_to_indonesian(final_response)
        except Exception as e:
            logger.warning(f"Response translation failed: {e}")
    
    # Update history (store original messages, not translated)
    new_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_response},
    ]
    
    # Keep history bounded
    if len(new_history) > 20:
        new_history = new_history[-20:]
    
    # Save conversation to JSONL if enabled
    if user_id:
        try:
            from .conversation import append_message, is_enabled
            if is_enabled():
                append_message(user_id, "user", user_message)
                append_message(
                    user_id, "assistant", final_response,
                    thinking=thinking_content_text,
                    tool_calls=all_tool_interactions if all_tool_interactions else None,
                )
        except Exception as e:
            logger.warning(f"Failed to save conversation: {e}")
    
    elapsed = time.time() - start_time
    logger.info(f"Agent run completed in {elapsed:.2f}s, iterations: {iterations}, response length: {len(final_response)}")
    
    return AgentResult(
        response=final_response,
        history=new_history,
        files=pending_files if pending_files else None,
    )
