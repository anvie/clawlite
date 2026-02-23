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
)
from .tools import get_tool, format_tools_for_prompt, list_tools, SKILL_TOOLS
from .translation import translate_to_english, translate_to_indonesian, TRANSLATION_ENABLED
from .context import load_full_context, ensure_user_dir, is_bot_unconfigured, load_conversation_history
from .config import get as config_get
from .errors import sanitize_error, format_user_error

logger = logging.getLogger("clawlite.agent")

# Load system prompt
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

# Configuration (from config/clawlite.yaml with defaults)
TOOL_TIMEOUT = config_get('agent.tool_timeout', 30)
LLM_MAX_RETRIES = config_get('agent.retry_attempts', 3)
LLM_RETRY_DELAY = 2  # base delay for exponential backoff
TOTAL_TIME_LIMIT = config_get('agent.total_timeout', 300)


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
2. You cannot access files outside /workspace
3. Only allowed shell commands can be executed
4. Think through problems step by step
5. After completing a task, summarize what you did

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
                'timeout', 'connection', 'network', 'temporary', '503', '502', '429'
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
    file_data: Optional[dict] = None  # For file responses from skills


async def _run_agent_native_tools(
    user_message: str,
    history: list[dict],
    system_prompt: str,
    user_id: Optional[str] = None,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None,
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
    
    # Get available tools and convert to Anthropic format
    available_tools = list_tools(user_id)
    anthropic_tools = convert_tools_to_anthropic_format(available_tools)
    logger.debug(f"Converted {len(anthropic_tools)} tools to Anthropic format")
    
    # Build initial messages from history
    messages: List[Dict[str, Any]] = []
    for msg in history[-10:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })
    
    # Add current user message (with images if provided)
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
        content.append({"type": "text", "text": user_message})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    
    iterations = 0
    accumulated_text = ""
    thinking_buffer = ""
    pending_file_data = None
    last_tool_result = None
    
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
                                await status_callback(f"{turn_text[:1500]}▌")
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
                result = await execute_tool_with_timeout(tool, tc.arguments)
                
                # Check for file data
                if result.file_data:
                    pending_file_data = result.file_data
                    result_text = f"File ready: {result.file_data.get('filename', 'file')}"
                    logger.info(f"Tool {tc.name} returned file: {result.file_data.get('filename')}")
                elif result.success:
                    result_text = result.output[:4000]  # Anthropic allows larger results
                    logger.info(f"Tool {tc.name} succeeded, output length: {len(result.output)}")
                else:
                    result_text = f"Error: {result.error}"
                    logger.warning(f"Tool {tc.name} failed: {result.error}")
                
                last_tool_result = {"tool": tc.name, "result": result_text, "success": result.success}
                
                tool_results.append(LLMToolResult(
                    tool_use_id=tc.id,
                    content=result_text,
                    is_error=not result.success,
                ))
            else:
                logger.warning(f"Unknown tool: {tc.name}")
                tool_results.append(LLMToolResult(
                    tool_use_id=tc.id,
                    content=f"Unknown tool: {tc.name}",
                    is_error=True,
                ))
        
        # Add tool results as user message
        messages.append(build_tool_result_message(tool_results))
    
    # Finalize response
    final_response = accumulated_text.strip()
    
    # Fallback if empty
    if not final_response and last_tool_result:
        logger.info("Response was empty, falling back to last tool result")
        if last_tool_result["success"]:
            final_response = f"Result:\n```\n{last_tool_result['result']}\n```"
        else:
            final_response = f"Error: {last_tool_result['result']}"
    
    # Translate if enabled
    if TRANSLATION_ENABLED:
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
                append_message(user_id, "assistant", final_response)
        except Exception as e:
            logger.warning(f"Failed to save conversation: {e}")
    
    elapsed = time.time() - start_time
    logger.info(f"Agent (native tools) completed in {elapsed:.2f}s, iterations: {iterations}")
    
    return AgentResult(
        response=final_response,
        history=new_history,
        file_data=pending_file_data,
    )


