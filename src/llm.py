"""LLM Client with multi-provider support (Ollama, OpenRouter)."""

import os
import json
import httpx
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional, Tuple

# Provider config
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

# Ollama config
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# OpenRouter config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def stream_generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        images: list[str] = None,  # List of base64 encoded images
    ) -> AsyncGenerator[Tuple[str, bool, Optional[str]], None]:
        """
        Stream response from LLM.
        
        Yields: (token, is_thinking, thinking_content)
        """
        pass
    
    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        images: list[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """Generate response (non-streaming)."""
        full_response = ""
        thinking = None
        
        async for token, is_thinking, thinking_content in self.stream_generate(prompt, system, temperature, images):
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


class OllamaProvider(LLMProvider):
    """Ollama LLM provider."""
    
    def __init__(self, host: str = OLLAMA_HOST, model: str = OLLAMA_MODEL):
        self.host = host
        self.model = model
    
    async def stream_generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        images: list[str] = None,  # Not supported by Ollama text models
    ) -> AsyncGenerator[Tuple[str, bool, Optional[str]], None]:
        """Stream response from Ollama."""
        
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
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
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


class OpenRouterProvider(LLMProvider):
    """OpenRouter LLM provider (OpenAI-compatible API)."""
    
    def __init__(
        self,
        api_key: str = OPENROUTER_API_KEY,
        model: str = OPENROUTER_MODEL,
        base_url: str = OPENROUTER_BASE_URL,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
    
    async def stream_generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        images: list[str] = None,  # List of base64 encoded images
    ) -> AsyncGenerator[Tuple[str, bool, Optional[str]], None]:
        """Stream response from OpenRouter."""
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        
        # Build user message content (multimodal if images provided)
        if images:
            content = []
            # Add text first
            content.append({"type": "text", "text": prompt})
            # Add images
            for img_base64 in images:
                # Detect image type from base64 header or default to jpeg
                if img_base64.startswith("/9j/"):
                    mime = "image/jpeg"
                elif img_base64.startswith("iVBOR"):
                    mime = "image/png"
                elif img_base64.startswith("R0lGOD"):
                    mime = "image/gif"
                elif img_base64.startswith("UklGR"):
                    mime = "image/webp"
                else:
                    mime = "image/jpeg"
                
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{img_base64}"}
                })
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})
        
        full_response = ""
        thinking_buffer = ""
        in_thinking = False
        thinking_done = False
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/anvie/clawlite",
            "X-Title": "ClawLite",
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "temperature": temperature,
                    "top_p": 0.9,
                }
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        
                        delta = choices[0].get("delta", {})
                        token = delta.get("content", "")
                        
                        if not token:
                            continue
                        
                        full_response += token
                        
                        # Check for thinking tags (same logic as Ollama)
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
                        
                    except json.JSONDecodeError:
                        continue


def get_provider() -> LLMProvider:
    """Get the configured LLM provider."""
    if LLM_PROVIDER == "openrouter":
        return OpenRouterProvider()
    else:
        return OllamaProvider()


# Backward compatibility - expose functions that use the configured provider
_provider: Optional[LLMProvider] = None

def _get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


async def stream_generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    images: list[str] = None,
) -> AsyncGenerator[Tuple[str, bool, Optional[str]], None]:
    """Stream response from configured LLM provider."""
    provider = _get_provider()
    async for item in provider.stream_generate(prompt, system, temperature, images):
        yield item


async def generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    images: list[str] = None,
) -> Tuple[str, Optional[str]]:
    """Generate response from configured LLM provider."""
    provider = _get_provider()
    return await provider.generate(prompt, system, temperature, images)
