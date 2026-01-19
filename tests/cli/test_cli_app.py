"""
Unit tests for cli/cli_app.py
Tests interactive CLI functions with mocked I/O.
"""
import pytest
from unittest.mock import patch, MagicMock
import json


class TestBuildApiPayload:
    """Tests for build_api_payload function."""

    def test_empty_params(self):
        """Test with empty params returns empty filter."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({})

        assert result == {}

    def test_repo_url_param(self):
        """Test repo_url is mapped correctly."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({"repo_url": "https://github.com/test/repo"})

        assert result["repo.url"] == "https://github.com/test/repo"

    def test_commit_hash_param(self):
        """Test commit_hash is mapped correctly."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({"commit_hash": "abc123"})

        assert result["repo.commit_hash"] == "abc123"

    def test_code_hash_param(self):
        """Test code_hash is passed through."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({"code_hash": "a" * 64})

        assert result["code_hash"] == "a" * 64

    def test_boolean_true_variants(self):
        """Test various true values for boolean flags."""
        from cli.cli_app import build_api_payload

        for true_val in ["true", "1", "yes", "y", "True", "YES"]:
            result = build_api_payload({"has_memory_management": true_val})
            assert result.get("labels.groups.memory_management") is True

    def test_boolean_false_variants(self):
        """Test various false values for boolean flags."""
        from cli.cli_app import build_api_payload

        for false_val in ["false", "0", "no", "n", "False", "NO"]:
            result = build_api_payload({"has_memory_management": false_val})
            assert result.get("labels.groups.memory_management") is False

    def test_empty_boolean_ignored(self):
        """Test empty boolean values are ignored."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({"has_memory_management": ""})

        assert "labels.groups.memory_management" not in result

    def test_multiple_boolean_flags(self):
        """Test multiple boolean flags."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({
            "has_memory_management": "true",
            "has_logic_error": "true",
            "has_concurrency": "false"
        })

        assert result["labels.groups.memory_management"] is True
        assert result["labels.groups.logic_error"] is True
        assert result["labels.groups.concurrency"] is False


class TestDoImport:
    """Tests for do_import function."""

    def test_import_success(self, tmp_path):
        """Test successful import."""
        from cli.cli_app import do_import

        with patch('cli.cli_app.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{"_id": "123"}]
            mock_post.return_value = mock_response

            params = {
                "target file": str(tmp_path / "output.json"),
                "limit": "100"
            }

            do_import(params)

            # File should be created
            assert (tmp_path / "output.json").exists()

    def test_import_connection_error(self, capsys):
        """Test import with connection error."""
        from cli.cli_app import do_import
        import requests

        with patch('cli.cli_app.requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError()

            params = {"target file": "/tmp/test.json", "limit": "100"}

            do_import(params)

            captured = capsys.readouterr()
            assert "Error" in captured.out


class TestDoScrape:
    """Tests for do_scrape function."""

    def test_scrape_success(self, capsys):
        """Test successful scrape."""
        from cli.cli_app import do_scrape

        with patch('cli.cli_app.socket.socket') as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value = mock_socket
            mock_socket.recv.side_effect = [
                b"ACK: Scraping config.json",
                b"ACK: Finished Scraping config.json\n"
            ]

            params = {"config_file": "config.json"}

            do_scrape(params)

            captured = capsys.readouterr()
            assert "SCRAPE" in captured.out

    def test_scrape_no_response(self, capsys):
        """Test scrape with no response."""
        from cli.cli_app import do_scrape

        with patch('cli.cli_app.socket.socket') as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value = mock_socket
            mock_socket.recv.return_value = b""

            params = {"config_file": "config.json"}

            do_scrape(params)

            captured = capsys.readouterr()
            assert "No response" in captured.out


class TestDoExportAll:
    """Tests for do_export_all function."""

    def test_export_creates_directory(self, tmp_path):
        """Test export creates directory if needed."""
        from cli.cli_app import do_export_all

        export_dir = tmp_path / "export_test"

        with patch('cli.cli_app.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = []
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_get.return_value = mock_response

            with patch('cli.cli_app.Path') as mock_path:
                mock_path_instance = MagicMock()
                mock_path.return_value = mock_path_instance

                do_export_all({})


class TestDoLabel:
    """Tests for do_label function."""

    def test_label_prints_message(self, capsys):
        """Test label command prints message."""
        from cli.cli_app import do_label

        do_label({})

        captured = capsys.readouterr()
        assert "Labeling" in captured.out


class TestCLIApp:
    """Tests for CLIApp class."""

    def test_cli_app_inherits_command_tree(self):
        """Test CLIApp inherits from CommandTree."""
        from cli.cli_app import CLIApp
        from cli.command_tree import CommandTree

        app = CLIApp()

        assert isinstance(app, CommandTree)

    def test_cli_app_has_commands(self):
        """Test CLIApp registers expected commands."""
        from cli.cli_app import CLIApp

        app = CLIApp()

        assert "scrape" in app.root.children
        assert "import" in app.root.children
        assert "import-all" in app.root.children
        assert "export-all" in app.root.children
        assert "label" in app.root.children

    def test_scrape_command_has_action(self):
        """Test scrape command has action bound."""
        from cli.cli_app import CLIApp

        app = CLIApp()

        assert app.root.children["scrape"].action is not None
        assert app.root.children["scrape"].is_command is True

    def test_scrape_command_has_params(self):
        """Test scrape command has parameters."""
        from cli.cli_app import CLIApp

        app = CLIApp()

        assert "config_file" in app.root.children["scrape"].param_set


class TestSafeFilename:
    """Tests for _safe_filename function."""

    def test_alphanumeric(self):
        """Test alphanumeric characters are preserved."""
        from cli.cli_app import _safe_filename

        result = _safe_filename("abc123")

        assert result == "abc123"

    def test_special_chars_removed(self):
        """Test special characters are removed."""
        from cli.cli_app import _safe_filename

        result = _safe_filename("file/with\\special:chars")

        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result

    def test_allowed_chars_preserved(self):
        """Test allowed special chars are preserved."""
        from cli.cli_app import _safe_filename

        result = _safe_filename("file-name_v1.txt")

        assert result == "file-name_v1.txt"


class TestConstants:
    """Tests for module constants."""

    def test_filter_params_defined(self):
        """Test FILTER_PARAMS dictionary is defined."""
        from cli.cli_app import FILTER_PARAMS

        assert "limit" in FILTER_PARAMS
        assert "repo_url" in FILTER_PARAMS
        assert "has_memory_management" in FILTER_PARAMS

    def test_api_base_default(self):
        """Test API_BASE has default value."""
        from cli.cli_app import API_BASE

        assert "localhost" in API_BASE or "8000" in API_BASE
