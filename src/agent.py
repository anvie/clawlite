"""Agent loop with tool calling."""

import json
import re
import os
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable

from .llm import stream_generate
from .tools import get_tool, format_tools_for_prompt, SKILL_TOOLS
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


def load_system_prompt() -> str:
    """Load system prompt from file, with onboarding if bot unconfigured."""
    prompt_file = os.path.join(PROMPTS_DIR, "system.md")
    try:
        with open(prompt_file, "r") as f:
            prompt = f.read()
    except FileNotFoundError:
        prompt = get_default_system_prompt()
    
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


def get_default_system_prompt() -> str:
    """Default system prompt if file not found."""
    skill_section = format_skill_prompts()
    return f"""You are ClawLite, an agentic AI assistant running in a sandboxed Docker container.
You can use tools to interact with the workspace filesystem and execute commands.

{format_tools_for_prompt()}
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
    
    # Load persisted conversation history if none provided
    if not history and user_id:
        history = load_conversation_history(user_id)
        if history:
            logger.info(f"Loaded {len(history)} persisted messages for {user_id}")
    
    # Load system prompt (with onboarding if bot unconfigured)
    system_prompt = load_system_prompt()
    
    # Load user-specific context if user_id provided
    if user_id:
        ensure_user_dir(user_id)
        user_context = load_full_context(user_id)
        if user_context:
            system_prompt += f"\n\n# Context\n\n{user_context}"
    
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
    
    # Fallback: if response is empty or only tool calls, include last tool result
    clean_response = re.sub(r'<tool_?call>.*?</tool_?call>', '', final_response, flags=re.DOTALL | re.IGNORECASE).strip()
    if not clean_response and last_tool_result:
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
