"""
Tests for cli/cli_app.py module.
"""

import json
import pytest
from unittest.mock import patch, MagicMock


class TestBuildApiPayload:
    """Tests for build_api_payload function."""

    def test_empty_params(self):
        """Test with empty parameters."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({})

        assert result == {}

    def test_repo_url_filter(self):
        """Test with repo_url parameter."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({"repo_url": "https://github.com/test/repo"})

        assert result == {"repo.url": "https://github.com/test/repo"}

    def test_commit_hash_filter(self):
        """Test with commit_hash parameter."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({"commit_hash": "abc123"})

        assert result == {"repo.commit_hash": "abc123"}

    def test_code_hash_filter(self):
        """Test with code_hash parameter."""
        from cli.cli_app import build_api_payload

        result = build_api_payload({"code_hash": "sha256hash"})

        assert result == {"code_hash": "sha256hash"}

    def test_boolean_filters_true(self):
        """Test with boolean filters set to true."""
        from cli.cli_app import build_api_payload

        params = {
            "has_memory_management": "true",
            "has_invalid_access": "1",
            "has_uninitialized": "yes",
            "has_concurrency": "Y",
        }
        result = build_api_payload(params)

        assert result["labels.groups.memory_management"] is True
        assert result["labels.groups.invalid_access"] is True
        assert result["labels.groups.uninitialized"] is True
        assert result["labels.groups.concurrency"] is True

    def test_boolean_filters_false(self):
        """Test with boolean filters set to false."""
        from cli.cli_app import build_api_payload

        params = {
            "has_logic_error": "false",
            "has_resource_leak": "0",
            "has_security_portability": "no",
            "has_code_quality_performance": "n",
        }
        result = build_api_payload(params)

        assert result["labels.groups.logic_error"] is False
        assert result["labels.groups.resource_leak"] is False
        assert result["labels.groups.security_portability"] is False
        assert result["labels.groups.code_quality_performance"] is False

    def test_combined_filters(self):
        """Test with multiple filter types."""
        from cli.cli_app import build_api_payload

        params = {
            "repo_url": "https://github.com/test/repo",
            "has_memory_management": "true",
            "has_logic_error": "false",
        }
        result = build_api_payload(params)

        assert result["repo.url"] == "https://github.com/test/repo"
        assert result["labels.groups.memory_management"] is True
        assert result["labels.groups.logic_error"] is False


class TestDoImport:
    """Tests for do_import function."""

    @patch("cli.cli_app.requests")
    def test_do_import_success(self, mock_requests, tmp_path):
        """Test successful import."""
        from cli.cli_app import do_import

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"_id": "test123", "code_original": "test"}]
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        target_file = str(tmp_path / "import.json")
        params = {"limit": "10", "target file": target_file}

        do_import(params)

        assert (tmp_path / "import.json").exists()
        with open(target_file) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["_id"] == "test123"

    @patch("cli.cli_app.requests")
    def test_do_import_connection_error(self, mock_requests):
        """Test import with connection error."""
        import requests as real_requests
        from cli.cli_app import do_import

        mock_requests.post.side_effect = real_requests.exceptions.ConnectionError()
        mock_requests.exceptions = real_requests.exceptions

        params = {"limit": "10", "target file": "test.json"}

        # Should not raise, just print error
        do_import(params)

    @patch("cli.cli_app.requests")
    def test_do_import_http_error(self, mock_requests):
        """Test import with HTTP error."""
        import requests as real_requests
        from cli.cli_app import do_import

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        http_error = real_requests.exceptions.HTTPError(response=mock_response)
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_requests.post.return_value = mock_response
        mock_requests.exceptions = real_requests.exceptions

        params = {"limit": "10", "target file": "test.json"}

        # Should not raise
        do_import(params)


class TestDoScrape:
    """Tests for scrape functions."""

    @patch("cli.cli_app._handler")
    def test_do_scrape(self, mock_handler):
        """Test sequential scrape."""
        from cli.cli_app import do_scrape

        params = {"config_file": "config.json"}
        do_scrape(params)

        mock_handler.scan.assert_called_once_with(config_file="config.json", parallel=False)

    @patch("cli.cli_app._handler")
    def test_do_scrape_parallel(self, mock_handler):
        """Test parallel scrape."""
        from cli.cli_app import do_scrape_parallel

        params = {"config_file": "config.json"}
        do_scrape_parallel(params)

        mock_handler.scan.assert_called_once_with(config_file="config.json", parallel=True)


class TestDoLabel:
    """Tests for labeling functions."""

    def test_do_label(self, capsys):
        """Test automatic labeling placeholder."""
        from cli.cli_app import do_label

        do_label({})

        captured = capsys.readouterr()
        assert "Automatic labeling is performed during scraping" in captured.out

    @patch("cli.cli_app.questionary")
    @patch("cli.cli_app._handler")
    def test_do_label_manual_no_entries(self, mock_handler, mock_questionary, capsys):
        """Test manual labeling with no entries."""
        from cli.cli_app import do_label_manual

        mock_handler.query.return_value = []

        do_label_manual({})

        captured = capsys.readouterr()
        assert "No entries found" in captured.out

    @patch("cli.cli_app.questionary")
    @patch("cli.cli_app._handler")
    def test_do_label_manual_cancel(self, mock_handler, mock_questionary):
        """Test manual labeling cancelled by user."""
        from cli.cli_app import do_label_manual

        mock_handler.query.return_value = [
            {"_id": "test123", "repo": {"url": "https://github.com/test/repo"}, "labels": {"cppcheck": []}}
        ]
        mock_questionary.select.return_value.ask.return_value = "CANCEL"

        do_label_manual({})

        # Should return without error
        mock_handler.label_manual.assert_not_called()


class TestDoExport:
    """Tests for export functions."""

    @patch("cli.cli_app._handler")
    def test_do_export_all(self, mock_handler):
        """Test export all files."""
        from cli.cli_app import do_export_all

        do_export_all({})

        mock_handler.export_all_files.assert_called_once_with("exported_files")

    @patch("cli.cli_app._handler")
    def test_do_export_json(self, mock_handler):
        """Test export JSON."""
        from cli.cli_app import do_export_json

        params = {"output_file": "output.json", "limit": "500"}
        do_export_json(params)

        mock_handler.export_json.assert_called_once_with("output.json", limit=500)

    @patch("cli.cli_app._handler")
    def test_do_export_csv(self, mock_handler):
        """Test export CSV."""
        from cli.cli_app import do_export_csv

        params = {"output_file": "output.csv", "limit": "500"}
        do_export_csv(params)

        mock_handler.export_csv.assert_called_once_with("output.csv", limit=500)


class TestDoQuery:
    """Tests for query function."""

    @patch("cli.cli_app._handler")
    def test_do_query(self, mock_handler):
        """Test query entries."""
        from cli.cli_app import do_query

        params = {"limit": "50", "repo_url": "https://github.com/test/repo"}
        do_query(params)

        mock_handler.query.assert_called_once()


class TestSafeFilename:
    """Tests for _safe_filename function."""

    def test_safe_filename_alphanumeric(self):
        """Test with alphanumeric string."""
        from cli.cli_app import _safe_filename

        result = _safe_filename("test123")

        assert result == "test123"

    def test_safe_filename_with_special_chars(self):
        """Test with special characters."""
        from cli.cli_app import _safe_filename

        result = _safe_filename("test/file:name*?.txt")

        assert result == "testfilename.txt"

    def test_safe_filename_with_dashes_underscores(self):
        """Test with dashes and underscores (allowed)."""
        from cli.cli_app import _safe_filename

        result = _safe_filename("test-file_name.txt")

        assert result == "test-file_name.txt"


class TestCLIApp:
    """Tests for CLIApp class."""

    def test_cli_app_initialization(self):
        """Test CLIApp initialization."""
        from cli.cli_app import CLIApp

        app = CLIApp()

        assert app.root is not None
        assert "scrape" in app.root.children
        assert "scrape-parallel" in app.root.children
        assert "import" in app.root.children
        assert "query" in app.root.children
        assert "export-all" in app.root.children
        assert "export-json" in app.root.children
        assert "export-csv" in app.root.children
        assert "label" in app.root.children
        assert "label-manual" in app.root.children

    def test_cli_app_command_nodes_have_actions(self):
        """Test that command nodes have actions."""
        from cli.cli_app import CLIApp

        app = CLIApp()

        # Check that commands have actions
        assert app.root.children["scrape"].action is not None
        assert app.root.children["export-json"].action is not None
        assert app.root.children["query"].action is not None
