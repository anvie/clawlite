"""Ollama LLM Client with streaming support."""

import os
import json
import httpx
from typing import AsyncGenerator, Optional, Tuple

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


async def stream_generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
) -> AsyncGenerator[Tuple[str, bool, Optional[str]], None]:
    """
    Stream response from Ollama.
    
    Yields: (token, is_thinking, thinking_content)
    - token: the text token
    - is_thinking: True if currently in <think> block
    - thinking_content: accumulated thinking so far (only when in thinking mode)
    """
    
    full_prompt = prompt
    if system:
        full_prompt = f"system\n{system}\n\nuser\n{prompt}"
    
    full_response = ""
    thinking_buffer = ""
    in_thinking = False
    thinking_done = False
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "top_p": 0.9,
                    "top_k": 50,
                    "repeat_penalty": 1.1,
                }
            }
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    token = data.get("response", "")
                    full_response += token
                    
                    # Check for thinking tags
                    if "<think>" in full_response and not in_thinking:
                        in_thinking = True
                        thinking_buffer = ""
                    
                    if in_thinking and not thinking_done:
                        if "</think>" in full_response:
                            thinking_done = True
                            think_start = full_response.find("<think>") + len("<think>")
                            think_end = full_response.find("</think>")
                            thinking_buffer = full_response[think_start:think_end].strip()
                            yield (token, False, thinking_buffer)
                        else:
                            think_start = full_response.find("<think>") + len("<think>")
                            thinking_buffer = full_response[think_start:].strip()
                            yield (token, True, thinking_buffer)
                    else:
                        yield (token, False, thinking_buffer if thinking_done else None)
                    
                    if data.get("done", False):
                        break
                        
                except json.JSONDecodeError:
                    continue


async def generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
) -> Tuple[str, Optional[str]]:
    """
    Generate response from Ollama (non-streaming).
    
    Returns: (response, thinking)
    """
    full_response = ""
    thinking = None
    
    async for token, is_thinking, thinking_content in stream_generate(prompt, system, temperature):
        full_response += token
        if thinking_content:
            thinking = thinking_content
    
    # Extract final response (after </think>)
    if "</think>" in full_response:
        parts = full_response.split("</think>")
        final_response = parts[-1].strip()
    else:
        final_response = full_response.strip()
    
    return final_response, thinking
