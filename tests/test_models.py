"""
Tests for fastapi_app/models.py module.
"""

import pytest
from datetime import datetime


class TestRepoInfo:
    """Tests for RepoInfo model."""

    def test_repo_info_creation(self):
        """Test creating RepoInfo."""
        from fastapi_app.models import RepoInfo

        repo = RepoInfo(
            url="https://github.com/test/repo",
            commit_hash="abc123def456",
            commit_date=datetime(2024, 1, 15, 10, 30, 0)
        )

        assert repo.url == "https://github.com/test/repo"
        assert repo.commit_hash == "abc123def456"
        assert repo.commit_date == datetime(2024, 1, 15, 10, 30, 0)


class TestLabelsGroup:
    """Tests for LabelsGroup model."""

    def test_labels_group_defaults(self):
        """Test LabelsGroup default values."""
        from fastapi_app.models import LabelsGroup

        groups = LabelsGroup()

        assert groups.memory_management is False
        assert groups.invalid_access is False
        assert groups.uninitialized is False
        assert groups.concurrency is False
        assert groups.logic_error is False
        assert groups.resource_leak is False
        assert groups.security_portability is False
        assert groups.code_quality_performance is False

    def test_labels_group_with_values(self):
        """Test LabelsGroup with custom values."""
        from fastapi_app.models import LabelsGroup

        groups = LabelsGroup(
            memory_management=True,
            invalid_access=True,
            logic_error=True
        )

        assert groups.memory_management is True
        assert groups.invalid_access is True
        assert groups.logic_error is True
        assert groups.uninitialized is False


class TestLabels:
    """Tests for Labels model."""

    def test_labels_creation(self):
        """Test creating Labels."""
        from fastapi_app.models import Labels, LabelsGroup

        labels = Labels(
            cppcheck=["memoryLeak", "nullPointer"],
            groups=LabelsGroup(memory_management=True)
        )

        assert labels.cppcheck == ["memoryLeak", "nullPointer"]
        assert labels.groups.memory_management is True

    def test_labels_empty_cppcheck(self):
        """Test Labels with empty cppcheck list."""
        from fastapi_app.models import Labels, LabelsGroup

        labels = Labels(groups=LabelsGroup())

        assert labels.cppcheck == []


class TestCodeEntry:
    """Tests for CodeEntry model."""

    def test_code_entry_creation(self):
        """Test creating CodeEntry."""
        from fastapi_app.models import CodeEntry, RepoInfo, Labels, LabelsGroup

        entry = CodeEntry(
            code_original="int main() { return 0; }",
            code_fixed="int main() { return 0; }",
            code_hash="a" * 64,
            repo=RepoInfo(
                url="https://github.com/test/repo",
                commit_hash="abc123",
                commit_date=datetime.now()
            ),
            ingest_timestamp=datetime.now(),
            labels=Labels(groups=LabelsGroup())
        )

        assert entry.code_original == "int main() { return 0; }"
        assert len(entry.code_hash) == 64

    def test_code_entry_with_id(self):
        """Test CodeEntry with ID."""
        from fastapi_app.models import CodeEntry, RepoInfo, Labels, LabelsGroup

        entry = CodeEntry(
            _id="507f1f77bcf86cd799439011",
            code_original="code",
            code_hash="b" * 64,
            repo=RepoInfo(
                url="https://github.com/test/repo",
                commit_hash="abc123",
                commit_date=datetime.now()
            ),
            ingest_timestamp=datetime.now(),
            labels=Labels(groups=LabelsGroup())
        )

        assert entry.id == "507f1f77bcf86cd799439011"

    def test_code_entry_invalid_hash(self):
        """Test CodeEntry rejects invalid hash."""
        from fastapi_app.models import CodeEntry, RepoInfo, Labels, LabelsGroup
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CodeEntry(
                code_original="code",
                code_hash="invalid",  # Not 64 hex characters
                repo=RepoInfo(
                    url="https://github.com/test/repo",
                    commit_hash="abc123",
                    commit_date=datetime.now()
                ),
                ingest_timestamp=datetime.now(),
                labels=Labels(groups=LabelsGroup())
            )
