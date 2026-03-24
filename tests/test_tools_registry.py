"""Tests for tools registry and filtering."""

import pytest


class TestToolsRegistry:
    """Tests for tool registration and retrieval."""
    
    def test_get_tool_returns_tool(self):
        """Should return tool by name."""
        from src.tools import get_tool
        
        tool = get_tool("read_file")
        
        assert tool is not None
        assert tool.name == "read_file"
    
    def test_get_tool_returns_none_for_unknown(self):
        """Should return None for unknown tool."""
        from src.tools import get_tool
        
        tool = get_tool("nonexistent_tool")
        
        assert tool is None
    
    def test_get_tool_sets_user_id(self):
        """Should set user_id on returned tool."""
        from src.tools import get_tool
        
        tool = get_tool("read_file", user_id="tg_123456")
        
        assert tool.user_id == "tg_123456"
    
    def test_list_tools_returns_all(self):
        """Should list all available tools."""
        from src.tools import list_tools
        
        tools = list_tools()
        
        assert isinstance(tools, list)
        assert len(tools) > 0
        
        # Check structure
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t
    
    def test_format_tools_for_prompt(self):
        """Should format tools for system prompt."""
        from src.tools import format_tools_for_prompt
        
        formatted = format_tools_for_prompt()
        
        assert "Available tools:" in formatted
        assert "read_file" in formatted
        assert "write_file" in formatted
    
    def test_format_tools_for_prompt_filters_by_user(self, admin_user_id, regular_user_id, monkeypatch):
        """Should filter tools based on user access."""
        from src.tools import format_tools_for_prompt
        
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
        
        # Regular user should get filtered list
        regular_prompt = format_tools_for_prompt(regular_user_id)
        assert "read_file" in regular_prompt
        assert "list_dir" in regular_prompt
        assert "write_file" not in regular_prompt  # Filtered out
        
        # Admin should get all tools
        admin_prompt = format_tools_for_prompt(admin_user_id)
        assert "read_file" in admin_prompt
        assert "write_file" in admin_prompt  # Admin gets all tools


class TestToolFiltering:
    """Tests for tool filtering based on config."""
    
    @pytest.fixture
    def mock_config(self, monkeypatch):
        """Mock config to control tool filtering."""
        config_data = {
            "tools": {
                "allowed": ["read_file", "list_dir"],
            }
        }
        
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
        
        return config_data
    
    def test_filtering_with_allowlist(self, mock_config, monkeypatch):
        """Should filter tools based on allowlist."""
        # Need to reimport to apply filter
        from src.tools import _filter_tools_by_config, _ALL_TOOLS
        
        filtered = _filter_tools_by_config(_ALL_TOOLS)
        
        assert "read_file" in filtered
        assert "list_dir" in filtered
        assert "write_file" not in filtered
        assert "exec" not in filtered
    
    def test_admin_bypasses_filter(self, mock_config, monkeypatch, admin_user_id):
        """Admin users should get all tools regardless of filter."""
        from src.tools import _filter_tools_by_config, _ALL_TOOLS
        
        filtered = _filter_tools_by_config(_ALL_TOOLS, user_id=admin_user_id)
        
        # Admin gets all tools
        assert "read_file" in filtered
        assert "write_file" in filtered
        assert "exec" in filtered
    
    def test_empty_allowlist_enables_all(self, monkeypatch):
        """Empty allowlist should enable all tools."""
        config_data = {"tools": {"allowed": []}}
        
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
        
        from src.tools import _filter_tools_by_config, _ALL_TOOLS
        
        filtered = _filter_tools_by_config(_ALL_TOOLS)
        
        # All tools enabled
        assert len(filtered) == len(_ALL_TOOLS)


class TestUserScopedTools:
    """Tests for user-scoped tools (memory tools)."""
    
    def test_get_user_tools_creates_instances(self):
        """Should create user-scoped tool instances."""
        from src.tools import get_user_tools
        
        tools = get_user_tools("tg_123")
        
        assert "memory_log" in tools
        assert "memory_read" in tools
        assert "memory_update" in tools
        # assert "user_update" in tools
    
    def test_user_tools_have_user_id_set(self):
        """User-scoped tools should have user_id set."""
        from src.tools import get_user_tools
        
        tools = get_user_tools("tg_123")
        
        for name, tool in tools.items():
            assert tool.user_id == "tg_123"
    
    def test_different_users_get_different_instances(self):
        """Different users should get different tool instances."""
        from src.tools import get_user_tools
        
        tools1 = get_user_tools("tg_user1")
        tools2 = get_user_tools("tg_user2")
        
        assert tools1["memory_log"] is not tools2["memory_log"]
        assert tools1["memory_log"].user_id == "tg_user1"
        assert tools2["memory_log"].user_id == "tg_user2"
    
    def test_get_all_tools_includes_user_tools(self):
        """get_all_tools should include user-scoped tools when user_id provided."""
        from src.tools import get_all_tools
        
        tools = get_all_tools(user_id="tg_123")
        
        assert "read_file" in tools  # Shared tool
        assert "memory_log" in tools  # User-scoped tool