async def run_agent(
    user_message: str,
    history: list[dict],
    user_id: Optional[str] = None,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None,
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
        if user_is_owner:
            admin_status = "- User role: **Owner** (full admin privileges)"
        elif user_is_admin:
            admin_status = "- User role: **Admin** (full privileges)"
        else:
            admin_status = "- User role: Regular user"
        
        runtime_context = f"""## Runtime Info
- Current datetime: `{datetime_str}` ({day_name})
- Current user ID: `{user_id}`
{admin_status}
- Use this ID for `clawlite-send` commands in cron jobs
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
            max_iterations=max_iterations,
            images=images,
            start_time=start_time,
        )
    
    # Fall through to XML-based tool calling for Ollama/OpenRouter
    logger.debug("Using XML-based tool calling")
    
    # Translate user message if translation is enabled
    processed_message = user_message
    if TRANSLATION_ENABLED:
        try:
            processed_message = await translate_to_english(user_message)
        except Exception as e:
            logger.warning(f"Translation failed, using original message: {e}")
    
    # Build conversation
    conversation = ""
    for msg in history[-10:]:
        role = msg["role"]
        content = msg["content"]
        conversation += f"{role}\n{content}\n\n"
    
    conversation += f"user\n{processed_message}\n\nassistant\n"
    
    full_prompt = f"{system_prompt}\n\n{conversation}"
    
    iterations = 0
    accumulated_response = ""
    thinking_shown = False
    last_tool_result = None  # Track last tool result for fallback
    pending_file_data = None  # Track file data from skills
    
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
            # Only pass images on first iteration
            current_images = images if iterations == 1 else None
            
            async for token, is_thinking, thinking_content in stream_with_retry(full_prompt, images=current_images):
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
                            # Show response progress
                            clean = current_response.split("</think>")[-1].strip() if "</think>" in current_response else current_response.strip()
                            if clean:
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
        
        accumulated_response += response_part
        
        # Check for tool calls (support multiple formats)
        # Format 1: <tool_call>{"tool": "x", "args": {}}</tool_call>
        # Format 2: <toolcall>{"name": "x", "arguments": {}}</toolcall>
        # Format 3: <tool_call>{"name": "x", "arguments": {}}</tool_call>
        tool_call_match = re.search(
            r'<tool_?call>\s*(\{.*?\})\s*</tool_?call>',
            response_part,
            re.DOTALL | re.IGNORECASE
        )
        
        if tool_call_match:
            try:
                tool_json = tool_call_match.group(1)
                tool_data = json.loads(tool_json)
                
                # Support multiple field names
                tool_name = tool_data.get("tool") or tool_data.get("name", "")
                tool_args = tool_data.get("args") or tool_data.get("arguments", {})
                
                logger.info(f"Executing tool: {tool_name} with args: {list(tool_args.keys())}")
                
                if status_callback:
                    try:
                        await status_callback(f"🔧 Calling: `{tool_name}`\n```json\n{json.dumps(tool_args, indent=2)}\n```")
                    except Exception as e:
                        logger.warning(f"Status callback failed: {e}")
                
                tool = get_tool(tool_name, user_id=user_id)
                if tool:
                    result = await execute_tool_with_timeout(tool, tool_args)
                    
                    # Check for file data (from skills)
                    if result.file_data:
                        pending_file_data = result.file_data
                        result_text = f"File ready: {result.file_data.get('filename', 'file')}"
                        logger.info(f"Tool {tool_name} returned file: {result.file_data.get('filename')}")
                    elif result.success:
                        result_text = f"{result.output[:2000]}"
                        logger.info(f"Tool {tool_name} succeeded, output length: {len(result.output)}")
                    else:
                        result_text = f"Error: {result.error}"
                        logger.warning(f"Tool {tool_name} failed: {result.error}")
                    
                    # Track last tool result for fallback
                    last_tool_result = {"tool": tool_name, "result": result_text, "success": result.success}
                    
                    # Add to prompt for next iteration (LLM will interpret this)
                    full_prompt += f"{response_part}\n\n<tool_result>\n{result_text}\n</tool_result>\n\nassistant\n"
                    
                else:
                    error_text = f"Unknown tool: {tool_name}"
                    logger.warning(error_text)
                    full_prompt += f"{response_part}\n\n<tool_result>\n{error_text}\n</tool_result>\n\nassistant\n"
                
            except json.JSONDecodeError as e:
                error_text = f"Invalid tool call JSON: {e}"
                logger.warning(f"Failed to parse tool call: {tool_json[:200]}")
                full_prompt += f"{response_part}\n\n<tool_result>\n{error_text}\n</tool_result>\n\nassistant\n"
        else:
            # No tool call, we're done
            logger.debug("No tool call found, finishing agent loop")
            break
    
    # Translate response back to Indonesian if translation is enabled
    final_response = accumulated_response
    
    # Always strip tool call tags from final response
    final_response = re.sub(r'<tool_?call>.*?</tool_?call>', '', final_response, flags=re.DOTALL | re.IGNORECASE).strip()
    
    # Fallback: if response is empty (was only tool calls), include last tool result
    if not final_response and last_tool_result:
        logger.info("Response was empty, falling back to last tool result")
        if last_tool_result["success"]:
            final_response = f"Result:\n```\n{last_tool_result['result']}\n```"
        else:
            final_response = f"Error: {last_tool_result['result']}"
    
    if TRANSLATION_ENABLED:
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
                append_message(user_id, "assistant", final_response)
        except Exception as e:
            logger.warning(f"Failed to save conversation: {e}")
    
    elapsed = time.time() - start_time
    logger.info(f"Agent run completed in {elapsed:.2f}s, iterations: {iterations}, response length: {len(final_response)}")
    
    return AgentResult(
        response=final_response,
        history=new_history,
        file_data=pending_file_data,
    )
