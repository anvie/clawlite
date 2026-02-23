"""Tests for file operation tools."""

import os
import pytest

from src.tools.file_ops import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from src.tools.base import WORKSPACE


class TestReadFileTool:
    """Tests for read_file tool."""
    
    @pytest.fixture
    def tool(self):
        return ReadFileTool()
    
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tool, sample_file, regular_user_id):
        """Should read existing file in workspace."""
        tool.user_id = regular_user_id
        result = await tool.execute(path="sample.md")
        
        assert result.success is True
        assert "# Sample File" in result.output
        assert "This is line 1." in result.output
    
    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tool, workspace, regular_user_id):
        """Should fail for nonexistent file."""
        tool.user_id = regular_user_id
        result = await tool.execute(path="nonexistent.md")
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_read_outside_workspace_blocked(self, tool, regular_user_id):
        """Regular user should be blocked from reading outside workspace."""
        tool.user_id = regular_user_id
        result = await tool.execute(path="/etc/passwd")
        
        assert result.success is False
        assert "outside workspace" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_read_outside_workspace_admin_allowed(self, tool, admin_user_id):
        """Admin user should be allowed to read outside workspace."""
        tool.user_id = admin_user_id
        # Try to read a file that definitely exists
        result = await tool.execute(path="/etc/hostname")
        
        # Should either succeed or fail for non-path reason (file not found is ok)
        # The key is it shouldn't fail with "outside workspace"
        if not result.success:
            assert "outside workspace" not in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, tool, regular_user_id):
        """Path traversal attempts should be blocked."""
        tool.user_id = regular_user_id
        result = await tool.execute(path="../../../etc/passwd")
        
        assert result.success is False
        assert "outside workspace" in result.error.lower()


class TestWriteFileTool:
    """Tests for write_file tool."""
    
    @pytest.fixture
    def tool(self):
        return WriteFileTool()
    
    @pytest.mark.asyncio
    async def test_write_new_file(self, tool, workspace, regular_user_id):
        """Should create new file in workspace."""
        tool.user_id = regular_user_id
        content = "Hello, World!"
        result = await tool.execute(path="new_file.txt", content=content)
        
        assert result.success is True
        
        # Verify file was created
        filepath = os.path.join(workspace, "new_file.txt")
        assert os.path.exists(filepath)
        with open(filepath) as f:
            assert f.read() == content
        
        # Cleanup
        os.remove(filepath)
    
    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tool, workspace, regular_user_id):
        """Should create parent directories if needed."""
        tool.user_id = regular_user_id
        result = await tool.execute(
            path="nested/dir/file.txt",
            content="nested content"
        )
        
        assert result.success is True
        
        filepath = os.path.join(workspace, "nested/dir/file.txt")
        assert os.path.exists(filepath)
        
        # Cleanup
        import shutil
        shutil.rmtree(os.path.join(workspace, "nested"))
    
    @pytest.mark.asyncio
    async def test_write_outside_workspace_blocked(self, tool, regular_user_id):
        """Regular user should be blocked from writing outside workspace."""
        tool.user_id = regular_user_id
        result = await tool.execute(path="/tmp/clawlite_test.txt", content="test")
        
        assert result.success is False
        assert "outside workspace" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_write_outside_workspace_admin_allowed(self, tool, admin_user_id):
        """Admin user should be allowed to write outside workspace."""
        tool.user_id = admin_user_id
        filepath = "/tmp/clawlite_admin_test.txt"
        result = await tool.execute(path=filepath, content="admin test")
        
        assert result.success is True
        assert os.path.exists(filepath)
        
        # Cleanup
        os.remove(filepath)


