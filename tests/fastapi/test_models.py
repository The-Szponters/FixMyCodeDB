"""
Unit tests for fastapi_app/models.py
Tests Pydantic model validation and serialization.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'fastapi_app'))

from models import (
    RepoInfo,
    LabelsGroup,
    Labels,
    CodeEntry,
    LabelUpdateRequest,
)


class TestRepoInfo:
    """Tests for RepoInfo model."""

    def test_valid_repo_info(self):
        """Test creating a valid RepoInfo."""
        repo = RepoInfo(
            url="https://github.com/test/repo",
            commit_hash="abc123",
            commit_date=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert repo.url == "https://github.com/test/repo"
        assert repo.commit_hash == "abc123"
        assert repo.commit_date == datetime(2024, 1, 15, 10, 30, 0)

    def test_repo_info_from_string_date(self):
        """Test RepoInfo with string date (should be parsed)."""
        repo = RepoInfo(
            url="https://github.com/test/repo",
            commit_hash="abc123",
            commit_date="2024-01-15T10:30:00",
        )
        assert isinstance(repo.commit_date, datetime)

    def test_repo_info_missing_url(self):
        """Test RepoInfo requires url."""
        with pytest.raises(ValidationError):
            RepoInfo(commit_hash="abc123", commit_date=datetime.now())


class TestLabelsGroup:
    """Tests for LabelsGroup model."""

    def test_default_values(self):
        """Test all defaults are False."""
        groups = LabelsGroup()
        assert groups.memory_management is False
        assert groups.invalid_access is False
        assert groups.uninitialized is False
        assert groups.concurrency is False
        assert groups.logic_error is False
        assert groups.resource_leak is False
        assert groups.security_portability is False
        assert groups.code_quality_performance is False

    def test_set_values(self):
        """Test setting specific flags."""
        groups = LabelsGroup(memory_management=True, logic_error=True)
        assert groups.memory_management is True
        assert groups.logic_error is True
        assert groups.invalid_access is False


class TestLabels:
    """Tests for Labels model."""

    def test_labels_with_groups(self):
        """Test Labels with groups."""
        labels = Labels(
            cppcheck=["nullPointer", "memleak"],
            groups=LabelsGroup(memory_management=True),
        )
        assert labels.cppcheck == ["nullPointer", "memleak"]
        assert labels.groups.memory_management is True
        assert labels.clang == {}

    def test_labels_default_cppcheck(self):
        """Test default empty cppcheck list."""
        labels = Labels(groups=LabelsGroup())
        assert labels.cppcheck == []

    def test_labels_requires_groups(self):
        """Test Labels requires groups field."""
        with pytest.raises(ValidationError):
            Labels(cppcheck=["test"])


class TestCodeEntry:
    """Tests for CodeEntry model."""

    def test_valid_code_entry(self, sample_code_entry_dict):
        """Test creating a valid CodeEntry."""
        entry = CodeEntry(**sample_code_entry_dict)
        assert entry.code_original == sample_code_entry_dict["code_original"]
        assert entry.code_hash == sample_code_entry_dict["code_hash"]
        assert entry.repo.url == "https://github.com/test/repo"
        assert entry.labels.groups.memory_management is True

    def test_code_entry_invalid_hash(self):
        """Test CodeEntry rejects invalid code_hash format."""
        with pytest.raises(ValidationError) as exc_info:
            CodeEntry(
                code_original="int main() {}",
                code_hash="not_a_valid_hash",  # Not 64 hex chars
                repo=RepoInfo(
                    url="https://github.com/test",
                    commit_hash="abc",
                    commit_date=datetime.now(),
                ),
                ingest_timestamp=datetime.now(),
                labels=Labels(groups=LabelsGroup()),
            )
        assert "code_hash" in str(exc_info.value)

    def test_code_entry_id_alias(self, sample_code_entry_dict):
        """Test _id alias works correctly."""
        entry = CodeEntry(**sample_code_entry_dict)
        assert entry.id == "507f1f77bcf86cd799439011"

    def test_code_entry_optional_id(self):
        """Test CodeEntry works without _id."""
        entry = CodeEntry(
            code_original="int main() {}",
            code_hash="a" * 64,
            repo=RepoInfo(
                url="https://github.com/test",
                commit_hash="abc",
                commit_date=datetime.now(),
            ),
            ingest_timestamp=datetime.now(),
            labels=Labels(groups=LabelsGroup()),
        )
        assert entry.id is None

    def test_code_entry_optional_code_fixed(self):
        """Test code_fixed is optional."""
        entry = CodeEntry(
            code_original="int main() {}",
            code_hash="a" * 64,
            repo=RepoInfo(
                url="https://github.com/test",
                commit_hash="abc",
                commit_date=datetime.now(),
            ),
            ingest_timestamp=datetime.now(),
            labels=Labels(groups=LabelsGroup()),
        )
        assert entry.code_fixed is None


class TestLabelUpdateRequest:
    """Tests for LabelUpdateRequest model."""

    def test_add_labels_only(self):
        """Test request with only add labels."""
        req = LabelUpdateRequest(add=["MemError", "LogicError"])
        assert req.add == ["MemError", "LogicError"]
        assert req.remove == []

    def test_remove_labels_only(self):
        """Test request with only remove labels."""
        req = LabelUpdateRequest(remove=["Concurrency"])
        assert req.add == []
        assert req.remove == ["Concurrency"]

    def test_both_add_and_remove(self):
        """Test request with both add and remove."""
        req = LabelUpdateRequest(add=["MemError"], remove=["LogicError"])
        assert req.add == ["MemError"]
        assert req.remove == ["LogicError"]

    def test_empty_request(self):
        """Test empty request (valid but does nothing)."""
        req = LabelUpdateRequest()
        assert req.add == []
        assert req.remove == []
