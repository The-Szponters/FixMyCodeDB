"""
Unit tests for fastapi_app/main.py endpoints.
Tests API endpoints using FastAPI TestClient with mocked database.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import sys
import os

# Add fastapi_app to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'fastapi_app'))

from fastapi.testclient import TestClient


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_crud():
    """Mock the crud module."""
    with patch('main.crud') as mock:
        yield mock


@pytest.fixture
def client():
    """Create a test client with mocked MongoDB connection."""
    with patch('main.AsyncIOMotorClient') as mock_motor:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_motor.return_value = mock_client

        from main import app
        app.mongodb_client = mock_client
        app.mongodb = mock_db

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ============================================================================
# Test Label Mapping
# ============================================================================

class TestLabelMapping:
    """Tests for LABEL_TO_GROUP_FIELD mapping."""

    def test_label_mapping_exists(self):
        """Test that label mapping is defined."""
        from main import LABEL_TO_GROUP_FIELD
        
        assert "MemError" in LABEL_TO_GROUP_FIELD
        assert "LogicError" in LABEL_TO_GROUP_FIELD
        assert LABEL_TO_GROUP_FIELD["MemError"] == "memory_management"
        assert LABEL_TO_GROUP_FIELD["LogicError"] == "logic_error"

    def test_label_mapping_bidirectional(self):
        """Test both friendly names and field names are mapped."""
        from main import LABEL_TO_GROUP_FIELD

        # Friendly names
        assert LABEL_TO_GROUP_FIELD["MemError"] == "memory_management"
        # Direct field names
        assert LABEL_TO_GROUP_FIELD["memory_management"] == "memory_management"


# ============================================================================
# Test POST /entries/
# ============================================================================

class TestCreateEndpoint:
    """Tests for POST /entries/ endpoint."""

    def test_create_entry_success(self, client, sample_code_entry_dict):
        """Test successful entry creation."""
        with patch('main.crud.create_entry', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "507f1f77bcf86cd799439011"

            # Remove _id for creation
            entry_data = sample_code_entry_dict.copy()
            entry_data.pop("_id", None)

            response = client.post("/entries/", json=entry_data)

            assert response.status_code == 201
            assert response.json() == {"id": "507f1f77bcf86cd799439011"}

    def test_create_entry_duplicate(self, client, sample_code_entry_dict):
        """Test duplicate entry returns 409."""
        from pymongo.errors import DuplicateKeyError

        with patch('main.crud.create_entry', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = DuplicateKeyError("duplicate key")

            entry_data = sample_code_entry_dict.copy()
            entry_data.pop("_id", None)

            response = client.post("/entries/", json=entry_data)

            assert response.status_code == 409

    def test_create_entry_validation_error(self, client):
        """Test invalid entry returns 422."""
        response = client.post("/entries/", json={"invalid": "data"})
        assert response.status_code == 422


# ============================================================================
# Test GET /entries/{entry_id}
# ============================================================================

class TestReadEndpoint:
    """Tests for GET /entries/{entry_id} endpoint."""

    def test_read_entry_success(self, client, sample_code_entry_dict):
        """Test successful entry retrieval."""
        from fastapi_app.models import CodeEntry

        with patch('main.crud.get_entry', new_callable=AsyncMock) as mock_get:
            mock_entry = CodeEntry(**sample_code_entry_dict)
            mock_get.return_value = mock_entry

            response = client.get("/entries/507f1f77bcf86cd799439011")

            assert response.status_code == 200
            assert response.json()["_id"] == "507f1f77bcf86cd799439011"

    def test_read_entry_not_found(self, client):
        """Test entry not found returns 404."""
        with patch('main.crud.get_entry', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            response = client.get("/entries/507f1f77bcf86cd799439011")

            assert response.status_code == 404


# ============================================================================
# Test GET /entries/
# ============================================================================

class TestGetAllEndpoint:
    """Tests for GET /entries/ endpoint."""

    def test_get_all_entries_empty(self, client):
        """Test getting all entries when empty."""
        with patch('main.crud.list_entries', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            response = client.get("/entries/")

            assert response.status_code == 200
            assert response.json() == []

    def test_get_all_entries_with_limit(self, client, sample_code_entry_dict):
        """Test getting all entries with limit."""
        from fastapi_app.models import CodeEntry

        with patch('main.crud.list_entries', new_callable=AsyncMock) as mock_list:
            mock_entry = CodeEntry(**sample_code_entry_dict)
            mock_list.return_value = [mock_entry]

            response = client.get("/entries/?limit=50")

            assert response.status_code == 200
            mock_list.assert_called_once()


# ============================================================================
# Test PUT /entries/{entry_id}
# ============================================================================

class TestUpdateEndpoint:
    """Tests for PUT /entries/{entry_id} endpoint."""

    def test_update_entry_success(self, client):
        """Test successful entry update."""
        with patch('main.crud.update_entry', new_callable=AsyncMock) as mock_update:
            mock_update.return_value = 1

            response = client.put(
                "/entries/507f1f77bcf86cd799439011",
                json={"code_fixed": "updated code"}
            )

            assert response.status_code == 200
            assert response.json() == {"updated": 1}

    def test_update_entry_not_found(self, client):
        """Test update on non-existent entry."""
        with patch('main.crud.update_entry', new_callable=AsyncMock) as mock_update:
            mock_update.return_value = 0

            response = client.put(
                "/entries/507f1f77bcf86cd799439011",
                json={"code_fixed": "updated code"}
            )

            assert response.status_code == 404


# ============================================================================
# Test DELETE /entries/{entry_id}
# ============================================================================

class TestDeleteEndpoint:
    """Tests for DELETE /entries/{entry_id} endpoint."""

    def test_delete_entry_success(self, client):
        """Test successful entry deletion."""
        with patch('main.crud.delete_entry', new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = 1

            response = client.delete("/entries/507f1f77bcf86cd799439011")

            assert response.status_code == 200
            assert response.json() == {"deleted": 1}

    def test_delete_entry_not_found(self, client):
        """Test delete on non-existent entry."""
        with patch('main.crud.delete_entry', new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = 0

            response = client.delete("/entries/507f1f77bcf86cd799439011")

            assert response.status_code == 404


# ============================================================================
# Test PATCH /entries/{entry_id}/labels
# ============================================================================

class TestUpdateLabelsEndpoint:
    """Tests for PATCH /entries/{entry_id}/labels endpoint."""

    def test_update_labels_add_group(self, client, sample_code_entry_dict):
        """Test adding a group label."""
        from fastapi_app.models import CodeEntry

        with patch('main.crud.get_entry', new_callable=AsyncMock) as mock_get, \
             patch('main.crud.update_entry', new_callable=AsyncMock) as mock_update:

            mock_entry = CodeEntry(**sample_code_entry_dict)
            mock_get.return_value = mock_entry
            mock_update.return_value = 1

            response = client.patch(
                "/entries/507f1f77bcf86cd799439011/labels",
                json={"add": ["MemError"], "remove": []}
            )

            assert response.status_code == 200

    def test_update_labels_entry_not_found(self, client):
        """Test updating labels on non-existent entry."""
        with patch('main.crud.get_entry', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            response = client.patch(
                "/entries/507f1f77bcf86cd799439011/labels",
                json={"add": ["MemError"], "remove": []}
            )

            assert response.status_code == 404

    def test_update_labels_add_cppcheck(self, client, sample_code_entry_dict):
        """Test adding a cppcheck label (not a group label)."""
        from fastapi_app.models import CodeEntry

        with patch('main.crud.get_entry', new_callable=AsyncMock) as mock_get, \
             patch('main.crud.add_to_cppcheck_labels', new_callable=AsyncMock) as mock_add:

            mock_entry = CodeEntry(**sample_code_entry_dict)
            mock_get.return_value = mock_entry
            mock_add.return_value = 1

            response = client.patch(
                "/entries/507f1f77bcf86cd799439011/labels",
                json={"add": ["customLabel"], "remove": []}
            )

            assert response.status_code == 200
            mock_add.assert_called_once()


# ============================================================================
# Test POST /entries/query/
# ============================================================================

class TestQueryEndpoint:
    """Tests for POST /entries/query/ endpoint."""

    def test_query_entries_empty_filter(self, client):
        """Test query with empty filter."""
        with patch('main.crud.list_entries', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            response = client.post("/entries/query/", json={})

            assert response.status_code == 200

    def test_query_entries_with_filter(self, client, sample_code_entry_dict):
        """Test query with filter."""
        from fastapi_app.models import CodeEntry

        with patch('main.crud.list_entries', new_callable=AsyncMock) as mock_list:
            mock_entry = CodeEntry(**sample_code_entry_dict)
            mock_list.return_value = [mock_entry]

            response = client.post(
                "/entries/query/",
                json={
                    "filter": {"labels.groups.memory_management": True},
                    "limit": 50
                }
            )

            assert response.status_code == 200
            assert len(response.json()) == 1


# ============================================================================
# Test GET /entries/export-all
# ============================================================================

class TestExportAllEndpoint:
    """Tests for GET /entries/export-all endpoint."""

    def test_export_all_empty(self, client):
        """Test export when no entries exist."""
        mock_cursor = MagicMock()

        async def async_gen():
            return
            yield  # Make it an async generator

        mock_cursor.__aiter__ = lambda self: async_gen()

        with patch.object(client.app, 'mongodb') as mock_db:
            mock_collection = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=mock_collection)

            mock_find = MagicMock(return_value=mock_cursor)
            mock_find.sort = MagicMock(return_value=mock_cursor)
            mock_collection.find = MagicMock(return_value=mock_find)

            response = client.get("/entries/export-all")

            assert response.status_code == 200
