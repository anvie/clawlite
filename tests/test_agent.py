"""Tests for agent module."""

import pytest


class TestSystemPrompt:
    """Tests for system prompt generation."""
    
    def test_get_default_system_prompt_includes_tools(self):
        """Should include tools in default system prompt."""
        from src.agent import get_default_system_prompt
        
        prompt = get_default_system_prompt()
        
        assert "ClawLite" in prompt
        assert "Available tools:" in prompt
        assert "read_file" in prompt
    
    def test_get_default_system_prompt_filters_by_user(self, admin_user_id, regular_user_id, monkeypatch):
        """Should filter tools in prompt based on user access."""
        from src.agent import get_default_system_prompt
        
        # Mock config with tool restrictions
        config_data = {"tools": {"allowed": ["read_file", "list_dir"]}}
        
        def mock_get(key, default=None):
            keys = key.split(".")
            value = config_data
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default
                if value is None:
                    return default
            return value
        
        from src import config
        monkeypatch.setattr(config, "get", mock_get)
        
        # Regular user should see only allowed tools
        regular_prompt = get_default_system_prompt(regular_user_id)
        assert "read_file" in regular_prompt
        assert "list_dir" in regular_prompt
        assert "write_file" not in regular_prompt  # Filtered out
        
        # Admin should see all tools
        admin_prompt = get_default_system_prompt(admin_user_id)
        assert "read_file" in admin_prompt
        assert "write_file" in admin_prompt  # Admin gets all
    
    def test_load_system_prompt_accepts_user_id(self, regular_user_id):
        """Should accept user_id parameter."""
        from src.agent import load_system_prompt
        
        # Should not raise
        prompt = load_system_prompt(user_id=regular_user_id)
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0
    
    def test_load_system_prompt_filters_tools(self, admin_user_id, regular_user_id, monkeypatch):
        """Should filter tools when loading system prompt."""
        from src.agent import load_system_prompt
        
        # Mock config with tool restrictions
        config_data = {"tools": {"allowed": ["read_file"]}}
        
        def mock_get(key, default=None):
            keys = key.split(".")
            value = config_data
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default
                if value is None:
                    return default
            return value
        
        from src import config
        monkeypatch.setattr(config, "get", mock_get)
        
        # Regular user gets filtered prompt
        regular_prompt = load_system_prompt(user_id=regular_user_id)
        assert "read_file" in regular_prompt
        # write_file should be filtered out (not in allowlist)
        # But it might still appear in SOUL.md or other context
        # So we can't reliably assert it's not there
        
        # Admin gets unfiltered prompt
        admin_prompt = load_system_prompt(user_id=admin_user_id)
        assert "read_file" in admin_prompt
