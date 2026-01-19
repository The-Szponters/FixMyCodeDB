"""
Unit tests for scraper/core/engine.py
Tests the Producer-Consumer scraper engine functions.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import hashlib


class TestCalculateHash:
    """Tests for calculate_hash function."""

    def test_hash_empty_string(self):
        """Test hashing empty string."""
        from scraper.core.engine import calculate_hash

        result = calculate_hash("")
        expected = hashlib.sha256("".encode("utf-8")).hexdigest()

        assert result == expected

    def test_hash_simple_string(self):
        """Test hashing simple string."""
        from scraper.core.engine import calculate_hash

        result = calculate_hash("hello world")
        expected = hashlib.sha256("hello world".encode("utf-8")).hexdigest()

        assert result == expected

    def test_hash_code_content(self):
        """Test hashing code content."""
        from scraper.core.engine import calculate_hash

        code = "int main() { return 0; }"
        result = calculate_hash(code)

        assert len(result) == 64  # SHA-256 produces 64 hex chars
        assert result == hashlib.sha256(code.encode("utf-8")).hexdigest()

    def test_hash_deterministic(self):
        """Test that same input produces same hash."""
        from scraper.core.engine import calculate_hash

        result1 = calculate_hash("test")
        result2 = calculate_hash("test")

        assert result1 == result2

    def test_hash_different_inputs(self):
        """Test that different inputs produce different hashes."""
        from scraper.core.engine import calculate_hash

        result1 = calculate_hash("abc")
        result2 = calculate_hash("abd")

        assert result1 != result2


class TestGetRepoSlug:
    """Tests for get_repo_slug function."""

    def test_standard_url(self):
        """Test parsing standard GitHub URL."""
        from scraper.core.engine import get_repo_slug

        result = get_repo_slug("https://github.com/owner/repo")

        assert result == "owner/repo"

    def test_url_with_git_suffix(self):
        """Test parsing URL with .git suffix."""
        from scraper.core.engine import get_repo_slug

        result = get_repo_slug("https://github.com/owner/repo.git")

        assert result == "owner/repo"

    def test_url_with_trailing_slash(self):
        """Test parsing URL with trailing content."""
        from scraper.core.engine import get_repo_slug

        result = get_repo_slug("https://github.com/owner/repo/tree/main")

        assert result == "owner/repo"

    def test_invalid_url(self):
        """Test invalid URL raises ValueError."""
        from scraper.core.engine import get_repo_slug

        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            get_repo_slug("https://gitlab.com/owner/repo")


class TestCandidateTask:
    """Tests for CandidateTask dataclass."""

    def test_create_task(self):
        """Test creating CandidateTask."""
        from scraper.core.engine import CandidateTask

        task = CandidateTask(
            code_original="int x;",
            code_fixed="int x = 0;",
            repo_url="https://github.com/test/repo",
            commit_sha="abc123",
            commit_date="2024-01-01T00:00:00",
            base_name="file.c"
        )

        assert task.code_original == "int x;"
        assert task.code_fixed == "int x = 0;"
        assert task.repo_url == "https://github.com/test/repo"
        assert task.commit_sha == "abc123"


class TestGetGithubContent:
    """Tests for get_github_content function."""

    def test_get_content_success(self):
        """Test successful content retrieval."""
        from scraper.core.engine import get_github_content

        mock_repo = MagicMock()
        mock_content = MagicMock()
        mock_content.decoded_content = b"int main() {}"
        mock_repo.get_contents.return_value = mock_content

        result = get_github_content(mock_repo, "abc123", "file.c")

        assert result == "int main() {}"
        mock_repo.get_contents.assert_called_once_with("file.c", ref="abc123")

    def test_get_content_error(self):
        """Test content retrieval returns empty on error."""
        from scraper.core.engine import get_github_content

        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = Exception("Not found")

        result = get_github_content(mock_repo, "abc123", "file.c")

        assert result == ""


class TestGetAllRepoFiles:
    """Tests for get_all_repo_files function."""

    def test_get_files_success(self):
        """Test successful file list retrieval."""
        from scraper.core.engine import get_all_repo_files

        mock_repo = MagicMock()
        mock_tree = MagicMock()
        mock_element1 = MagicMock()
        mock_element1.path = "src/main.c"
        mock_element2 = MagicMock()
        mock_element2.path = "include/header.h"
        mock_tree.tree = [mock_element1, mock_element2]
        mock_repo.get_git_tree.return_value = mock_tree

        result = get_all_repo_files(mock_repo, "abc123")

        assert result == ["src/main.c", "include/header.h"]
        mock_repo.get_git_tree.assert_called_once_with("abc123", recursive=True)

    def test_get_files_error(self):
        """Test file list returns empty on error."""
        from scraper.core.engine import get_all_repo_files

        mock_repo = MagicMock()
        mock_repo.get_git_tree.side_effect = Exception("Error")

        result = get_all_repo_files(mock_repo, "abc123")

        assert result == []


class TestFindCorrespondingFile:
    """Tests for find_corresponding_file function."""

    def test_find_header_for_source(self):
        """Test finding header file for source file."""
        from scraper.core.engine import find_corresponding_file

        all_files = ["src/main.c", "src/main.h", "src/utils.c"]

        result = find_corresponding_file("src/main.c", [".h"], all_files)

        assert result == "src/main.h"

    def test_find_source_for_header(self):
        """Test finding source file for header."""
        from scraper.core.engine import find_corresponding_file

        all_files = ["src/main.c", "src/main.h", "src/utils.cpp"]

        result = find_corresponding_file("src/main.h", [".c", ".cpp"], all_files)

        assert result == "src/main.c"

    def test_no_corresponding_file(self):
        """Test when no corresponding file exists."""
        from scraper.core.engine import find_corresponding_file

        all_files = ["src/main.c", "src/other.h"]

        result = find_corresponding_file("src/main.c", [".h"], all_files)

        assert result is None


class TestFormatContext:
    """Tests for format_context function."""

    def test_format_with_both(self):
        """Test formatting with header and implementation."""
        from scraper.core.engine import format_context

        result = format_context("int x;", "int main() {}")

        assert "int x;" in result
        assert "int main() {}" in result

    def test_format_with_empty_header(self):
        """Test formatting with empty header."""
        from scraper.core.engine import format_context

        result = format_context("", "int main() {}")

        assert "int main() {}" in result

    def test_format_with_empty_impl(self):
        """Test formatting with empty implementation."""
        from scraper.core.engine import format_context

        result = format_context("int x;", "")

        assert "int x;" in result


class TestInsertPayloadToDb:
    """Tests for insert_payload_to_db function."""

    def test_insert_success(self):
        """Test successful DB insert."""
        from scraper.core.engine import insert_payload_to_db

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "123"}

        with patch('scraper.core.engine.requests.post', return_value=mock_response):
            result = insert_payload_to_db({"code": "test"})

            assert result == "123"

    def test_insert_duplicate(self):
        """Test duplicate entry returns None."""
        from scraper.core.engine import insert_payload_to_db

        mock_response = MagicMock()
        mock_response.status_code = 409

        with patch('scraper.core.engine.requests.post', return_value=mock_response):
            result = insert_payload_to_db({"code": "test"})

            assert result is None

    def test_insert_error(self):
        """Test API error returns None."""
        from scraper.core.engine import insert_payload_to_db
        import requests as req

        with patch('scraper.core.engine.requests.post', side_effect=req.exceptions.ConnectionError("Error")):
            result = insert_payload_to_db({"code": "test"})

            assert result is None


class TestSavePayloadToFile:
    """Tests for save_payload_to_file function."""

    def test_save_creates_file(self, tmp_path):
        """Test saving payload creates file."""
        from scraper.core.engine import save_payload_to_file

        payload = {"code": "int main() {}", "code_hash": "abc123"}

        save_payload_to_file(payload, str(tmp_path))

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_save_with_custom_directory(self, tmp_path):
        """Test saving to custom directory."""
        from scraper.core.engine import save_payload_to_file
        import json

        payload = {"code": "test", "code_hash": "hash123"}
        output_dir = tmp_path / "output"

        save_payload_to_file(payload, str(output_dir))

        assert output_dir.exists()
        files = list(output_dir.glob("*.json"))
        assert len(files) == 1

        # Verify content
        with open(files[0]) as f:
            saved = json.load(f)
        assert saved["code"] == "test"


class TestPoisonPill:
    """Tests for poison pill constant."""

    def test_poison_pill_is_none(self):
        """Test POISON_PILL is None."""
        from scraper.core.engine import POISON_PILL

        assert POISON_PILL is None


class TestApiUrl:
    """Tests for API_URL constant."""

    def test_api_url_default(self):
        """Test default API_URL value."""
        import os
        # Clear env var if set
        original = os.environ.pop("API_URL", None)

        try:
            # Need to reload module to get default
            import importlib
            import scraper.core.engine as engine
            importlib.reload(engine)

            assert "fastapi" in engine.API_URL or "localhost" in engine.API_URL or "8000" in engine.API_URL
        finally:
            if original:
                os.environ["API_URL"] = original
