"""Pytest configuration and shared fixtures."""

import os
import sys
import tempfile
import shutil
import pytest

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test workspace before importing modules
TEST_WORKSPACE = tempfile.mkdtemp(prefix="clawlite_test_")
os.environ["WORKSPACE_PATH"] = TEST_WORKSPACE


@pytest.fixture(scope="session", autouse=True)
def setup_test_workspace():
    """Create and cleanup test workspace."""
    os.makedirs(TEST_WORKSPACE, exist_ok=True)
    yield TEST_WORKSPACE
    # Cleanup after all tests
    shutil.rmtree(TEST_WORKSPACE, ignore_errors=True)


@pytest.fixture
def workspace(setup_test_workspace):
    """Provide test workspace path."""
    return setup_test_workspace


@pytest.fixture
def sample_file(workspace):
    """Create a sample file in workspace."""
    filepath = os.path.join(workspace, "sample.md")
    content = """# Sample File

This is line 1.
This is line 2.
This is line 3.

## Section

Some more content here.
"""
    with open(filepath, "w") as f:
        f.write(content)
    yield filepath
    # Cleanup
    if os.path.exists(filepath):
        os.remove(filepath)


@pytest.fixture
def admin_user_id():
    """Return a mock admin user ID."""
    return "tg_admin_123"


@pytest.fixture
def regular_user_id():
    """Return a mock regular user ID."""
    return "tg_user_456"


@pytest.fixture(autouse=True)
def mock_access_control(monkeypatch, admin_user_id):
    """Mock access control for tests."""
    def mock_is_admin(user_id):
        return user_id == admin_user_id
    
    # Patch the access module
    try:
        from src import access
        monkeypatch.setattr(access, "is_admin", mock_is_admin)
    except ImportError:
        pass
    
    # Also patch in tools.base module
    try:
        from src.tools import base
        monkeypatch.setattr(base, "_is_admin_user", mock_is_admin)
    except (ImportError, AttributeError):
        pass
