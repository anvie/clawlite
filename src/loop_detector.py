"""Smart loop detection for agent tool calls.

Combines three strategies:
1. Argument-based: Same tool + same args = high loop score
2. Result-based: Same tool + same result = medium loop score
3. Graduated intervention: Warn → Block (not abrupt)

Scoring:
- Same tool + same args + same result: +3 (definite loop)
- Same tool + same args (any result): +2 (likely loop)
- Same tool + same result (diff args): +1 (possible loop)
- Different tool or different args+result: reset score

Interventions:
- Score 0-2: ✅ Allow (normal operation)
- Score 3-4: ⚠️ Warn (inject suggestion)
- Score 5+: 🛑 Block (force different approach)
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional
from collections import deque

logger = logging.getLogger("clawlite.loop_detector")


@dataclass
class ToolCallRecord:
    """Record of a single tool call."""
    tool_name: str
    args_hash: str
    result_hash: Optional[str] = None


class LoopDetector:
    """Smart loop detector with multi-factor analysis."""
    
    WARNING_THRESHOLD = 2  # Warn earlier (was 3)
    BLOCK_THRESHOLD = 4    # Block earlier (was 5)
    MAX_HISTORY = 20
    
    def __init__(self):
        self.history: deque[ToolCallRecord] = deque(maxlen=self.MAX_HISTORY)
        self.loop_score = 0
        self.last_call: Optional[ToolCallRecord] = None
        self.warned = False
    
    def _hash_args(self, args: dict) -> str:
        """Create stable hash of tool arguments."""
        try:
            serialized = json.dumps(args, sort_keys=True, default=str)
            return hashlib.md5(serialized.encode()).hexdigest()[:12]
        except Exception:
            return "unhashable"
    
    def _hash_result(self, result: str) -> str:
        """Create hash of tool result (first 500 chars)."""
        truncated = (result or "")[:500]
        return hashlib.md5(truncated.encode()).hexdigest()[:12]
    
    def check(self, tool_name: str, args: dict, result: Optional[str] = None) -> tuple:
        """
        Check if current tool call indicates a loop.
        
        Returns:
            (should_allow: bool, warning_msg: str|None)
        """
        args_hash = self._hash_args(args)
        result_hash = self._hash_result(result) if result else None
        
        current_call = ToolCallRecord(tool_name, args_hash, result_hash)
        
        # Calculate score adjustment
        if self.last_call:
            if self.last_call.tool_name == tool_name:
                if self.last_call.args_hash == args_hash:
                    if result_hash and self.last_call.result_hash == result_hash:
                        # Exact same call with same result - definite loop (+3)
                        self.loop_score += 3
                        logger.debug(f"Loop +3 (same tool+args+result): {tool_name} score={self.loop_score}")
                    else:
                        # Same tool and args, different/no result - likely loop (+2)
                        self.loop_score += 2
                        logger.debug(f"Loop +2 (same tool+args): {tool_name} score={self.loop_score}")
                elif result_hash and self.last_call.result_hash == result_hash:
                    # Same tool, different args, but same result - possible loop (+1)
                    self.loop_score += 1
                    logger.debug(f"Loop +1 (same tool+result): {tool_name} score={self.loop_score}")
                else:
                    # Same tool but different args and result - making progress (reset)
                    self.loop_score = max(0, self.loop_score - 1)
                    logger.debug(f"Loop -1 (progress): {tool_name} score={self.loop_score}")
            else:
                # Different tool - full reset
                self.loop_score = 0
                self.warned = False
                logger.debug(f"Loop reset (different tool: {tool_name})")
        
        # Store for next comparison
        self.last_call = current_call
        self.history.append(current_call)
        
        # Determine intervention
        if self.loop_score >= self.BLOCK_THRESHOLD:
            return (
                False,
                f"🛑 I notice you've been calling `{tool_name}` repeatedly without progress. "
                f"Please try a different approach or summarize your findings."
            )
        elif self.loop_score >= self.WARNING_THRESHOLD:
            if not self.warned:
                self.warned = True
                return (
                    True,
                    f"⚠️ You've called `{tool_name}` multiple times. "
                    f"Consider trying a different approach if not making progress."
                )
        
        return (True, None)
    
    def reset(self):
        """Reset detector state."""
        self.history.clear()
        self.loop_score = 0
        self.last_call = None
        self.warned = False
    
    def get_stats(self) -> dict:
        """Get detection stats for debugging."""
        return {
            "loop_score": self.loop_score,
            "history_size": len(self.history),
            "last_tool": self.last_call.tool_name if self.last_call else None,
            "warned": self.warned,
        }
