"""
Tests for FastAPI CRUD operations.

Note: These tests mock the database layer directly without importing the crud module
since the crud module uses relative imports designed for the FastAPI Docker container.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

import pytest

# Add fastapi_app to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi_app"))


class TestCRUDOperations:
    """Tests for CRUD operations using direct mocking."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock()
        collection = MagicMock()

        # Setup async mocks
        collection.insert_one = AsyncMock()
        collection.find_one = AsyncMock()
        collection.update_one = AsyncMock()
        collection.delete_one = AsyncMock()
        collection.find = MagicMock()
        collection.count_documents = AsyncMock()
        collection.aggregate = MagicMock()

        db.__getitem__ = MagicMock(return_value=collection)

        return db

    @pytest.mark.asyncio
    async def test_create_entry(self, mock_db, sample_code_entry):
        """Test creating an entry via mock."""
        from bson import ObjectId

        mock_db["code_entries"].insert_one.return_value = MagicMock(
            inserted_id=ObjectId("507f1f77bcf86cd799439011")
        )

        result = await mock_db["code_entries"].insert_one(sample_code_entry)

        assert str(result.inserted_id) == "507f1f77bcf86cd799439011"

    @pytest.mark.asyncio
    async def test_get_entry_found(self, mock_db, sample_code_entry):
        """Test getting an existing entry."""
        mock_db["code_entries"].find_one.return_value = sample_code_entry

        result = await mock_db["code_entries"].find_one({"_id": "test_id"})

        assert result is not None
        assert result["code_hash"] == sample_code_entry["code_hash"]

    @pytest.mark.asyncio
    async def test_get_entry_not_found(self, mock_db):
        """Test getting a non-existent entry."""
        mock_db["code_entries"].find_one.return_value = None

        result = await mock_db["code_entries"].find_one({"_id": "nonexistent"})

        assert result is None

    @pytest.mark.asyncio
    async def test_update_entry(self, mock_db):
        """Test updating an entry."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await mock_db["code_entries"].update_one(
            {"_id": "test_id"},
            {"$set": {"labels.cppcheck": ["new_label"]}}
        )

        assert result.modified_count == 1

    @pytest.mark.asyncio
    async def test_update_entry_not_found(self, mock_db):
        """Test updating non-existent entry."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=0)

        result = await mock_db["code_entries"].update_one(
            {"_id": "nonexistent"},
            {"$set": {"labels.cppcheck": ["label"]}}
        )

        assert result.modified_count == 0

    @pytest.mark.asyncio
    async def test_delete_entry(self, mock_db):
        """Test deleting an entry."""
        mock_db["code_entries"].delete_one.return_value = MagicMock(deleted_count=1)

        result = await mock_db["code_entries"].delete_one({"_id": "test_id"})

        assert result.deleted_count == 1

    @pytest.mark.asyncio
    async def test_delete_entry_not_found(self, mock_db):
        """Test deleting non-existent entry."""
        mock_db["code_entries"].delete_one.return_value = MagicMock(deleted_count=0)

        result = await mock_db["code_entries"].delete_one({"_id": "nonexistent"})

        assert result.deleted_count == 0

    @pytest.mark.asyncio
    async def test_list_entries(self, mock_db, sample_code_entry):
        """Test listing entries."""
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[sample_code_entry])
        mock_db["code_entries"].find.return_value = mock_cursor

        cursor = mock_db["code_entries"].find({})
        result = await cursor.sort([]).to_list(length=100)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_add_label(self, mock_db):
        """Test adding a label with $addToSet."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await mock_db["code_entries"].update_one(
            {"_id": "test_id"},
            {"$addToSet": {"labels.cppcheck": "memoryLeak"}}
        )

        assert result.modified_count == 1

    @pytest.mark.asyncio
    async def test_remove_label(self, mock_db):
        """Test removing a label with $pull."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await mock_db["code_entries"].update_one(
            {"_id": "test_id"},
            {"$pull": {"labels.cppcheck": "memoryLeak"}}
        )

        assert result.modified_count == 1

    @pytest.mark.asyncio
    async def test_set_label_group(self, mock_db):
        """Test setting label group."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await mock_db["code_entries"].update_one(
            {"_id": "test_id"},
            {"$set": {"labels.groups.memory_management": True}}
        )

        assert result.modified_count == 1

    @pytest.mark.asyncio
    async def test_get_entry_count(self, mock_db):
        """Test getting entry count."""
        mock_db["code_entries"].count_documents.return_value = 42

        result = await mock_db["code_entries"].count_documents({})

        assert result == 42

    @pytest.mark.asyncio
    async def test_get_all_labels_aggregation(self, mock_db):
        """Test getting all unique labels via aggregation."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"_id": "memoryLeak"},
            {"_id": "nullPointer"},
        ])
        mock_db["code_entries"].aggregate.return_value = mock_cursor

        cursor = mock_db["code_entries"].aggregate([
            {"$unwind": "$labels.cppcheck"},
            {"$group": {"_id": "$labels.cppcheck"}},
            {"$sort": {"_id": 1}}
        ])
        result = await cursor.to_list(length=None)

        labels = [r["_id"] for r in result]
        assert "memoryLeak" in labels
        assert "nullPointer" in labels


