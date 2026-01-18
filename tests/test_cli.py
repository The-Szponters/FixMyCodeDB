"""
Tests for CLI modules.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli.argparser import (
    create_parser,
    parse_args,
    has_action_args,
    build_filter_dict,
)
from cli.handlers import CommandHandler


class TestArgparser:
    """Tests for CLI argument parser."""

    def test_create_parser(self):
        """Test parser creation."""
        parser = create_parser()

        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.prog == "fixmycodedb"

    def test_parse_no_args(self):
        """Test parsing with no arguments (interactive mode)."""
        args = parse_args([])

        assert not args.scan
        assert args.export is None
        assert not args.label_manual

    def test_parse_scan_args(self):
        """Test parsing scan command."""
        args = parse_args(["--scan", "--config", "custom.json"])

        assert args.scan
        assert args.config == "custom.json"

    def test_parse_scan_parallel(self):
        """Test parsing parallel scan command."""
        args = parse_args(["--scan", "--parallel", "--max-workers", "8"])

        assert args.scan
        assert args.parallel
        assert args.max_workers == 8

    def test_parse_scan_single_repo(self):
        """Test parsing scan with single repo URL."""
        args = parse_args(["--scan", "--repo-url", "https://github.com/test/repo"])

        assert args.scan
        assert args.repo_url == "https://github.com/test/repo"

    def test_parse_export_json(self):
        """Test parsing JSON export command."""
        args = parse_args(["--export", "json", "--output", "data.json"])

        assert args.export == "json"
        assert args.output == "data.json"

    def test_parse_export_csv(self):
        """Test parsing CSV export command."""
        args = parse_args(["--export", "csv", "-o", "data.csv"])

        assert args.export == "csv"
        assert args.output == "data.csv"

    def test_parse_label_manual(self):
        """Test parsing manual label command."""
        args = parse_args([
            "--label-manual",
            "--id", "abc123",
            "--set-label", "memory-leak"
        ])

        assert args.label_manual
        assert args.id == "abc123"
        assert args.set_label == "memory-leak"

    def test_parse_label_remove(self):
        """Test parsing label removal command."""
        args = parse_args([
            "--label-manual",
            "--id", "abc123",
            "--remove-label", "old-label"
        ])

        assert args.label_manual
        assert args.remove_label == "old-label"

    def test_parse_query(self):
        """Test parsing query command."""
        args = parse_args(["--query", "--limit", "50"])

        assert args.query
        assert args.limit == 50

    def test_parse_query_with_filters(self):
        """Test parsing query with filters."""
        args = parse_args([
            "--query",
            "--has-memory-management",
            "--repo-filter", "https://github.com/test/repo"
        ])

        assert args.query
        assert args.has_memory_management
        assert args.repo_filter == "https://github.com/test/repo"

    def test_parse_no_docker(self):
        """Test parsing --no-docker flag."""
        args = parse_args(["--no-docker", "--scan"])

        assert args.no_docker
        assert args.scan

    def test_parse_verbose(self):
        """Test parsing verbose flag."""
        args = parse_args(["-v", "--query"])

        assert args.verbose

    def test_parse_api_url(self):
        """Test parsing custom API URL."""
        args = parse_args(["--api-url", "http://custom:9000", "--query"])

        assert args.api_url == "http://custom:9000"

    def test_mutually_exclusive_modes(self):
        """Test that mode flags are mutually exclusive."""
        # This should work
        args = parse_args(["--scan"])
        assert args.scan

        # argparse should prevent multiple modes


class TestHasActionArgs:
    """Tests for has_action_args function."""

    def test_no_action(self):
        """Test with no action args."""
        args = parse_args([])

        assert not has_action_args(args)

    def test_scan_action(self):
        """Test with scan action."""
        args = parse_args(["--scan"])

        assert has_action_args(args)

    def test_export_action(self):
        """Test with export action."""
        args = parse_args(["--export", "json"])

        assert has_action_args(args)

    def test_label_action(self):
        """Test with label action."""
        args = parse_args(["--label-manual"])

        assert has_action_args(args)

    def test_query_action(self):
        """Test with query action."""
        args = parse_args(["--query"])

        assert has_action_args(args)


class TestBuildFilterDict:
    """Tests for build_filter_dict function."""

    def test_empty_filters(self):
        """Test with no filters."""
        args = parse_args(["--query"])

        filter_dict = build_filter_dict(args)

        assert filter_dict == {}

    def test_repo_filter(self):
        """Test with repo URL filter."""
        args = parse_args(["--query", "--repo-filter", "https://github.com/test/repo"])

        filter_dict = build_filter_dict(args)

        assert filter_dict["repo.url"] == "https://github.com/test/repo"

    def test_commit_hash_filter(self):
        """Test with commit hash filter."""
        args = parse_args(["--query", "--commit-hash", "abc123"])

        filter_dict = build_filter_dict(args)

        assert filter_dict["repo.commit_hash"] == "abc123"

    def test_boolean_filters(self):
        """Test with boolean label filters."""
        args = parse_args([
            "--query",
            "--has-memory-management",
            "--has-invalid-access"
        ])

        filter_dict = build_filter_dict(args)

        assert filter_dict["labels.groups.memory_management"] is True
        assert filter_dict["labels.groups.invalid_access"] is True

    def test_combined_filters(self):
        """Test with multiple filters."""
        args = parse_args([
            "--query",
            "--repo-filter", "https://github.com/test/repo",
            "--has-memory-management",
            "--limit", "50"
        ])

        filter_dict = build_filter_dict(args)

        assert "repo.url" in filter_dict
        assert "labels.groups.memory_management" in filter_dict


class TestCommandHandler:
    """Tests for CommandHandler class."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return CommandHandler(api_url="http://localhost:8000", verbose=False)

    def test_init(self, handler):
        """Test handler initialization."""
        assert handler.api_url == "http://localhost:8000"
        assert handler.verbose is False

    def test_init_default_api_url(self):
        """Test handler with default API URL."""
        handler = CommandHandler()

        assert handler.api_url is not None

    @patch("cli.handlers.requests")
    def test_export_json(self, mock_requests, handler, tmp_path):
        """Test JSON export."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"_id": "test", "code_hash": "abc"}]
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        output_path = str(tmp_path / "export.json")
        result = handler.export_json(output_path, limit=10)

        assert result is True
        assert os.path.exists(output_path)

        with open(output_path) as f:
            data = json.load(f)
        assert len(data) == 1

    @patch("cli.handlers.requests")
    def test_export_csv(self, mock_requests, handler, tmp_path):
        """Test CSV export."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            "_id": "test",
            "code_hash": "a" * 64,
            "code_original": "int x;",
            "code_fixed": "int x = 0;",
            "repo": {"url": "https://github.com/test/repo", "commit_hash": "abc", "commit_date": "2024-01-01"},
            "ingest_timestamp": "2024-01-01T00:00:00",
            "labels": {
                "cppcheck": ["uninitvar"],
                "groups": {"memory_management": False, "uninitialized": True}
            }
        }]
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        output_path = str(tmp_path / "export.csv")
        result = handler.export_csv(output_path, limit=10)

        assert result is True
        assert os.path.exists(output_path)

    @patch("cli.handlers.requests")
    def test_export_connection_error(self, mock_requests, handler, tmp_path):
        """Test export with connection error."""
        mock_requests.post.side_effect = Exception("Connection refused")

        output_path = str(tmp_path / "export.json")
        result = handler.export_json(output_path)

        assert result is False

    @patch("cli.handlers.requests")
    def test_label_manual_add(self, mock_requests, handler):
        """Test adding a label."""
        # Mock get entry
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "_id": "test_id",
            "labels": {"cppcheck": ["existing_label"]}
        }
        mock_get_response.raise_for_status = MagicMock()

        # Mock update
        mock_put_response = MagicMock()
        mock_put_response.status_code = 200
        mock_put_response.raise_for_status = MagicMock()

        mock_requests.get.return_value = mock_get_response
        mock_requests.put.return_value = mock_put_response

        result = handler.label_manual("test_id", "new_label", remove=False)

        assert result is True
        mock_requests.put.assert_called_once()

    @patch("cli.handlers.requests")
    def test_label_manual_remove(self, mock_requests, handler):
        """Test removing a label."""
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "_id": "test_id",
            "labels": {"cppcheck": ["label_to_remove", "other_label"]}
        }
        mock_get_response.raise_for_status = MagicMock()

        mock_put_response = MagicMock()
        mock_put_response.status_code = 200
        mock_put_response.raise_for_status = MagicMock()

        mock_requests.get.return_value = mock_get_response
        mock_requests.put.return_value = mock_put_response

        result = handler.label_manual("test_id", "label_to_remove", remove=True)

        assert result is True

    @patch("cli.handlers.requests")
    def test_label_manual_not_found(self, mock_requests, handler):
        """Test labeling non-existent record."""
        import requests as real_requests
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        http_error = real_requests.exceptions.HTTPError(response=mock_response)
        http_error.response = mock_response
        mock_requests.get.return_value.raise_for_status.side_effect = http_error
        mock_requests.exceptions = real_requests.exceptions

        result = handler.label_manual("nonexistent_id", "label")

        assert result is False

    @patch("cli.handlers.requests")
    def test_query(self, mock_requests, handler):
        """Test querying entries."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"_id": "1", "repo": {"url": "https://github.com/test/repo"}, "labels": {"cppcheck": []}},
            {"_id": "2", "repo": {"url": "https://github.com/test/repo2"}, "labels": {"cppcheck": ["memleak"]}}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        entries = handler.query(limit=10, display=False)

        assert entries is not None
        assert len(entries) == 2

    @patch("cli.handlers.requests")
    def test_get_entry(self, mock_requests, handler):
        """Test getting single entry."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"_id": "test_id", "code_hash": "abc"}
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        entry = handler.get_entry("test_id")

        assert entry is not None
        assert entry["_id"] == "test_id"

    def test_safe_filename(self, handler):
        """Test safe filename generation."""
        assert handler._safe_filename("test-file_123.json") == "test-file_123.json"
        assert handler._safe_filename("test file!@#$%") == "testfile"
        assert handler._safe_filename("") == ""

    @patch("cli.handlers.requests")
    def test_set_label_group_valid(self, mock_requests, handler):
        """Test setting valid label group."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_requests.put.return_value = mock_response

        result = handler.set_label_group("test_id", "memory_management", True)

        assert result is True

    def test_set_label_group_invalid(self, handler):
        """Test setting invalid label group."""
        result = handler.set_label_group("test_id", "invalid_group", True)

        assert result is False

    @patch("cli.handlers.requests")
    def test_set_label_group_not_found(self, mock_requests, handler):
        """Test setting label group on non-existent record."""
        import requests as real_requests

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        http_error = real_requests.exceptions.HTTPError(response=mock_response)
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_requests.put.return_value = mock_response
        mock_requests.exceptions = real_requests.exceptions

        result = handler.set_label_group("nonexistent_id", "memory_management", True)

        assert result is False

    @patch("cli.handlers.requests")
    def test_set_label_group_connection_error(self, mock_requests, handler):
        """Test setting label group with connection error."""
        import requests as real_requests

        mock_requests.put.side_effect = real_requests.exceptions.ConnectionError()
        mock_requests.exceptions = real_requests.exceptions

        result = handler.set_label_group("test_id", "memory_management", True)

        assert result is False

    @patch("cli.handlers.requests")
    def test_get_entry_not_found(self, mock_requests, handler):
        """Test getting non-existent entry."""
        import requests as real_requests

        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = real_requests.exceptions.HTTPError(response=mock_response)
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_requests.get.return_value = mock_response
        mock_requests.exceptions = real_requests.exceptions

        entry = handler.get_entry("nonexistent")

        assert entry is None

    @patch("cli.handlers.requests")
    def test_get_entry_connection_error(self, mock_requests, handler):
        """Test getting entry with connection error."""
        import requests as real_requests

        mock_requests.get.side_effect = real_requests.exceptions.ConnectionError()
        mock_requests.exceptions = real_requests.exceptions

        entry = handler.get_entry("test_id")

        assert entry is None

    @patch("cli.handlers.requests")
    def test_fetch_entries_connection_error(self, mock_requests, handler):
        """Test fetching entries with connection error."""
        import requests as real_requests

        mock_requests.post.side_effect = real_requests.exceptions.ConnectionError()
        mock_requests.exceptions = real_requests.exceptions

        entries = handler._fetch_entries({}, 10)

        assert entries is None

    @patch("cli.handlers.requests")
    def test_fetch_entries_http_error(self, mock_requests, handler):
        """Test fetching entries with HTTP error."""
        import requests as real_requests

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"
        http_error = real_requests.exceptions.HTTPError(response=mock_response)
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_requests.post.return_value = mock_response
        mock_requests.exceptions = real_requests.exceptions

        entries = handler._fetch_entries({}, 10)

        assert entries is None

    @patch("cli.handlers.requests")
    def test_export_all_files_success(self, mock_requests, handler, tmp_path):
        """Test exporting all files."""
        # Mock streaming response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_lines.return_value = [
            '{"_id": "entry1", "code_hash": "abc"}',
            '{"_id": "entry2", "code_hash": "def"}',
        ]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_requests.get.return_value = mock_response

        result = handler.export_all_files(str(tmp_path / "export"))

        assert result is True
        assert (tmp_path / "export" / "entry1.json").exists()
        assert (tmp_path / "export" / "entry2.json").exists()

    @patch("cli.handlers.requests")
    def test_export_all_files_connection_error(self, mock_requests, handler):
        """Test exporting all files with connection error."""
        import requests as real_requests

        mock_requests.get.side_effect = real_requests.exceptions.ConnectionError()
        mock_requests.exceptions = real_requests.exceptions

        result = handler.export_all_files("export_dir")

        assert result is False

    @patch("cli.handlers.socket")
    def test_scan_success(self, mock_socket, handler):
        """Test successful scan."""
        mock_sock = MagicMock()
        mock_socket.socket.return_value = mock_sock

        # Simulate responses
        mock_sock.recv.side_effect = [
            b"ACK: Scraping config.json",
            b"PROGRESS: 1/10 (commit: abc123)\n",
            b"ACK: Finished Scraping config.json\n",
        ]

        result = handler.scan("config.json", parallel=False)

        assert result is True
        mock_sock.sendall.assert_called()

    @patch("cli.handlers.socket")
    def test_scan_parallel(self, mock_socket, handler):
        """Test parallel scan."""
        mock_sock = MagicMock()
        mock_socket.socket.return_value = mock_sock

        mock_sock.recv.side_effect = [
            b"ACK: Parallel scraping config.json",
            b"RESULT: Completed 4/4 repos, 100 records in 60.0s\n",
            b"ACK: Finished Parallel Scraping config.json\n",
        ]

        result = handler.scan("config.json", parallel=True)

        assert result is True
        # Verify parallel command was sent
        call_args = mock_sock.sendall.call_args[0][0].decode()
        assert "SCRAPE_PARALLEL" in call_args

    @patch("cli.handlers.socket.socket")
    def test_scan_timeout(self, mock_socket_class, handler):
        """Test scan timeout."""
        import socket as real_socket

        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.connect.side_effect = real_socket.timeout("Connection timed out")

        result = handler.scan("config.json")

        assert result is False

    @patch("cli.handlers.socket.socket")
    def test_scan_connection_refused(self, mock_socket_class, handler):
        """Test scan with connection refused."""
        import socket as real_socket

        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.connect.side_effect = real_socket.gaierror("Name resolution failed")

        result = handler.scan("config.json")

        assert result is False

    @patch("cli.handlers.socket.socket")
    def test_scan_no_response(self, mock_socket_class, handler):
        """Test scan with no response."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.recv.return_value = b""

        result = handler.scan("config.json")

        assert result is False

    def test_set_label_group_invalid(self, handler):
        """Test setting invalid label group."""
        result = handler.set_label_group("test_id", "invalid_group", True)

        assert result is False
