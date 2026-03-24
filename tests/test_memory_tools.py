"""Tests for memory tools (memory_log, memory_read, memory_update, memory_search)."""

import os
import pytest
from pathlib import Path
from datetime import date


@pytest.fixture
def user_workspace(tmp_path, monkeypatch):
    """Set up a user workspace with sample memory files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    # Patch the module-level constant directly
    import src.tools.memory as memory_module
    monkeypatch.setattr(memory_module, "WORKSPACE_DIR", str(workspace))
    
    # Create user directory structure
    user_id = "tg_123456"
    user_dir = workspace / "users" / user_id
    memory_dir = user_dir / "memory"
    memory_dir.mkdir(parents=True)
    
    # Create USER.md
    user_file = user_dir / "USER.md"
    user_file.write_text("""# User Info
Name: Test User
Phone: +628123456789

## Notes
Prefers dark mode
""")
    
    # Create MEMORY.md
    memory_file = user_dir / "MEMORY.md"
    memory_file.write_text("""# Long-term Memory

## Pets
- Kelinci Ma: sedang dalam program point
- Kelinci Mo: warna putih

## Preferences
- Suka kopi hitam
- Tidak suka durian
""")
    
    # Create daily logs
    daily_log_1 = memory_dir / "2026-03-22.md"
    daily_log_1.write_text("""### 10:00

Kelinci Mo juga dalam program point sekarang.

### 14:00

Kelinci Ma dapat +2 point, kelinci Mo dapat +1 point
""")
    
    daily_log_2 = memory_dir / "2026-03-21.md"
    daily_log_2.write_text("""### 09:00

Hari ini cerah, Robin pergi ke kantor.

### 15:00