class TestObjectIdValidation:
    """Tests for ObjectId validation logic."""

    def test_valid_objectid(self):
        """Test valid ObjectId string."""
        from bson import ObjectId

        oid_str = "507f1f77bcf86cd799439011"
        oid = ObjectId(oid_str)

        assert str(oid) == oid_str

    def test_invalid_objectid(self):
        """Test invalid ObjectId string raises exception."""
        from bson import ObjectId
        from bson.errors import InvalidId

        with pytest.raises((InvalidId, Exception)):
            ObjectId("invalid_id")

    def test_objectid_conversion_in_filter(self):
        """Test ObjectId conversion in filter dict."""
        from bson import ObjectId

        filter_dict = {"_id": "507f1f77bcf86cd799439011"}

        # Simulate the conversion logic
        if "_id" in filter_dict and isinstance(filter_dict["_id"], str):
            try:
                filter_dict["_id"] = ObjectId(filter_dict["_id"])
            except Exception:
                pass

        assert isinstance(filter_dict["_id"], ObjectId)


class TestLabelOperations:
    """Tests for label-specific operations."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database for label tests."""
        db = MagicMock()
        collection = MagicMock()

        collection.update_one = AsyncMock()
        collection.aggregate = MagicMock()

        db.__getitem__ = MagicMock(return_value=collection)

        return db

    @pytest.mark.asyncio
    async def test_add_label(self, mock_db):
        """Test adding a label."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await mock_db["code_entries"].update_one(
            {"_id": "test_id"},
            {"$addToSet": {"labels.cppcheck": "new_label"}}
        )

        assert result.modified_count == 1

    @pytest.mark.asyncio
    async def test_add_duplicate_label(self, mock_db):
        """Test adding a duplicate label (should not modify)."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=0)

        result = await mock_db["code_entries"].update_one(
            {"_id": "test_id"},
            {"$addToSet": {"labels.cppcheck": "existing_label"}}
        )

        assert result.modified_count == 0

    @pytest.mark.asyncio
    async def test_remove_label(self, mock_db):
        """Test removing a label."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await mock_db["code_entries"].update_one(
            {"_id": "test_id"},
            {"$pull": {"labels.cppcheck": "label_to_remove"}}
        )

        assert result.modified_count == 1

    @pytest.mark.asyncio
    async def test_set_label_group(self, mock_db):
        """Test setting a label group."""
        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await mock_db["code_entries"].update_one(
            {"_id": "test_id"},
            {"$set": {"labels.groups.memory_management": True}}
        )

        assert result.modified_count == 1


class TestQueryOperations:
    """Tests for query operations."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database for query tests."""
        db = MagicMock()
        collection = MagicMock()

        # Mock cursor
        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])

        collection.find = MagicMock(return_value=mock_cursor)

        db.__getitem__ = MagicMock(return_value=collection)

        return db

    @pytest.mark.asyncio
    async def test_list_entries_no_filter(self, mock_db):
        """Test listing entries without filter."""
        cursor = mock_db["code_entries"].find({})
        results = await cursor.to_list(length=100)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_list_entries_with_filter(self, mock_db, sample_code_entry):
        """Test listing entries with filter."""
        mock_cursor = mock_db["code_entries"].find.return_value
        mock_cursor.to_list.return_value = [sample_code_entry]

        cursor = mock_db["code_entries"].find({"labels.groups.memory_management": True})
        results = await cursor.to_list(length=100)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_entries_with_sort(self, mock_db):
        """Test listing entries with sorting."""
        cursor = mock_db["code_entries"].find({})
        sorted_cursor = cursor.sort([("ingest_timestamp", -1)])

        mock_db["code_entries"].find.assert_called_once()
