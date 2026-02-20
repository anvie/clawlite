"""Agent loop with tool calling."""

import json
import re
import os
from typing import Optional, Callable, Awaitable

from .llm import stream_generate
from .tools import get_tool, format_tools_for_prompt
from .translation import translate_to_english, translate_to_indonesian, TRANSLATION_ENABLED
from .context import load_full_context, ensure_user_dir, is_new_user

# Load system prompt
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

def load_system_prompt(user_id: Optional[int] = None) -> str:
    """Load system prompt from file, with onboarding for new users."""
    prompt_file = os.path.join(PROMPTS_DIR, "system.md")
    try:
        with open(prompt_file, "r") as f:
            prompt = f.read()
    except FileNotFoundError:
        prompt = get_default_system_prompt()
    
    # Add onboarding instructions for new users
    if user_id and is_new_user(user_id):
        onboarding_file = os.path.join(PROMPTS_DIR, "onboarding.md")
        try:
            with open(onboarding_file, "r") as f:
                prompt += "\n\n" + f.read()
        except FileNotFoundError:
            pass
    
    return prompt


def get_default_system_prompt() -> str:
    """Default system prompt if file not found."""
    return f"""You are ClawLite, an agentic AI assistant running in a sandboxed Docker container.
You can use tools to interact with the workspace filesystem and execute commands.

{format_tools_for_prompt()}

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


async def run_agent(
    user_message: str,
    history: list[dict],
    user_id: Optional[int] = None,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    max_iterations: int = 10,
    images: list[str] = None,  # List of base64 encoded images
) -> tuple[str, list[dict]]:
    """
    Run the agent loop.
    
    Args:
        user_message: The user's input
        history: Conversation history
        user_id: Telegram user ID (for user-scoped context and tools)
        status_callback: Async callback for status updates
        max_iterations: Maximum tool call iterations
        images: List of base64 encoded images for multimodal input
    
    Returns:
        (final_response, updated_history)
    """
    # Load system prompt (with onboarding for new users)
    system_prompt = load_system_prompt(user_id)
    
    # Load user-specific context if user_id provided
    if user_id:
        ensure_user_dir(user_id)
        user_context = load_full_context(user_id)
        if user_context:
            system_prompt += f"\n\n# Context\n\n{user_context}"
    
    # Translate user message if translation is enabled
    processed_message = user_message
    if TRANSLATION_ENABLED:
        processed_message = await translate_to_english(user_message)
    
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
    
    while iterations < max_iterations:
        iterations += 1
        
        # Stream LLM response
        current_response = ""
        current_thinking = ""
        last_update = 0
        
        import asyncio
        
        # Only pass images on first iteration
        current_images = images if iterations == 1 else None
        
        async for token, is_thinking, thinking_content in stream_generate(full_prompt, images=current_images):
            current_response += token
            
            if thinking_content:
                current_thinking = thinking_content
            
            # Status updates
            current_time = asyncio.get_event_loop().time()
            if status_callback and (current_time - last_update > 1.0):
                if is_thinking and thinking_content:
                    preview = thinking_content[-400:] if len(thinking_content) > 400 else thinking_content
                    await status_callback(f"🧠 _Thinking..._\n```\n{preview}▌\n```")
                    thinking_shown = True
                elif not is_thinking and current_response:
                    # Show response progress
                    clean = current_response.split("</think>")[-1].strip() if "</think>" in current_response else current_response.strip()
                    if clean:
                        await status_callback(f"{clean[:1500]}▌")
                last_update = current_time
        
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
                tool_data = json.loads(tool_call_match.group(1))
                # Support multiple field names
                tool_name = tool_data.get("tool") or tool_data.get("name", "")
                tool_args = tool_data.get("args") or tool_data.get("arguments", {})
                
                if status_callback:
                    await status_callback(f"🔧 Calling: `{tool_name}`\n```json\n{json.dumps(tool_args, indent=2)}\n```")
                
                tool = get_tool(tool_name, user_id=user_id)
                if tool:
                    result = await tool.execute(**tool_args)
                    
                    # Format result for context (internal only, not shown to user)
                    if result.success:
                        result_text = f"{result.output[:2000]}"
                    else:
                        result_text = f"Error: {result.error}"
                    
                    # Track last tool result for fallback
                    last_tool_result = {"tool": tool_name, "result": result_text, "success": result.success}
                    
                    # Add to prompt for next iteration (LLM will interpret this)
                    full_prompt += f"{response_part}\n\n<tool_result>\n{result_text}\n</tool_result>\n\nassistant\n"
                    # Don't add raw result to user response - let LLM interpret it
                    
                else:
                    error_text = f"Unknown tool: {tool_name}"
                    full_prompt += f"{response_part}\n\n<tool_result>\n{error_text}\n</tool_result>\n\nassistant\n"
                
            except json.JSONDecodeError as e:
                error_text = f"Invalid tool call JSON: {e}"
                full_prompt += f"{response_part}\n\n<tool_result>\n{error_text}\n</tool_result>\n\nassistant\n"
        else:
            # No tool call, we're done
            break
    
    # Translate response back to Indonesian if translation is enabled
    final_response = accumulated_response
    
    # Fallback: if response is empty or only tool calls, include last tool result
    clean_response = re.sub(r'<tool_?call>.*?</tool_?call>', '', final_response, flags=re.DOTALL | re.IGNORECASE).strip()
    if not clean_response and last_tool_result:
        if last_tool_result["success"]:
            final_response = f"Result:\n```\n{last_tool_result['result']}\n```"
        else:
            final_response = f"Error: {last_tool_result['result']}"
    
    if TRANSLATION_ENABLED:
        final_response = await translate_to_indonesian(final_response)
    
    # Update history (store original messages, not translated)
    new_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_response},
    ]
    
    # Keep history bounded
    if len(new_history) > 20:
        new_history = new_history[-20:]
    
    return final_response, new_history
