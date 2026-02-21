"""Web search and fetch tools."""

import asyncio
import logging
from typing import Optional
from .base import Tool, ToolResult

logger = logging.getLogger("clawlite.tools.web")


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web using DuckDuckGo. Returns titles, URLs, and snippets."
    parameters = {
        "query": "string - search query",
        "max_results": "integer - max results to return (default: 5, max: 10)"
    }
    
    async def execute(
        self,
        query: str = "",
        max_results: int = 5,
        **kwargs
    ) -> ToolResult:
        if not query:
            return ToolResult(False, "", "Query is required")
        
        max_results = min(max(1, max_results), 10)
        
        try:
            # Run sync DDGS in thread pool
            from duckduckgo_search import DDGS
            
            def do_search():
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=max_results))
                return results
            
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, do_search)
            
            if not results:
                return ToolResult(True, "No results found")
            
            # Format results
            output_lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "No title")
                url = r.get("href", r.get("link", ""))
                snippet = r.get("body", r.get("snippet", ""))[:200]
                output_lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}\n")
            
            return ToolResult(True, "\n".join(output_lines))
            
        except ImportError:
            return ToolResult(False, "", "duckduckgo-search not installed. Run: pip install duckduckgo-search")
        except Exception as e:
            logger.exception("Web search failed")
            return ToolResult(False, "", f"Search failed: {str(e)}")


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch and extract readable content from a URL"
    parameters = {
        "url": "string - URL to fetch",
        "max_chars": "integer - max characters to return (default: 8000)"
    }
    
    async def execute(
        self,
        url: str = "",
        max_chars: int = 8000,
        **kwargs
    ) -> ToolResult:
        if not url:
            return ToolResult(False, "", "URL is required")
        
        if not url.startswith(("http://", "https://")):
            return ToolResult(False, "", "URL must start with http:// or https://")
        
        max_chars = min(max(500, max_chars), 50000)
        
        try:
            # Try trafilatura first (better extraction)
            try:
                import trafilatura
                
                def do_fetch():
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        return trafilatura.extract(
                            downloaded,
                            include_links=True,
                            include_tables=True,
                            output_format="txt"
                        )
                    return None
                
                loop = asyncio.get_event_loop()
                content = await loop.run_in_executor(None, do_fetch)
                
                if content:
                    if len(content) > max_chars:
                        content = content[:max_chars] + "\n\n[...truncated]"
                    return ToolResult(True, content)
                    
            except ImportError:
                logger.warning("trafilatura not installed, falling back to httpx")
            
            # Fallback to httpx + basic extraction
            import httpx
            
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ClawLite/1.0)"
                })
                resp.raise_for_status()
                html = resp.text
            
            # Basic HTML to text (strip tags)
            import re
            # Remove script/style
            html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
            # Remove tags
            text = re.sub(r'<[^>]+>', ' ', html)
            # Clean whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n[...truncated]"
            
            return ToolResult(True, text if text else "No readable content extracted")
            
        except httpx.HTTPStatusError as e:
            return ToolResult(False, "", f"HTTP error {e.response.status_code}: {e.response.reason_phrase}")
        except httpx.TimeoutException:
            return ToolResult(False, "", "Request timed out")
        except Exception as e:
            logger.exception("Web fetch failed")
            return ToolResult(False, "", f"Fetch failed: {str(e)}")
