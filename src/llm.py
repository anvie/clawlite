"""LLM Client with multi-provider support (Ollama, OpenRouter, Anthropic)."""

import os
import json
import httpx
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, Optional, Tuple, List, Dict, Any

logger = logging.getLogger("clawlite.llm")


# =============================================================================
# Config helpers - read from config.yaml, secrets from env vars
# =============================================================================

def _get_config(key: str, default=None):
    """Get config value from config.yaml."""
    try:
        from .config import get as config_get
        return config_get(key, default)
    except ImportError:
        return default


def get_llm_provider() -> str:
    """Get LLM provider from config."""
    return str(_get_config("llm.provider", "ollama")).lower()


def get_llm_model() -> str:
    """Get LLM model from config."""
    return str(_get_config("llm.model", "llama3.2:3b"))


def get_llm_base_url_config() -> str:
    """Get LLM base_url from config."""
    # Support both old 'host' key and new 'base_url' key for backwards compatibility
    base_url = _get_config("llm.base_url", None)
    if base_url:
        return str(base_url)
    # Fallback to old 'host' key
    return str(_get_config("llm.host", "http://localhost:11434"))


def get_llm_timeout() -> int:
    """Get LLM timeout from config."""
    return int(_get_config("llm.timeout", 60))


def get_anthropic_extended_thinking() -> bool:
    """Get Anthropic extended thinking setting from config."""
    return bool(_get_config("llm.extended_thinking", True))


def get_anthropic_thinking_budget() -> int:
    """Get Anthropic thinking budget from config."""
    return int(_get_config("llm.thinking_budget", 10000))


# Secrets - always from env vars
def get_openrouter_api_key() -> str:
    """Get OpenRouter API key from env."""
    return os.getenv("OPENROUTER_API_KEY", "")


# Fixed URLs (not configurable)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com"

# Instance name for credential resolution (set by main.py or channel)
_current_instance: Optional[str] = None

def set_instance(instance_name: Optional[str]):
    """Set current instance for credential resolution."""
    global _current_instance
    _current_instance = instance_name

