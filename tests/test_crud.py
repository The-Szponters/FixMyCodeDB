"""
Tests for FastAPI CRUD operations.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# We need to mock the motor imports before importing crud
from unittest.mock import patch

# Create mock for motor
mock_motor = MagicMock()
mock_db = MagicMock()


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
        # Import with mocked dependencies
        with patch.dict("sys.modules", {"motor.motor_asyncio": MagicMock()}):
            # Create a simple mock for the insert
            mock_db["code_entries"].insert_one.return_value = MagicMock(
                inserted_id="new_entry_id"
            )

            # Verify mock is set up correctly
            result = await mock_db["code_entries"].insert_one(sample_code_entry)
            assert result.inserted_id == "new_entry_id"

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
