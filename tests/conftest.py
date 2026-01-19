"""
Pytest configuration and shared fixtures for all test modules.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_code_entry_dict():
    """A sample CodeEntry as a dictionary."""
    return {
        "_id": "507f1f77bcf86cd799439011",
        "code_original": 'int main() { int *p; delete p; return 0; }',
        "code_fixed": 'int main() { int *p = nullptr; if(p) delete p; return 0; }',
        "code_hash": "a" * 64,
        "repo": {
            "url": "https://github.com/test/repo",
            "commit_hash": "abc123def456",
            "commit_date": "2024-01-15T10:30:00",
        },
        "ingest_timestamp": "2024-01-15T10:30:00",
        "labels": {
            "cppcheck": ["nullPointer", "memleak"],
            "clang": {},
            "groups": {
                "memory_management": True,
                "invalid_access": False,
                "uninitialized": False,
                "concurrency": False,
                "logic_error": False,
                "resource_leak": True,
                "security_portability": False,
                "code_quality_performance": False,
            },
        },
    }


@pytest.fixture
def sample_repo_info():
    """Sample RepoInfo dictionary."""
    return {
        "url": "https://github.com/test/repo",
        "commit_hash": "abc123def456",
        "commit_date": datetime(2024, 1, 15, 10, 30, 0),
    }


@pytest.fixture
def sample_labels_groups():
    """Sample LabelsGroup dictionary."""
    return {
        "memory_management": True,
        "invalid_access": False,
        "uninitialized": False,
        "concurrency": False,
        "logic_error": False,
        "resource_leak": True,
        "security_portability": False,
        "code_quality_performance": False,
    }


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_mongodb():
    """Mock AsyncIOMotorDatabase for MongoDB operations."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    
    # Setup common async methods
    mock_collection.insert_one = AsyncMock()
    mock_collection.find_one = AsyncMock()
    mock_collection.update_one = AsyncMock()
    mock_collection.delete_one = AsyncMock()
    mock_collection.find = MagicMock()
    
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    
    return mock_db


@pytest.fixture
def mock_socket():
    """Mock socket for network operations."""
    mock_sock = MagicMock()
    mock_sock.connect = MagicMock()
    mock_sock.sendall = MagicMock()
    mock_sock.recv = MagicMock()
    mock_sock.settimeout = MagicMock()
    mock_sock.close = MagicMock()
    return mock_sock