class TestEditFileTool:
    """Tests for edit_file tool."""
    
    @pytest.fixture
    def tool(self):
        return EditFileTool()
    
    @pytest.mark.asyncio
    async def test_search_replace(self, tool, sample_file, workspace, regular_user_id):
        """Should replace text in file."""
        tool.user_id = regular_user_id
        result = await tool.execute(
            path="sample.md",
            old_text="This is line 1.",
            new_text="This is the FIRST line."
        )
        
        assert result.success is True
        assert "Replaced" in result.output
        
        # Verify change
        with open(sample_file) as f:
            content = f.read()
        assert "This is the FIRST line." in content
        assert "This is line 1." not in content
    
    @pytest.mark.asyncio
    async def test_search_replace_not_found(self, tool, sample_file, regular_user_id):
        """Should fail if old_text not found."""
        tool.user_id = regular_user_id
        result = await tool.execute(
            path="sample.md",
            old_text="This text does not exist",
            new_text="replacement"
        )
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_search_replace_multiple_matches(self, tool, workspace, regular_user_id):
        """Should fail if old_text matches multiple times."""
        # Create file with repeated text
        filepath = os.path.join(workspace, "repeated.md")
        with open(filepath, "w") as f:
            f.write("foo bar foo baz foo")
        
        tool.user_id = regular_user_id
        result = await tool.execute(
            path="repeated.md",
            old_text="foo",
            new_text="FOO"
        )
        
        assert result.success is False
        assert "found 3 times" in result.error.lower()
        
        # Cleanup
        os.remove(filepath)
    
    @pytest.mark.asyncio
    async def test_append(self, tool, sample_file, regular_user_id):
        """Should append content to file."""
        tool.user_id = regular_user_id
        result = await tool.execute(
            path="sample.md",
            content="\n## Appended Section\n",
            append=True
        )
        
        assert result.success is True
        assert "Appended" in result.output
        
        with open(sample_file) as f:
            content = f.read()
        assert "## Appended Section" in content
        assert content.endswith("## Appended Section\n")
    
    @pytest.mark.asyncio
    async def test_prepend(self, tool, sample_file, regular_user_id):
        """Should prepend content to file."""
        tool.user_id = regular_user_id
        result = await tool.execute(
            path="sample.md",
            content="# Header\n\n",
            prepend=True
        )
        
        assert result.success is True
        assert "Prepended" in result.output
        
        with open(sample_file) as f:
            content = f.read()
        assert content.startswith("# Header\n\n")
    
    @pytest.mark.asyncio
    async def test_delete_text(self, tool, sample_file, regular_user_id):
        """Should delete text when new_text is empty."""
        tool.user_id = regular_user_id
        result = await tool.execute(
            path="sample.md",
            old_text="This is line 2.\n",
            new_text=""
        )
        
        assert result.success is True
        # Delete is implemented as replace with empty string
        assert "Replaced" in result.output or "Deleted" in result.output
        
        with open(sample_file) as f:
            content = f.read()
        assert "This is line 2." not in content
    
    @pytest.mark.asyncio
    async def test_edit_outside_workspace_blocked(self, tool, regular_user_id):
        """Regular user should be blocked from editing outside workspace."""
        tool.user_id = regular_user_id
        result = await tool.execute(
            path="/etc/hostname",
            old_text="test",
            new_text="TEST"
        )
        
        assert result.success is False
        assert "outside workspace" in result.error.lower()


class TestListDirTool:
    """Tests for list_dir tool."""
    
    @pytest.fixture
    def tool(self):
        return ListDirTool()
    
    @pytest.mark.asyncio
    async def test_list_workspace(self, tool, sample_file, regular_user_id):
        """Should list workspace contents."""
        tool.user_id = regular_user_id
        result = await tool.execute(path=".")
        
        assert result.success is True
        assert "sample.md" in result.output
    
    @pytest.mark.asyncio
    async def test_list_nonexistent_dir(self, tool, regular_user_id):
        """Should fail for nonexistent directory."""
        tool.user_id = regular_user_id
        result = await tool.execute(path="nonexistent_dir")
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_list_outside_workspace_blocked(self, tool, regular_user_id):
        """Regular user should be blocked from listing outside workspace."""
        tool.user_id = regular_user_id
        result = await tool.execute(path="/etc")
        
        assert result.success is False
        assert "outside workspace" in result.error.lower()


class TestPathValidation:
    """Tests for path validation security."""
    
    def test_relative_path_resolved_to_workspace(self, regular_user_id):
        """Relative paths should resolve within workspace."""
        from src.tools.base import Tool, WORKSPACE
        
        class DummyTool(Tool):
            name = "dummy"
            async def execute(self, **kwargs):
                pass
        
        tool = DummyTool()
        tool.user_id = regular_user_id
        
        resolved = tool.validate_path("subdir/file.txt")
        assert resolved.startswith(os.path.realpath(WORKSPACE))
    
    def test_absolute_workspace_path_allowed(self, workspace, regular_user_id):
        """Absolute paths within workspace should be allowed."""
        from src.tools.base import Tool
        
        class DummyTool(Tool):
            name = "dummy"
            async def execute(self, **kwargs):
                pass
        
        tool = DummyTool()
        tool.user_id = regular_user_id
        
        abs_path = os.path.join(workspace, "file.txt")
        resolved = tool.validate_path(abs_path)
        assert resolved == os.path.realpath(abs_path)
    
    def test_symlink_escape_blocked(self, workspace, regular_user_id):
        """Symlinks that escape workspace should be blocked."""
        from src.tools.base import Tool
        
        # Create symlink pointing outside workspace
        symlink_path = os.path.join(workspace, "escape_link")
        try:
            os.symlink("/etc", symlink_path)
        except OSError:
            pytest.skip("Cannot create symlinks")
        
        class DummyTool(Tool):
            name = "dummy"
            async def execute(self, **kwargs):
                pass
        
        tool = DummyTool()
        tool.user_id = regular_user_id
        
        with pytest.raises(ValueError, match="outside workspace"):
            tool.validate_path("escape_link/passwd")
        
        # Cleanup
        os.remove(symlink_path)
    
    def test_admin_bypasses_workspace_restriction(self, admin_user_id):
        """Admin users should bypass workspace restriction."""
        from src.tools.base import Tool
        
        class DummyTool(Tool):
            name = "dummy"
            async def execute(self, **kwargs):
                pass
        
        tool = DummyTool()
        tool.user_id = admin_user_id
        
        # Should not raise
        resolved = tool.validate_path("/etc/hostname")
        assert resolved == "/etc/hostname"
