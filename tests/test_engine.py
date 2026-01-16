"""
Tests for scraper engine module.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from scraper.core.engine import (
    calculate_hash,
    get_repo_slug,
    format_context,
    find_corresponding_file,
)


class TestCalculateHash:
    """Tests for calculate_hash function."""

    def test_hash_consistency(self):
        """Test that same input produces same hash."""
        text = "test string"

        hash1 = calculate_hash(text)
        hash2 = calculate_hash(text)

        assert hash1 == hash2

    def test_hash_different_inputs(self):
        """Test that different inputs produce different hashes."""
        hash1 = calculate_hash("text1")
        hash2 = calculate_hash("text2")

        assert hash1 != hash2

    def test_hash_format(self):
        """Test hash is valid SHA256 format."""
        result = calculate_hash("test")

        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_empty_string(self):
        """Test hashing empty string."""
        result = calculate_hash("")

        assert len(result) == 64

    def test_hash_unicode(self):
        """Test hashing unicode strings."""
        result = calculate_hash("こんにちは")

        assert len(result) == 64


class TestGetRepoSlug:
    """Tests for get_repo_slug function."""

    def test_standard_url(self):
        """Test standard GitHub URL."""
        result = get_repo_slug("https://github.com/owner/repo")

        assert result == "owner/repo"

    def test_url_with_git_suffix(self):
        """Test URL with .git suffix."""
        result = get_repo_slug("https://github.com/owner/repo.git")

        assert result == "owner/repo"

    def test_url_with_path(self):
        """Test URL with additional path."""
        result = get_repo_slug("https://github.com/owner/repo/tree/main")

        assert result == "owner/repo"

    def test_invalid_url(self):
        """Test invalid URL raises ValueError."""
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            get_repo_slug("https://gitlab.com/owner/repo")

    def test_malformed_url(self):
        """Test malformed URL raises ValueError."""
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            get_repo_slug("not-a-url")


class TestFormatContext:
    """Tests for format_context function."""

    def test_header_and_implementation(self):
        """Test combining header and implementation."""
        header = "#include <iostream>\nclass Foo {};"
        impl = "void Foo::bar() {}"

        result = format_context(header, impl)

        assert "#include <iostream>" in result
        assert "void Foo::bar()" in result

    def test_header_only(self):
        """Test with only header."""
        header = "#include <iostream>"
        impl = ""

        result = format_context(header, impl)

        assert result == "#include <iostream>"

    def test_implementation_only(self):
        """Test with only implementation."""
        header = ""
        impl = "void foo() {}"

        result = format_context(header, impl)

        assert result == "void foo() {}"

    def test_both_empty(self):
        """Test with both empty."""
        result = format_context("", "")

        assert result == ""

    def test_whitespace_trimming(self):
        """Test that whitespace is trimmed."""
        header = "  header  \n\n"
        impl = "\nimpl\n  "

        result = format_context(header, impl)

        assert result == "header\nimpl"


class TestFindCorrespondingFile:
    """Tests for find_corresponding_file function."""

    def test_find_cpp_for_header(self):
        """Test finding .cpp file for .h header."""
        base_file = "src/utils/helper.h"
        all_files = ["src/utils/helper.cpp", "src/main.cpp", "include/other.h"]

        result = find_corresponding_file(base_file, [".cpp", ".cxx", ".cc"], all_files)

        assert result == "src/utils/helper.cpp"

    def test_find_header_for_cpp(self):
        """Test finding .h header for .cpp file."""
        base_file = "src/main.cpp"
        all_files = ["src/main.h", "src/main.cpp", "include/other.h"]

        result = find_corresponding_file(base_file, [".h", ".hpp"], all_files)

        assert result == "src/main.h"

    def test_no_corresponding_file(self):
        """Test when no corresponding file exists."""
        base_file = "src/unique.cpp"
        all_files = ["src/unique.cpp", "src/other.h"]

        result = find_corresponding_file(base_file, [".h", ".hpp"], all_files)

        assert result is None

    def test_find_in_different_directory(self):
        """Test finding file in different directory."""
        base_file = "src/impl/module.cpp"
        all_files = ["include/module.h", "src/impl/module.cpp"]

        result = find_corresponding_file(base_file, [".h", ".hpp"], all_files)

        assert result == "include/module.h"

    def test_multiple_extensions_priority(self):
        """Test that first matching extension is preferred."""
        base_file = "src/file.h"
        all_files = ["src/file.cpp", "src/file.cxx", "src/file.h"]

        result = find_corresponding_file(base_file, [".cpp", ".cxx", ".cc"], all_files)

        assert result == "src/file.cpp"


class TestProcessRepository:
    """Tests for process_repository function."""

    @pytest.fixture
    def mock_github_repo(self):
        """Create mock GitHub repository."""
        mock_repo = MagicMock()
        mock_repo.get_commits.return_value = []
        return mock_repo

    @pytest.fixture
    def mock_repo_config(self):
        """Create mock repository config."""
        from scraper.config.scraper_config import RepoConfig
        return RepoConfig(
            url="https://github.com/test/repo",
            target_record_count=5,
            fix_regexes=["(?i)\\bfix\\b"]
        )

    @patch("scraper.core.engine.Labeler")
    def test_process_empty_commits(self, mock_labeler, mock_github_repo, mock_repo_config):
        """Test processing repository with no commits."""
        from scraper.core.engine import process_repository

        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_github_repo

        # Should not raise
        process_repository(mock_github, mock_repo_config)


class TestPayloadOperations:
    """Tests for payload save/insert operations."""

    @patch("scraper.core.engine.requests")
    def test_insert_payload_success(self, mock_requests):
        """Test successful payload insertion."""
        from scraper.core.engine import insert_payload_to_db

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "new_id"}
        mock_requests.post.return_value = mock_response

        payload = {"code_hash": "test_hash"}
        result = insert_payload_to_db(payload)

        assert result == "new_id"

    @patch("scraper.core.engine.requests")
    def test_insert_payload_duplicate(self, mock_requests):
        """Test payload insertion with duplicate."""
        from scraper.core.engine import insert_payload_to_db

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_requests.post.return_value = mock_response

        result = insert_payload_to_db({"code_hash": "existing_hash"})

        assert result is None

    @patch("scraper.core.engine.requests")
    def test_insert_payload_error(self, mock_requests):
        """Test payload insertion with error."""
        from scraper.core.engine import insert_payload_to_db

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_requests.post.return_value = mock_response

        result = insert_payload_to_db({"code_hash": "test"})

        assert result is None

    def test_save_payload_to_file(self, tmp_path):
        """Test saving payload to file."""
        from scraper.core.engine import save_payload_to_file

        payload = {
            "code_hash": "test_hash_123",
            "code_original": "int x = 1;",
            "code_fixed": "int x = 0;"
        }

        save_payload_to_file(payload, str(tmp_path))

        # Check file was created
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "test_hash_123" in files[0].name