def _get_anthropic_credentials() -> tuple[Optional[str], Optional[str]]:
    """Get Anthropic credentials using auth module with resolution order."""
    try:
        from .auth import get_anthropic_credentials
        return get_anthropic_credentials(_current_instance)
    except ImportError:
        # Fallback if auth module not available
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
        return (api_key or None, auth_token or None)


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass 
class ToolResult:
    """Result to send back to the LLM."""
    tool_use_id: str
    content: str
    is_error: bool = False


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @property
    def supports_native_tools(self) -> bool:
        """Whether this provider supports native tool calling."""
        return False
    
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
    
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        system: str = "",
        tools: List[Dict[str, Any]] = None,
        temperature: float = 0.3,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream response with native tool support.
        
        Only implemented by providers that support native tools.
        
        Yields dicts with:
        - {"type": "text", "text": "..."} for text content
        - {"type": "thinking", "thinking": "..."} for thinking content
        - {"type": "tool_use", "tool_call": ToolCall} for tool calls
        - {"type": "done", "stop_reason": "..."} when complete
        """
        raise NotImplementedError("This provider does not support native tools")


class OllamaProvider(LLMProvider):
    """Ollama LLM provider."""
    
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or get_llm_base_url_config()).rstrip("/")
        self.model = model or get_llm_model()
    
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
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": True,
                    "options": {
                        "temperature": _get_config('llm.temperature', temperature),
                        "top_p": _get_config('llm.top_p', 0.9),
                        "top_k": _get_config('llm.top_k', 50),
                        "repeat_penalty": _get_config('llm.repeat_penalty', 1.1),
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
        api_key: str = None,
        model: str = None,
        base_url: str = None,
    ):
        self.api_key = api_key or get_openrouter_api_key()
        self.model = model or get_llm_model()
        self.base_url = (base_url or OPENROUTER_BASE_URL).rstrip("/")
    
    async def stream_generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        images: list[str] = None,  # List of base64 encoded images
    ) -> AsyncGenerator[Tuple[str, bool, Optional[str]], None]:
        """Stream response from OpenRouter or OpenAI-compatible server."""
        
        # Only require API key for actual OpenRouter (not self-hosted)
        is_self_hosted = self.base_url != OPENROUTER_BASE_URL
        if not is_self_hosted and not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        
        # For Qwen3.5 models on vLLM, disable thinking mode to get direct responses
        is_qwen35 = "qwen3.5" in self.model.lower() or "qwen3_5" in self.model.lower()
        if is_qwen35 and is_self_hosted:
            prompt = prompt + " /no_think"
        
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
            "Content-Type": "application/json",
        }
        
        # Only add OpenRouter-specific headers for actual OpenRouter
        if not is_self_hosted:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["HTTP-Referer"] = "https://github.com/anvie/clawlite"
            headers["X-Title"] = "ClawLite"
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        request_body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "top_p": 0.9,
        }
        
        # Add thinking control for self-hosted servers (e.g. llama.cpp + Qwen3.5)
        if is_self_hosted:
            enable_thinking = get_llm_enable_thinking()
            request_body["chat_template_kwargs"] = {
                "enable_thinking": enable_thinking
            }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=request_body,
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
                        reasoning = delta.get("reasoning_content", "")
                        
                        # Handle reasoning_content field (llama.cpp / Qwen3.5 style)
                        if reasoning:
                            thinking_buffer += reasoning
                            in_thinking = True
                            yield ("", True, thinking_buffer)
                            continue
                        
                        # If we were in reasoning and now got content, mark thinking done
                        if in_thinking and token:
                            thinking_done = True
                            in_thinking = False
                        
                        if not token:
                            continue
                        
                        full_response += token
                        
                        # Check for thinking tags (Ollama / inline style fallback)
                        if "<think>" in full_response and not in_thinking and not thinking_done:
                            in_thinking = True
                            thinking_buffer = ""
                        
                        # Check for Qwen3.5 "Thinking Process:" prefix (vLLM without reasoning parser)
                        if full_response.startswith("Thinking Process:") and not in_thinking and not thinking_done:
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


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider with native tool support.
    
    Supports two auth methods:
    - API Key: ANTHROPIC_API_KEY (sk-ant-xxx format)
    - OAuth Token: ANTHROPIC_AUTH_TOKEN (from `claude setup-token`)
    
    Credentials are resolved via auth module:
    1. Instance credentials (~/.clawlite/instances/<name>/credentials.json)
    2. Global credentials (~/.clawlite/credentials.json)
    3. Environment variables (fallback)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        auth_token: Optional[str] = None,
        model: str = None,
        base_url: str = None,
        extended_thinking: bool = None,
        thinking_budget: int = None,
    ):
        # Resolve credentials if not explicitly provided
        if api_key is None and auth_token is None:
            api_key, auth_token = _get_anthropic_credentials()
        
        self.api_key = api_key
        self.auth_token = auth_token
        
        # Get config values with defaults
        self.model = model or get_llm_model()
        self.base_url = (base_url or ANTHROPIC_BASE_URL).rstrip("/")
        self.extended_thinking = extended_thinking if extended_thinking is not None else get_anthropic_extended_thinking()
        self.thinking_budget = thinking_budget if thinking_budget is not None else get_anthropic_thinking_budget()
        
        # Determine auth mode
        self.use_oauth = bool(auth_token)
        if self.use_oauth:
            logger.info("Anthropic: Using OAuth token auth")
        elif self.api_key:
            logger.info("Anthropic: Using API key auth")
        else:
            logger.warning("Anthropic: No credentials found")
    
    def _get_auth_headers(self) -> dict:
        """Get authentication headers based on auth mode."""
        if self.use_oauth:
            return {
                "Authorization": f"Bearer {self.auth_token}",
                "anthropic-beta": "oauth-2025-04-20",
            }
        else:
            return {
                "x-api-key": self.api_key,
            }
    
    @property
    def supports_native_tools(self) -> bool:
        return True
    
    def _detect_image_mime(self, img_base64: str) -> str:
        """Detect image MIME type from base64 prefix."""
        if img_base64.startswith("/9j/"):
            return "image/jpeg"
        elif img_base64.startswith("iVBOR"):
            return "image/png"
        elif img_base64.startswith("R0lGOD"):
            return "image/gif"
        elif img_base64.startswith("UklGR"):
            return "image/webp"
        return "image/jpeg"
    
    def _build_content_blocks(self, prompt: str, images: list[str] = None) -> list:
        """Build content blocks for user message."""
        blocks = []
        
        # Add images first if provided
        if images:
            for img_base64 in images:
                mime = self._detect_image_mime(img_base64)
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": img_base64,
                    }
                })
        
        # Add text
        blocks.append({"type": "text", "text": prompt})
        return blocks
    
    async def stream_generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        images: list[str] = None,
    ) -> AsyncGenerator[Tuple[str, bool, Optional[str]], None]:
        """Stream response from Anthropic (without tools)."""
        
        if not self.api_key and not self.auth_token:
            raise ValueError("ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN not set")
        
        # Build user message content
        if images:
            content = self._build_content_blocks(prompt, images)
        else:
            content = prompt
        
        messages = [{"role": "user", "content": content}]
        
        headers = {
            **self._get_auth_headers(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        
        # Build request body
        body = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        
        if system:
            body["system"] = system
        
        # Add extended thinking if enabled
        if self.extended_thinking:
            headers["anthropic-beta"] = "interleaved-thinking-2025-05-14"
            body["temperature"] = 1  # Required for extended thinking
            body["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }
        
        full_response = ""
        thinking_buffer = ""
        current_block_type = None
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=body,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise Exception(f"Anthropic API error {response.status_code}: {error_text.decode()}")
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    
                    try:
                        event = json.loads(data_str)
                        event_type = event.get("type", "")
                        
                        if event_type == "content_block_start":
                            block = event.get("content_block", {})
                            current_block_type = block.get("type")
                            
                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            delta_type = delta.get("type", "")
                            
                            if delta_type == "thinking_delta":
                                # Extended thinking content
                                thinking_text = delta.get("thinking", "")
                                thinking_buffer += thinking_text
                                yield ("", True, thinking_buffer)
                                
                            elif delta_type == "text_delta":
                                # Regular text content
                                text = delta.get("text", "")
                                full_response += text
                                yield (text, False, thinking_buffer if thinking_buffer else None)
                        
                        elif event_type == "content_block_stop":
                            current_block_type = None
                            
                        elif event_type == "message_stop":
                            break
                            
                    except json.JSONDecodeError:
                        continue
    
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        system: str = "",
        tools: List[Dict[str, Any]] = None,
        temperature: float = 0.3,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream response with native tool support.
        
        Yields dicts with:
        - {"type": "text", "text": "..."} for text content
        - {"type": "thinking", "thinking": "..."} for thinking content  
        - {"type": "tool_use", "tool_call": ToolCall} for tool calls
        - {"type": "done", "stop_reason": "..."} when complete
        """
        
        if not self.api_key and not self.auth_token:
            raise ValueError("ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN not set")
        
        headers = {
            **self._get_auth_headers(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        
        body = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        
        if system:
            body["system"] = system
        
        if tools:
            body["tools"] = tools
        
        # Add extended thinking if enabled
        if self.extended_thinking:
            headers["anthropic-beta"] = "interleaved-thinking-2025-05-14"
            body["temperature"] = 1  # Required for extended thinking
            body["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }
        
        # Track current state
        current_tool_call: Optional[Dict[str, Any]] = None
        current_tool_input_json = ""
        thinking_buffer = ""
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=body,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise Exception(f"Anthropic API error {response.status_code}: {error_text.decode()}")
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data_str = line[6:]
                    
                    try:
                        event = json.loads(data_str)
                        event_type = event.get("type", "")
                        
                        if event_type == "content_block_start":
                            block = event.get("content_block", {})
                            block_type = block.get("type")
                            
                            if block_type == "tool_use":
                                # Start tracking tool call
                                current_tool_call = {
                                    "id": block.get("id", ""),
                                    "name": block.get("name", ""),
                                }
                                current_tool_input_json = ""
                                
                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            delta_type = delta.get("type", "")
                            
                            if delta_type == "thinking_delta":
                                thinking_text = delta.get("thinking", "")
                                thinking_buffer += thinking_text
                                yield {"type": "thinking", "thinking": thinking_buffer}
                                
                            elif delta_type == "text_delta":
                                text = delta.get("text", "")
                                yield {"type": "text", "text": text}
                                
                            elif delta_type == "input_json_delta":
                                # Accumulate tool input JSON
                                partial_json = delta.get("partial_json", "")
                                current_tool_input_json += partial_json
                        
                        elif event_type == "content_block_stop":
                            # If we were building a tool call, emit it now
                            if current_tool_call:
                                try:
                                    args = json.loads(current_tool_input_json) if current_tool_input_json else {}
                                except json.JSONDecodeError:
                                    args = {}
                                    logger.warning(f"Failed to parse tool args: {current_tool_input_json[:100]}")
                                
                                tool_call = ToolCall(
                                    id=current_tool_call["id"],
                                    name=current_tool_call["name"],
                                    arguments=args,
                                )
                                yield {"type": "tool_use", "tool_call": tool_call}
                                current_tool_call = None
                                current_tool_input_json = ""
                        
                        elif event_type == "message_delta":
                            # Check stop reason
                            delta = event.get("delta", {})
                            stop_reason = delta.get("stop_reason")
                            if stop_reason:
                                yield {"type": "done", "stop_reason": stop_reason}
                                
                        elif event_type == "message_stop":
                            yield {"type": "done", "stop_reason": "end_turn"}
                            break
                            
                    except json.JSONDecodeError:
                        continue


def get_llm_base_url() -> str:
    """Get custom LLM base URL from config (for self-hosted OpenAI-compatible servers).
    
    Deprecated: Use get_llm_base_url_config() instead.
    """
    return str(_get_config("llm.base_url", ""))


def get_llm_enable_thinking() -> bool:
    """Get thinking toggle from config (for Qwen3.5 models via llama.cpp)."""
    return bool(_get_config("llm.enable_thinking", True))


def get_provider() -> LLMProvider:
    """Get the configured LLM provider."""
    provider = get_llm_provider()
    if provider == "anthropic":
        return AnthropicProvider()
    elif provider == "openrouter":
        base_url = get_llm_base_url_config()
        # Only override if not default ollama URL
        if base_url == "http://localhost:11434":
            base_url = OPENROUTER_BASE_URL
        return OpenRouterProvider(base_url=base_url)
    elif provider in ("llama-server", "vllm", "openai"):
        # OpenAI-compatible API (llama.cpp, vLLM, etc.)
        base_url = get_llm_base_url_config()
        return OpenRouterProvider(base_url=base_url)
    else:
        # Default: ollama
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


def supports_native_tools() -> bool:
    """Check if current provider supports native tool calling."""
    provider = _get_provider()
    return provider.supports_native_tools


async def stream_with_tools(
    messages: List[Dict[str, Any]],
    system: str = "",
    tools: List[Dict[str, Any]] = None,
    temperature: float = 0.3,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream response with native tool support (if available)."""
    provider = _get_provider()
    async for item in provider.stream_with_tools(messages, system, tools, temperature):
        yield item


def convert_tools_to_anthropic_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert ClawLite tool definitions to Anthropic tool format.
    
    ClawLite format:
    {
        "name": "tool_name",
        "description": "Tool description",
        "parameters": {"param1": "description", "param2": "description"}
    }
    
    Anthropic format:
    {
        "name": "tool_name",
        "description": "Tool description",
        "input_schema": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
    """
    anthropic_tools = []
    
    for tool in tools:
        name = tool.get("name", "")
        description = tool.get("description", "")
        params = tool.get("parameters", {})
        
        # Convert simple param descriptions to JSON schema
        properties = {}
        required = []
        
        for param_name, param_desc in params.items():
            # Parse param description for type hints
            # Format: "description (type)" or just "description"
            if isinstance(param_desc, str):
                param_type = "string"  # default
                desc = param_desc
                
                # Check for type hints in parentheses
                if "(" in param_desc and ")" in param_desc:
                    # Try to extract type from description
                    parts = param_desc.rsplit("(", 1)
                    if len(parts) == 2:
                        desc = parts[0].strip()
                        type_hint = parts[1].rstrip(")").strip().lower()
                        if type_hint in ("int", "integer", "number"):
                            param_type = "integer"
                        elif type_hint in ("bool", "boolean"):
                            param_type = "boolean"
                        elif type_hint in ("list", "array"):
                            param_type = "array"
                
                properties[param_name] = {
                    "type": param_type,
                    "description": desc,
                }
                
                # Mark as required if description doesn't indicate optional
                if "optional" not in param_desc.lower():
                    required.append(param_name)
            
            elif isinstance(param_desc, dict):
                # Already in JSON schema format
                properties[param_name] = param_desc
                if param_desc.get("required", True):
                    required.append(param_name)
        
        anthropic_tools.append({
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        })
    
    return anthropic_tools


def build_tool_result_message(tool_results: List[ToolResult]) -> Dict[str, Any]:
    """Build a user message containing tool results for Anthropic."""
    content = []
    for result in tool_results:
        content.append({
            "type": "tool_result",
            "tool_use_id": result.tool_use_id,
            "content": result.content,
            "is_error": result.is_error,
        })
    return {"role": "user", "content": content}
