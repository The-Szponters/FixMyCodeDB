"""
Pytest configuration and fixtures.
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_config():
    """Sample scraper configuration."""
    return {
        "tokens": ["token1", "token2"],
        "max_workers": 2,
        "repositories": [
            {
                "url": "https://github.com/test/repo1",
                "target_record_count": 5,
                "fix_regexes": ["(?i)\\bfix\\b", "(?i)\\bbug\\b"]
            },
            {
                "url": "https://github.com/test/repo2",
                "target_record_count": 10,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31"
            }
        ]
    }


@pytest.fixture
def sample_config_file(sample_config, tmp_path):
    """Create a temporary config file."""
    config_path = tmp_path / "config.json"
    with open(config_path, "w") as f:
        json.dump(sample_config, f)
    return str(config_path)


@pytest.fixture
def sample_code_entry():
    """Sample code entry for database tests."""
    return {
        "_id": "507f1f77bcf86cd799439011",
        "code_original": "int* ptr = malloc(sizeof(int));\nfree(ptr);\nfree(ptr);",
        "code_fixed": "int* ptr = malloc(sizeof(int));\nfree(ptr);\nptr = NULL;",
        "code_hash": "a" * 64,
        "repo": {
            "url": "https://github.com/test/repo",
            "commit_hash": "abc123def456",
            "commit_date": datetime.now().isoformat()
        },
        "ingest_timestamp": datetime.now().isoformat(),
        "labels": {
            "cppcheck": ["doubleFree"],
            "clang": {},
            "groups": {
                "memory_management": True,
                "invalid_access": False,
                "uninitialized": False,
                "concurrency": False,
                "logic_error": False,
                "resource_leak": False,
                "security_portability": False,
                "code_quality_performance": False
            }
        }
    }


@pytest.fixture
def mock_github():
    """Mock GitHub client."""
    mock = MagicMock()
    mock_repo = MagicMock()
    mock_repo.get_commits.return_value = []
    mock.get_repo.return_value = mock_repo
    return mock


@pytest.fixture
def mock_requests():
    """Mock requests library."""
    with patch("requests.get") as mock_get, patch("requests.post") as mock_post, patch("requests.put") as mock_put:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_get.return_value = mock_response
        mock_post.return_value = mock_response
        mock_put.return_value = mock_response

        yield {
            "get": mock_get,
            "post": mock_post,
            "put": mock_put,
            "response": mock_response
        }


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB client."""
    mock_db = MagicMock()
    mock_collection = MagicMock()

    # Mock async methods
    mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="new_id"))
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    mock_collection.find = MagicMock()
    mock_collection.count_documents = AsyncMock(return_value=0)

    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    return mock_db


@pytest.fixture
def temp_export_dir(tmp_path):
    """Create temporary export directory."""
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    return export_dir
