"""
Unit tests for fastapi_app/crud.py
Tests CRUD operations with mocked MongoDB.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'fastapi_app'))


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database with mock collection."""
    db = MagicMock()
    collection = MagicMock()
    db.__getitem__ = MagicMock(return_value=collection)
    return db, collection


@pytest.fixture
def sample_entry():
    """Sample CodeEntry-like object for testing."""
    class MockEntry:
        def model_dump(self, by_alias=False, exclude=None):
            data = {
                "_id": "507f1f77bcf86cd799439011",
                "code_original": "int main() {}",
                "code_fixed": "int main() { return 0; }",
                "code_hash": "a" * 64,
                "repo": {
                    "url": "https://github.com/test/repo",
                    "commit_hash": "abc123",
                    "commit_date": "2024-01-15T10:30:00",
                },
                "ingest_timestamp": "2024-01-15T10:30:00",
                "labels": {
                    "cppcheck": ["nullPointer"],
                    "clang": {},
                    "groups": {"memory_management": True},
                },
            }
            if exclude and "id" in exclude:
                data.pop("_id", None)
            return data
    return MockEntry()


# ============================================================================
# Test create_entry
# ============================================================================

class TestCreateEntry:
    """Tests for create_entry function."""

    @pytest.mark.asyncio
    async def test_create_entry_success(self, mock_db, sample_entry):
        """Test successful entry creation."""
        db, collection = mock_db
        mock_result = MagicMock()
        mock_result.inserted_id = ObjectId("507f1f77bcf86cd799439011")
        collection.insert_one = AsyncMock(return_value=mock_result)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.create_entry(db, sample_entry)

        assert result == "507f1f77bcf86cd799439011"
        collection.insert_one.assert_called_once()


# ============================================================================
# Test get_entry
# ============================================================================

class TestGetEntry:
    """Tests for get_entry function."""

    @pytest.mark.asyncio
    async def test_get_entry_success(self, mock_db, sample_code_entry_dict):
        """Test successful entry retrieval."""
        db, collection = mock_db
        collection.find_one = AsyncMock(return_value=sample_code_entry_dict)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.get_entry(db, "507f1f77bcf86cd799439011")

        assert result is not None
        collection.find_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_entry_not_found(self, mock_db):
        """Test entry not found returns None."""
        db, collection = mock_db
        collection.find_one = AsyncMock(return_value=None)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.get_entry(db, "507f1f77bcf86cd799439011")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_entry_invalid_id(self, mock_db):
        """Test invalid ObjectId returns None."""
        db, collection = mock_db

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.get_entry(db, "invalid_id")

        assert result is None
        collection.find_one.assert_not_called()


# ============================================================================
# Test update_entry
# ============================================================================

class TestUpdateEntry:
    """Tests for update_entry function."""

    @pytest.mark.asyncio
    async def test_update_entry_success(self, mock_db):
        """Test successful entry update."""
        db, collection = mock_db
        mock_result = MagicMock()
        mock_result.modified_count = 1
        collection.update_one = AsyncMock(return_value=mock_result)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.update_entry(db, "507f1f77bcf86cd799439011", {"code_fixed": "new code"})

        assert result == 1
        collection.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_entry_not_found(self, mock_db):
        """Test update on non-existent entry."""
        db, collection = mock_db
        mock_result = MagicMock()
        mock_result.modified_count = 0
        collection.update_one = AsyncMock(return_value=mock_result)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.update_entry(db, "507f1f77bcf86cd799439011", {"code_fixed": "new"})

        assert result == 0

    @pytest.mark.asyncio
    async def test_update_entry_invalid_id(self, mock_db):
        """Test update with invalid ObjectId."""
        db, collection = mock_db

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.update_entry(db, "invalid", {"code_fixed": "new"})

        assert result == 0


# ============================================================================
# Test delete_entry
# ============================================================================

class TestDeleteEntry:
    """Tests for delete_entry function."""

    @pytest.mark.asyncio
    async def test_delete_entry_success(self, mock_db):
        """Test successful entry deletion."""
        db, collection = mock_db
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        collection.delete_one = AsyncMock(return_value=mock_result)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.delete_entry(db, "507f1f77bcf86cd799439011")

        assert result == 1

    @pytest.mark.asyncio
    async def test_delete_entry_not_found(self, mock_db):
        """Test delete on non-existent entry."""
        db, collection = mock_db
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        collection.delete_one = AsyncMock(return_value=mock_result)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.delete_entry(db, "507f1f77bcf86cd799439011")

        assert result == 0

    @pytest.mark.asyncio
    async def test_delete_entry_invalid_id(self, mock_db):
        """Test delete with invalid ObjectId."""
        db, collection = mock_db

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.delete_entry(db, "invalid")

        assert result == 0


# ============================================================================
# Test list_entries
# ============================================================================

class TestListEntries:
    """Tests for list_entries function."""

    @pytest.mark.asyncio
    async def test_list_entries_empty(self, mock_db):
        """Test listing with no entries."""
        db, collection = mock_db
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        collection.find = MagicMock(return_value=mock_cursor)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.list_entries(db)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_entries_with_results(self, mock_db, sample_code_entry_dict):
        """Test listing with results."""
        db, collection = mock_db
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[sample_code_entry_dict])
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        collection.find = MagicMock(return_value=mock_cursor)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.list_entries(db)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_entries_with_filter(self, mock_db, sample_code_entry_dict):
        """Test listing with filter."""
        db, collection = mock_db
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[sample_code_entry_dict])
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        collection.find = MagicMock(return_value=mock_cursor)

        filter_dict = {"labels.groups.memory_management": True}

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.list_entries(db, filter_dict=filter_dict)

        collection.find.assert_called_once_with(filter_dict)

    @pytest.mark.asyncio
    async def test_list_entries_invalid_id_filter(self, mock_db):
        """Test listing with invalid _id filter returns empty."""
        db, collection = mock_db

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.list_entries(db, filter_dict={"_id": "invalid"})

        assert result == []


# ============================================================================
# Test cppcheck label functions
# ============================================================================

class TestCppcheckLabelFunctions:
    """Tests for add_to_cppcheck_labels and remove_from_cppcheck_labels."""

    @pytest.mark.asyncio
    async def test_add_to_cppcheck_labels_success(self, mock_db):
        """Test adding labels to cppcheck array."""
        db, collection = mock_db
        mock_result = MagicMock()
        mock_result.modified_count = 1
        collection.update_one = AsyncMock(return_value=mock_result)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.add_to_cppcheck_labels(
                db, "507f1f77bcf86cd799439011", ["newLabel"]
            )

        assert result == 1

    @pytest.mark.asyncio
    async def test_add_to_cppcheck_labels_invalid_id(self, mock_db):
        """Test adding labels with invalid id."""
        db, collection = mock_db

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.add_to_cppcheck_labels(db, "invalid", ["label"])

        assert result == 0

    @pytest.mark.asyncio
    async def test_remove_from_cppcheck_labels_success(self, mock_db):
        """Test removing labels from cppcheck array."""
        db, collection = mock_db
        mock_result = MagicMock()
        mock_result.modified_count = 1
        collection.update_one = AsyncMock(return_value=mock_result)

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.remove_from_cppcheck_labels(
                db, "507f1f77bcf86cd799439011", ["oldLabel"]
            )

        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_from_cppcheck_labels_invalid_id(self, mock_db):
        """Test removing labels with invalid id."""
        db, collection = mock_db

        with patch.dict(sys.modules, {'models': MagicMock()}):
            import crud
            result = await crud.remove_from_cppcheck_labels(db, "invalid", ["label"])

        assert result == 0