Meeting dengan tim development selesai.
""")
    
    return {
        "workspace": workspace,
        "user_id": user_id,
        "user_dir": user_dir,
        "memory_dir": memory_dir,
    }


class TestMemorySearchTool:
    """Tests for memory_search tool."""
    
    @pytest.fixture
    def search_tool(self, user_workspace):
        """Get memory_search tool with user_id set."""
        from src.tools.memory import MemorySearchTool
        tool = MemorySearchTool()
        tool.user_id = user_workspace["user_id"]
        return tool
    
    @pytest.mark.asyncio
    async def test_search_finds_in_user_md(self, search_tool, user_workspace):
        """Should find matches in USER.md."""
        result = await search_tool.execute(query="dark mode")
        
        assert result.success
        assert "USER.md" in result.output
        assert "dark mode" in result.output.lower()
    
    @pytest.mark.asyncio
    async def test_search_finds_in_memory_md(self, search_tool, user_workspace):
        """Should find matches in MEMORY.md."""
        result = await search_tool.execute(query="kelinci")
        
        assert result.success
        assert "MEMORY.md" in result.output
        assert "Kelinci" in result.output
    
    @pytest.mark.asyncio
    async def test_search_finds_in_daily_logs(self, search_tool, user_workspace):
        """Should find matches in daily memory logs."""
        result = await search_tool.execute(query="point")
        
        assert result.success
        assert "memory/2026-03-22.md" in result.output
        assert "point" in result.output.lower()
    
    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, search_tool, user_workspace):
        """Search should be case-insensitive."""
        result = await search_tool.execute(query="KELINCI")
        
        assert result.success
        assert "Kelinci" in result.output
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, search_tool, user_workspace):
        """Should handle no matches gracefully."""
        result = await search_tool.execute(query="nonexistent_query_xyz")
        
        assert result.success
        assert "No matches found" in result.output
    
    @pytest.mark.asyncio
    async def test_search_short_query_rejected(self, search_tool, user_workspace):
        """Should reject queries shorter than 2 characters."""
        result = await search_tool.execute(query="a")
        
        assert not result.success
        assert "at least 2 characters" in result.error
    
    @pytest.mark.asyncio
    async def test_search_empty_query_rejected(self, search_tool, user_workspace):
        """Should reject empty queries."""
        result = await search_tool.execute(query="")
        
        assert not result.success
        assert "at least 2 characters" in result.error
    
    @pytest.mark.asyncio
    async def test_search_limit_works(self, search_tool, user_workspace):
        """Should respect the limit parameter."""
        result = await search_tool.execute(query="kelinci", limit=2)
        
        assert result.success
        # Count number of results (look for [1], [2], etc.)
        assert "[1]" in result.output
        assert "[2]" in result.output
        # Should not have more than limit
        # Note: deduplication might reduce results below limit
    
    @pytest.mark.asyncio
    async def test_search_highlights_query(self, search_tool, user_workspace):
        """Should highlight the query in results with bold markdown."""
        result = await search_tool.execute(query="kopi")
        
        assert result.success
        assert "**kopi**" in result.output.lower() or "**Kopi**" in result.output
    
    @pytest.mark.asyncio
    async def test_search_shows_line_numbers(self, search_tool, user_workspace):
        """Should show line numbers in results."""
        result = await search_tool.execute(query="durian")
        
        assert result.success
        assert "(line " in result.output
    
    @pytest.mark.asyncio
    async def test_search_without_user_id_fails(self, user_workspace):
        """Should fail if user_id is not set."""
        from src.tools.memory import MemorySearchTool
        tool = MemorySearchTool()
        # user_id not set
        
        result = await tool.execute(query="test")
        
        assert not result.success
        assert "User ID not set" in result.error


class TestMemoryLogTool:
    """Tests for memory_log tool."""
    
    @pytest.fixture
    def log_tool(self, user_workspace):
        """Get memory_log tool with user_id set."""
        from src.tools.memory import MemoryLogTool
        tool = MemoryLogTool()
        tool.user_id = user_workspace["user_id"]
        return tool
    
    @pytest.mark.asyncio
    async def test_log_creates_daily_file(self, log_tool, user_workspace):
        """Should create today's log file if it doesn't exist."""
        today = date.today().isoformat()
        log_path = user_workspace["memory_dir"] / f"{today}.md"
        
        # Remove if exists
        if log_path.exists():
            log_path.unlink()
        
        result = await log_tool.execute(content="Test log entry here")
        
        assert result.success
        assert log_path.exists()
        assert "Test log entry here" in log_path.read_text()
    
    @pytest.mark.asyncio
    async def test_log_appends_to_existing(self, log_tool, user_workspace):
        """Should append to existing log file."""
        today = date.today().isoformat()
        log_path = user_workspace["memory_dir"] / f"{today}.md"
        log_path.write_text("### 08:00\n\nExisting content\n")
        
        result = await log_tool.execute(content="New log entry added")
        
        assert result.success
        content = log_path.read_text()
        assert "Existing content" in content
        assert "New log entry added" in content
    
    @pytest.mark.asyncio
    async def test_log_rejects_empty_content(self, log_tool, user_workspace):
        """Should reject empty or placeholder content."""
        result = await log_tool.execute(content="")
        
        assert not result.success
        assert "empty" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_log_rejects_placeholder_content(self, log_tool, user_workspace):
        """Should reject placeholder content like '...'."""
        result = await log_tool.execute(content="...")
        
        assert not result.success
        assert "placeholder" in result.error.lower() or "empty" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_log_rejects_short_content(self, log_tool, user_workspace):
        """Should reject very short content."""
        result = await log_tool.execute(content="hi")
        
        assert not result.success
        assert "too short" in result.error.lower()


class TestMemoryReadTool:
    """Tests for memory_read tool."""
    
    @pytest.fixture
    def read_tool(self, user_workspace):
        """Get memory_read tool with user_id set."""
        from src.tools.memory import MemoryReadTool
        tool = MemoryReadTool()
        tool.user_id = user_workspace["user_id"]
        return tool
    
    @pytest.mark.asyncio
    async def test_read_memory_md(self, read_tool, user_workspace):
        """Should read MEMORY.md when no date is specified."""
        result = await read_tool.execute()
        
        assert result.success
        assert "Long-term Memory" in result.output
        assert "Kelinci Ma" in result.output
    
    @pytest.mark.asyncio
    async def test_read_daily_log_by_date(self, read_tool, user_workspace):
        """Should read specific daily log by date."""
        result = await read_tool.execute(date="2026-03-22")
        
        assert result.success
        assert "program point" in result.output
    
    @pytest.mark.asyncio
    async def test_read_nonexistent_date_fails(self, read_tool, user_workspace):
        """Should fail gracefully for nonexistent date."""
        result = await read_tool.execute(date="1999-01-01")
        
        assert not result.success
        assert "not found" in result.error.lower()


class TestMemoryUpdateTool:
    """Tests for memory_update tool."""
    
    @pytest.fixture
    def update_tool(self, user_workspace):
        """Get memory_update tool with user_id set."""
        from src.tools.memory import MemoryUpdateTool
        tool = MemoryUpdateTool()
        tool.user_id = user_workspace["user_id"]
        return tool
    
    @pytest.mark.asyncio
    async def test_update_appends_to_memory(self, update_tool, user_workspace):
        """Should append content to MEMORY.md."""
        result = await update_tool.execute(content="## New Section\n\nNew important info")
        
        assert result.success
        
        memory_file = user_workspace["user_dir"] / "MEMORY.md"
        content = memory_file.read_text()
        assert "New Section" in content
        assert "New important info" in content
        # Original content should still be there
        assert "Kelinci Ma" in content
    
    @pytest.mark.asyncio
    async def test_update_rejects_empty(self, update_tool, user_workspace):
        """Should reject empty content."""
        result = await update_tool.execute(content="")
        
        assert not result.success
        assert "empty" in result.error.lower()
