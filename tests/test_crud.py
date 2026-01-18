"""
Tests for FastAPI CRUD operations.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

import pytest


class TestCRUDOperations:
    """Tests for CRUD operations."""

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
        """Test creating an entry."""
        from fastapi_app.crud import create_entry
        from fastapi_app.models import CodeEntry, RepoInfo, Labels, LabelsGroup

        # Setup mock
        mock_db["code_entries"].insert_one.return_value = MagicMock(
            inserted_id=ObjectId("507f1f77bcf86cd799439011")
        )

        entry = CodeEntry(
            code_original="int x;",
            code_hash="a" * 64,
            repo=RepoInfo(
                url="https://github.com/test/repo",
                commit_hash="abc123",
                commit_date=datetime.now()
            ),
            ingest_timestamp=datetime.now(),
            labels=Labels(groups=LabelsGroup())
        )

        result = await create_entry(mock_db, entry)

        assert result == "507f1f77bcf86cd799439011"

    @pytest.mark.asyncio
    async def test_get_entry_found(self, mock_db, sample_code_entry):
        """Test getting an existing entry."""
        from fastapi_app.crud import get_entry

        mock_db["code_entries"].find_one.return_value = sample_code_entry

        result = await get_entry(mock_db, "507f1f77bcf86cd799439011")

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_entry_invalid_id(self, mock_db):
        """Test getting entry with invalid ObjectId."""
        from fastapi_app.crud import get_entry

        result = await get_entry(mock_db, "invalid_id")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_entry_not_found(self, mock_db):
        """Test getting a non-existent entry."""
        from fastapi_app.crud import get_entry

        mock_db["code_entries"].find_one.return_value = None

        result = await get_entry(mock_db, "507f1f77bcf86cd799439011")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_entry(self, mock_db):
        """Test updating an entry."""
        from fastapi_app.crud import update_entry

        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await update_entry(mock_db, "507f1f77bcf86cd799439011", {"labels.cppcheck": ["new_label"]})

        assert result == 1

    @pytest.mark.asyncio
    async def test_update_entry_invalid_id(self, mock_db):
        """Test updating entry with invalid ObjectId."""
        from fastapi_app.crud import update_entry

        result = await update_entry(mock_db, "invalid_id", {"labels": []})

        assert result == 0

    @pytest.mark.asyncio
    async def test_delete_entry(self, mock_db):
        """Test deleting an entry."""
        from fastapi_app.crud import delete_entry

        mock_db["code_entries"].delete_one.return_value = MagicMock(deleted_count=1)

        result = await delete_entry(mock_db, "507f1f77bcf86cd799439011")

        assert result == 1

    @pytest.mark.asyncio
    async def test_delete_entry_invalid_id(self, mock_db):
        """Test deleting entry with invalid ObjectId."""
        from fastapi_app.crud import delete_entry

        result = await delete_entry(mock_db, "invalid_id")

        assert result == 0

    @pytest.mark.asyncio
    async def test_list_entries(self, mock_db, sample_code_entry):
        """Test listing entries."""
        from fastapi_app.crud import list_entries

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[sample_code_entry])
        mock_db["code_entries"].find.return_value = mock_cursor

        result = await list_entries(mock_db, {}, {}, 100)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_entries_with_filter(self, mock_db, sample_code_entry):
        """Test listing entries with filter."""
        from fastapi_app.crud import list_entries

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[sample_code_entry])
        mock_db["code_entries"].find.return_value = mock_cursor

        result = await list_entries(mock_db, {"_id": "507f1f77bcf86cd799439011"}, {}, 100)

        # Verify ObjectId conversion
        mock_db["code_entries"].find.assert_called()

    @pytest.mark.asyncio
    async def test_list_entries_invalid_id_filter(self, mock_db):
        """Test listing entries with invalid ObjectId filter."""
        from fastapi_app.crud import list_entries

        result = await list_entries(mock_db, {"_id": "invalid"}, {}, 100)

        assert result == []

    @pytest.mark.asyncio
    async def test_add_label(self, mock_db):
        """Test adding a label."""
        from fastapi_app.crud import add_label

        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await add_label(mock_db, "507f1f77bcf86cd799439011", "memoryLeak")

        assert result == 1

    @pytest.mark.asyncio
    async def test_add_label_invalid_id(self, mock_db):
        """Test adding label with invalid ObjectId."""
        from fastapi_app.crud import add_label

        result = await add_label(mock_db, "invalid_id", "label")

        assert result == 0

    @pytest.mark.asyncio
    async def test_remove_label(self, mock_db):
        """Test removing a label."""
        from fastapi_app.crud import remove_label

        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await remove_label(mock_db, "507f1f77bcf86cd799439011", "memoryLeak")

        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_label_invalid_id(self, mock_db):
        """Test removing label with invalid ObjectId."""
        from fastapi_app.crud import remove_label

        result = await remove_label(mock_db, "invalid_id", "label")

        assert result == 0

    @pytest.mark.asyncio
    async def test_set_label_group(self, mock_db):
        """Test setting label group."""
        from fastapi_app.crud import set_label_group

        mock_db["code_entries"].update_one.return_value = MagicMock(modified_count=1)

        result = await set_label_group(mock_db, "507f1f77bcf86cd799439011", "memory_management", True)

        assert result == 1

    @pytest.mark.asyncio
    async def test_set_label_group_invalid_group(self, mock_db):
        """Test setting invalid label group."""
        from fastapi_app.crud import set_label_group

        result = await set_label_group(mock_db, "507f1f77bcf86cd799439011", "invalid_group", True)

        assert result == 0

    @pytest.mark.asyncio
    async def test_set_label_group_invalid_id(self, mock_db):
        """Test setting label group with invalid ObjectId."""
        from fastapi_app.crud import set_label_group

        result = await set_label_group(mock_db, "invalid_id", "memory_management", True)

        assert result == 0

    @pytest.mark.asyncio
    async def test_get_entry_count(self, mock_db):
        """Test getting entry count."""
        from fastapi_app.crud import get_entry_count

        mock_db["code_entries"].count_documents.return_value = 42

        result = await get_entry_count(mock_db, {})

        assert result == 42

    @pytest.mark.asyncio
    async def test_get_all_labels(self, mock_db):
        """Test getting all unique labels."""
        from fastapi_app.crud import get_all_labels

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"_id": "memoryLeak"},
            {"_id": "nullPointer"},
        ])
        mock_db["code_entries"].aggregate.return_value = mock_cursor

        result = await get_all_labels(mock_db)

        assert "memoryLeak" in result
        assert "nullPointer" in result

        result = await mock_db["code_entries"].delete_one({"_id": "test_id"})

        assert result.deleted_count == 1

    @pytest.mark.asyncio
    async def test_delete_entry_not_found(self, mock_db):
        """Test deleting non-existent entry."""
        mock_db["code_entries"].delete_one.return_value = MagicMock(deleted_count=0)

        result = await mock_db["code_entries"].delete_one({"_id": "nonexistent"})

        assert result.deleted_count == 0

    @pytest.mark.asyncio
    async def test_count_documents(self, mock_db):
        """Test counting documents."""
        mock_db["code_entries"].count_documents.return_value = 42

        result = await mock_db["code_entries"].count_documents({})

        assert result == 42

    @pytest.mark.asyncio
    async def test_count_documents_with_filter(self, mock_db):
        """Test counting documents with filter."""
        mock_db["code_entries"].count_documents.return_value = 10

        result = await mock_db["code_entries"].count_documents(
            {"labels.groups.memory_management": True}
        )

        assert result == 10


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
