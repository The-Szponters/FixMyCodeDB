"""
Unit tests for cli/handlers.py
Tests CLI handler functions with mocked requests and sockets.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import json


# ============================================================================
# Test Label Mapping
# ============================================================================

class TestLabelMapping:
    """Tests for label mapping utilities."""

    def test_labels_to_filter_group_labels(self):
        """Test converting group labels to MongoDB filter."""
        from cli.handlers import labels_to_filter

        result = labels_to_filter(["MemError", "LogicError"])

        assert "labels.groups.memory_management" in result
        assert result["labels.groups.memory_management"] is True
        assert "labels.groups.logic_error" in result
        assert result["labels.groups.logic_error"] is True

    def test_labels_to_filter_cppcheck_labels(self):
        """Test converting unknown labels as cppcheck labels."""
        from cli.handlers import labels_to_filter

        result = labels_to_filter(["nullPointer"])

        assert "labels.cppcheck" in result
        assert result["labels.cppcheck"] == {"$in": ["nullPointer"]}

    def test_labels_to_filter_mixed(self):
        """Test mixed group and cppcheck labels."""
        from cli.handlers import labels_to_filter

        result = labels_to_filter(["MemError", "customLabel"])

        assert "labels.groups.memory_management" in result
        assert "labels.cppcheck" in result


# ============================================================================
# Test Scrape Handler
# ============================================================================

class TestHandleScrape:
    """Tests for handle_scrape function."""

    def test_scrape_success(self):
        """Test successful scrape command."""
        from cli.handlers import handle_scrape

        with patch('cli.handlers.socket.socket') as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value = mock_socket
            mock_socket.recv.side_effect = [
                b"ACK: Scraping config.json",
                b"ACK: Finished Scraping config.json\n",
            ]

            result = handle_scrape("config.json")

            assert result == 0
            mock_socket.connect.assert_called_once()
            mock_socket.sendall.assert_called_once()

    def test_scrape_connection_error(self):
        """Test scrape with connection error."""
        from cli.handlers import handle_scrape
        import socket

        with patch('cli.handlers.socket.socket') as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value = mock_socket
            mock_socket.connect.side_effect = socket.gaierror("host not found")

            result = handle_scrape("config.json")

            assert result == 1

    def test_scrape_timeout(self):
        """Test scrape with timeout."""
        from cli.handlers import handle_scrape
        import socket

        with patch('cli.handlers.socket.socket') as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value = mock_socket
            mock_socket.recv.side_effect = socket.timeout()

            result = handle_scrape("config.json")

            assert result == 1

    def test_scrape_no_response(self):
        """Test scrape with no initial response."""
        from cli.handlers import handle_scrape

        with patch('cli.handlers.socket.socket') as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value = mock_socket
            mock_socket.recv.return_value = b""

            result = handle_scrape("config.json")

            assert result == 1


# ============================================================================
# Test List Handlers
# ============================================================================

class TestHandleListAll:
    """Tests for handle_list_all function."""

    def test_list_all_success(self):
        """Test successful list all."""
        from cli.handlers import handle_list_all

        with patch('cli.handlers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {"_id": "123", "labels": {"groups": {"memory_management": True}, "cppcheck": []}}
            ]
            mock_get.return_value = mock_response

            result = handle_list_all()

            assert result == 0

    def test_list_all_connection_error(self):
        """Test list all with connection error."""
        from cli.handlers import handle_list_all
        import requests

        with patch('cli.handlers.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()

            result = handle_list_all()

            assert result == 1

    def test_list_all_http_error(self):
        """Test list all with HTTP error."""
        from cli.handlers import handle_list_all
        import requests

        with patch('cli.handlers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=MagicMock(text="Server Error")
            )
            mock_get.return_value = mock_response

            result = handle_list_all()

            assert result == 1


class TestHandleListLabels:
    """Tests for handle_list_labels function."""

    def test_list_labels_success(self):
        """Test successful list by labels."""
        from cli.handlers import handle_list_labels

        with patch('cli.handlers.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {"_id": "123", "labels": {"groups": {"memory_management": True}, "cppcheck": []}}
            ]
            mock_post.return_value = mock_response

            result = handle_list_labels(["MemError"])

            assert result == 0
            # Verify filter was constructed correctly
            call_args = mock_post.call_args
            assert "json" in call_args.kwargs
            assert "filter" in call_args.kwargs["json"]

    def test_list_labels_empty_result(self):
        """Test list labels with no matching entries."""
        from cli.handlers import handle_list_labels

        with patch('cli.handlers.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_post.return_value = mock_response

            result = handle_list_labels(["NonexistentLabel"])

            assert result == 0


# ============================================================================
# Test Import Handler
# ============================================================================

class TestHandleImportAll:
    """Tests for handle_import_all function."""

    def test_import_folder_not_exists(self, tmp_path):
        """Test import from non-existent folder."""
        from cli.handlers import handle_import_all

        result = handle_import_all("/nonexistent/path", "JSON")

        assert result == 1

    def test_import_no_files(self, tmp_path):
        """Test import from empty folder."""
        from cli.handlers import handle_import_all

        result = handle_import_all(str(tmp_path), "JSON")

        assert result == 1

    def test_import_json_success(self, tmp_path, sample_code_entry_dict):
        """Test successful JSON import."""
        from cli.handlers import handle_import_all

        # Create a test JSON file
        json_file = tmp_path / "test.json"
        entry = sample_code_entry_dict.copy()
        entry.pop("_id", None)
        json_file.write_text(json.dumps(entry))

        with patch('cli.handlers.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_post.return_value = mock_response

            result = handle_import_all(str(tmp_path), "JSON")

            assert result == 0

    def test_import_json_duplicate(self, tmp_path, sample_code_entry_dict):
        """Test import with duplicate entry."""
        from cli.handlers import handle_import_all

        json_file = tmp_path / "test.json"
        entry = sample_code_entry_dict.copy()
        entry.pop("_id", None)
        json_file.write_text(json.dumps(entry))

        with patch('cli.handlers.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_post.return_value = mock_response

            result = handle_import_all(str(tmp_path), "JSON")

            # Errors occurred but function completes
            assert result == 1


# ============================================================================
# Test Export Handler
# ============================================================================

class TestHandleExportAll:
    """Tests for handle_export_all function."""

    def test_export_json_success(self, tmp_path, sample_code_entry_dict):
        """Test successful JSON export."""
        from cli.handlers import handle_export_all

        with patch('cli.handlers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = [
                json.dumps(sample_code_entry_dict)
            ]
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_get.return_value = mock_response

            result = handle_export_all(str(tmp_path), "JSON")

            assert result == 0

    def test_export_csv_success(self, tmp_path, sample_code_entry_dict):
        """Test successful CSV export."""
        from cli.handlers import handle_export_all

        with patch('cli.handlers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = [
                json.dumps(sample_code_entry_dict)
            ]
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_get.return_value = mock_response

            result = handle_export_all(str(tmp_path), "CSV")

            assert result == 0

    def test_export_with_labels_filter(self, tmp_path, sample_code_entry_dict):
        """Test export with labels filter."""
        from cli.handlers import handle_export_all

        with patch('cli.handlers.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [sample_code_entry_dict]
            mock_post.return_value = mock_response

            result = handle_export_all(str(tmp_path), "JSON", labels=["MemError"])

            assert result == 0
            mock_post.assert_called_once()

    def test_export_connection_error(self, tmp_path):
        """Test export with connection error."""
        from cli.handlers import handle_export_all
        import requests

        with patch('cli.handlers.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()

            result = handle_export_all(str(tmp_path), "JSON")

            assert result == 1

    def test_export_empty(self, tmp_path):
        """Test export with no entries."""
        from cli.handlers import handle_export_all

        with patch('cli.handlers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = []
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_get.return_value = mock_response

            result = handle_export_all(str(tmp_path), "JSON")

            assert result == 0


# ============================================================================
# Test Edit Handler
# ============================================================================

class TestHandleEditLabels:
    """Tests for handle_edit_labels function."""

    def test_edit_add_labels_success(self):
        """Test successful label addition."""
        from cli.handlers import handle_edit_labels

        with patch('cli.handlers.requests.patch') as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"_id": "123"}
            mock_patch.return_value = mock_response

            result = handle_edit_labels("123", add_labels=["MemError"])

            assert result == 0

    def test_edit_remove_labels_success(self):
        """Test successful label removal."""
        from cli.handlers import handle_edit_labels

        with patch('cli.handlers.requests.patch') as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"_id": "123"}
            mock_patch.return_value = mock_response

            result = handle_edit_labels("123", remove_labels=["LogicError"])

            assert result == 0

    def test_edit_no_labels_specified(self):
        """Test edit with no labels specified."""
        from cli.handlers import handle_edit_labels

        result = handle_edit_labels("123")

        assert result == 1

    def test_edit_entry_not_found(self):
        """Test edit on non-existent entry."""
        from cli.handlers import handle_edit_labels

        with patch('cli.handlers.requests.patch') as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_patch.return_value = mock_response

            result = handle_edit_labels("nonexistent", add_labels=["MemError"])

            assert result == 1

    def test_edit_connection_error(self):
        """Test edit with connection error."""
        from cli.handlers import handle_edit_labels
        import requests

        with patch('cli.handlers.requests.patch') as mock_patch:
            mock_patch.side_effect = requests.exceptions.ConnectionError()

            result = handle_edit_labels("123", add_labels=["MemError"])

            assert result == 1


# ============================================================================
# Test Helper Functions
# ============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_safe_filename(self):
        """Test safe filename generation."""
        from cli.handlers import _safe_filename

        assert _safe_filename("abc123") == "abc123"
        assert _safe_filename("abc/def") == "abcdef"
        assert _safe_filename("test.json") == "test.json"
        assert _safe_filename("file with spaces") == "filewithspaces"

    def test_flatten_entry(self, sample_code_entry_dict):
        """Test entry flattening for CSV."""
        from cli.handlers import _flatten_entry

        flat = _flatten_entry(sample_code_entry_dict)

        assert "_id" in flat
        assert "code_original" in flat
        assert "repo_url" in flat
        assert "labels_memory_management" in flat

    def test_unflatten_csv_row(self):
        """Test CSV row unflattening."""
        from cli.handlers import _unflatten_csv_row

        row = {
            "code_original": "int main() {}",
            "code_fixed": "",
            "code_hash": "a" * 64,
            "repo_url": "https://github.com/test",
            "repo_commit_hash": "abc",
            "repo_commit_date": "2024-01-01T00:00:00",
            "ingest_timestamp": "2024-01-01T00:00:00",
            "labels_cppcheck": '["nullPointer"]',
            "labels_clang": "{}",
            "labels_memory_management": "True",
            "labels_invalid_access": "False",
            "labels_uninitialized": "False",
            "labels_concurrency": "False",
            "labels_logic_error": "False",
            "labels_resource_leak": "False",
            "labels_security_portability": "False",
            "labels_code_quality_performance": "False",
        }

        entry = _unflatten_csv_row(row)

        assert entry["code_original"] == "int main() {}"
        assert entry["repo"]["url"] == "https://github.com/test"
        assert entry["labels"]["cppcheck"] == ["nullPointer"]
        assert entry["labels"]["groups"]["memory_management"] is True

    def test_print_entries_table_empty(self, capsys):
        """Test printing empty entries table."""
        from cli.handlers import _print_entries_table

        _print_entries_table([])

        captured = capsys.readouterr()
        assert "No entries found" in captured.out

    def test_print_entries_table_with_entries(self, capsys, sample_code_entry_dict):
        """Test printing entries table with data."""
        from cli.handlers import _print_entries_table

        _print_entries_table([sample_code_entry_dict])

        captured = capsys.readouterr()
        assert "507f1f77bcf86cd799439011" in captured.out
        assert "Total: 1 entries" in captured.out
