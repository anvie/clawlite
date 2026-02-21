"""Internal HTTP API for ClawLite service."""

import asyncio
import logging
from aiohttp import web
from typing import Optional, Callable, Awaitable

logger = logging.getLogger("clawlite.api")


class APIServer:
    """Simple HTTP API server for internal service calls."""
    
    def __init__(
        self,
        send_callback: Callable[[str, str], Awaitable[bool]],
        host: str = "127.0.0.1",
        port: int = 8080,
    ):
        """
        Initialize API server.
        
        Args:
            send_callback: Async function(user_id, message) -> bool
            host: Bind host (default localhost only)
            port: Bind port
        """
        self.send_callback = send_callback
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up API routes."""
        self.app.router.add_post("/api/send", self._handle_send)
        self.app.router.add_get("/api/health", self._handle_health)
    
    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "ok"})
    
    async def _handle_send(self, request: web.Request) -> web.Response:
        """
        Send message to user.
        
        POST /api/send
        Body: user=tg_123456&message=Hello
        Or JSON: {"user": "tg_123456", "message": "Hello"}
        """
        try:
            # Try JSON first, then form data
            content_type = request.content_type
            if content_type == "application/json":
                data = await request.json()
                user_id = data.get("user", "")
                message = data.get("message", "")
            else:
                data = await request.post()
                user_id = data.get("user", "")
                message = data.get("message", "")
            
            if not user_id or not message:
                return web.json_response(
                    {"error": "Missing 'user' or 'message' parameter"},
                    status=400
                )
            
            logger.info(f"API send request: user={user_id}, message_len={len(message)}")
            
            # Call the send callback
            success = await self.send_callback(user_id, message)
            
            if success:
                return web.json_response({"status": "sent", "user": user_id})
            else:
                return web.json_response(
                    {"error": "Failed to send message"},
                    status=500
                )
                
        except Exception as e:
            logger.exception("API send error")
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    async def start(self):
        """Start the API server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"API server started on http://{self.host}:{self.port}")
    
    async def stop(self):
        """Stop the API server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("API server stopped")
