"""Tests for configuration module."""

import os
import tempfile
import pytest
import yaml


class TestConfigLoading:
    """Tests for config loading."""
    
    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file."""
        config = {
            "llm": {
                "provider": "ollama",
                "model": "test-model",
                "host": "http://localhost:11434",
                "timeout": 30,
            },
            "access": {
                "allowed_users": ["tg_123", "tg_456"],
                "admins": ["tg_admin"],
            },
            "channels": {
                "telegram": {"enabled": True},
                "whatsapp": {"enabled": False},
            },
            "tools": {
                "allowed": ["read_file", "write_file"],
            },
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            filepath = f.name
        
        yield filepath
        
        # Cleanup
        os.unlink(filepath)
    
    def test_load_config(self, temp_config_file, monkeypatch):
        """Should load config from file."""
        monkeypatch.setenv("CLAWLITE_CONFIG", temp_config_file)
        
        # Clear cached config
        from src import config
        config._config = None
        
        loaded = config.load_config()
        
        assert loaded["llm"]["provider"] == "ollama"
        assert loaded["llm"]["model"] == "test-model"
    
    def test_get_nested_value(self, temp_config_file, monkeypatch):
        """Should get nested config values with dot notation."""
        monkeypatch.setenv("CLAWLITE_CONFIG", temp_config_file)
        
        from src import config
        config._config = None
        config.load_config()
        
        assert config.get("llm.provider") == "ollama"
        assert config.get("llm.model") == "test-model"
        assert config.get("llm.timeout") == 30
        assert config.get("access.admins") == ["tg_admin"]
    
    def test_get_with_default(self, temp_config_file, monkeypatch):
        """Should return default for missing keys."""
        monkeypatch.setenv("CLAWLITE_CONFIG", temp_config_file)
        
        from src import config
        config._config = None
        config.load_config()
        
        assert config.get("nonexistent.key", "default") == "default"
        assert config.get("llm.nonexistent", 42) == 42
    
    def test_get_section(self, temp_config_file, monkeypatch):
        """Should get entire config section."""
        monkeypatch.setenv("CLAWLITE_CONFIG", temp_config_file)
        
        from src import config
        config._config = None
        config.load_config()
        
        llm_section = config.get_section("llm")
        
        assert isinstance(llm_section, dict)
        assert llm_section["provider"] == "ollama"
        assert llm_section["model"] == "test-model"
    
    def test_missing_config_uses_defaults(self, monkeypatch):
        """Should use empty dict when config file missing."""
        monkeypatch.setenv("CLAWLITE_CONFIG", "/nonexistent/path/config.yaml")
        
        from src import config
        config._config = None
        loaded = config.load_config()
        
        assert loaded == {}
        assert config.get("llm.provider", "default_provider") == "default_provider"
    
    def test_reload_config(self, temp_config_file, monkeypatch):
        """Should reload config from file."""
        monkeypatch.setenv("CLAWLITE_CONFIG", temp_config_file)
        
        from src import config
        config._config = None
        config.load_config()
        
        # Modify the file
        with open(temp_config_file) as f:
            data = yaml.safe_load(f)
        data["llm"]["model"] = "new-model"
        with open(temp_config_file, "w") as f:
            yaml.dump(data, f)
        
        # Reload
        config.reload_config()
        
        assert config.get("llm.model") == "new-model"
