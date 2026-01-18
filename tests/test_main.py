"""
Tests for cli/main.py module.
"""

import pytest
import sys
from unittest.mock import patch, MagicMock


class TestManageInfrastructure:
    """Tests for manage_infrastructure function."""

    @patch("cli.main.subprocess.run")
    def test_manage_infrastructure_success(self, mock_run):
        """Test successful docker command."""
        from cli.main import manage_infrastructure

        mock_run.return_value = MagicMock(returncode=0)

        # Should not raise
        manage_infrastructure("up -d", "/test/dir")

        mock_run.assert_called_once()

    @patch("cli.main.subprocess.run")
    def test_manage_infrastructure_failure(self, mock_run):
        """Test failed docker command."""
        from cli.main import manage_infrastructure
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(
            1, "docker compose", stderr=b"Error message"
        )

        with pytest.raises(SystemExit) as exc_info:
            manage_infrastructure("up -d", "/test/dir")

        assert exc_info.value.code == 1

    @patch("cli.main.subprocess.run")
    def test_manage_infrastructure_docker_not_found(self, mock_run):
        """Test docker not found."""
        from cli.main import manage_infrastructure

        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(SystemExit) as exc_info:
            manage_infrastructure("up -d", "/test/dir")

        assert exc_info.value.code == 1


class TestRunCliCommand:
    """Tests for run_cli_command function."""

    def test_run_cli_command_scan(self):
        """Test scan command."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=True,
            config="config.json",
            parallel=False,
            repo_url=None,
            target_count=None,
            api_url="http://localhost:8000",
            verbose=False,
            export=None,
            label_manual=False,
            query=False,
            import_data=False,
        )

        with patch("cli.main.CommandHandler") as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler.scan.return_value = True
            mock_handler_class.return_value = mock_handler

            result = run_cli_command(args)

            assert result == 0
            mock_handler.scan.assert_called_once()

    def test_run_cli_command_scan_failure(self):
        """Test scan command failure."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=True,
            config="config.json",
            parallel=True,
            repo_url=None,
            target_count=None,
            api_url="http://localhost:8000",
            verbose=False,
            export=None,
            label_manual=False,
            query=False,
            import_data=False,
        )

        with patch("cli.main.CommandHandler") as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler.scan.return_value = False
            mock_handler_class.return_value = mock_handler

            result = run_cli_command(args)

            assert result == 1

    def test_run_cli_command_export_json(self):
        """Test export JSON command."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=False,
            export="json",
            output="data.json",
            limit=100,
            api_url="http://localhost:8000",
            verbose=False,
            label_manual=False,
            query=False,
            import_data=False,
            repo_url=None,
            commit_hash=None,
            code_hash=None,
            memory_management=None,
        )

        with patch("cli.main.CommandHandler") as mock_handler_class:
            with patch("cli.main.build_filter_dict") as mock_build_filter:
                mock_handler = MagicMock()
                mock_handler.export_json.return_value = True
                mock_handler_class.return_value = mock_handler
                mock_build_filter.return_value = {}

                result = run_cli_command(args)

                assert result == 0
                mock_handler.export_json.assert_called_once()

    def test_run_cli_command_export_csv(self):
        """Test export CSV command."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=False,
            export="csv",
            output=None,  # Should default to export.csv
            limit=100,
            api_url="http://localhost:8000",
            verbose=False,
            label_manual=False,
            query=False,
            import_data=False,
            repo_url=None,
            commit_hash=None,
            code_hash=None,
            memory_management=None,
        )

        with patch("cli.main.CommandHandler") as mock_handler_class:
            with patch("cli.main.build_filter_dict") as mock_build_filter:
                mock_handler = MagicMock()
                mock_handler.export_csv.return_value = True
                mock_handler_class.return_value = mock_handler
                mock_build_filter.return_value = {}

                result = run_cli_command(args)

                assert result == 0
                mock_handler.export_csv.assert_called_once()

    def test_run_cli_command_label_manual_missing_id(self):
        """Test label manual without ID."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=False,
            export=None,
            label_manual=True,
            id=None,
            set_label=None,
            remove_label=None,
            api_url="http://localhost:8000",
            verbose=False,
            query=False,
            import_data=False,
        )

        with patch("cli.main.CommandHandler"):
            result = run_cli_command(args)

            assert result == 1

    def test_run_cli_command_label_manual_add(self):
        """Test label manual add."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=False,
            export=None,
            label_manual=True,
            id="test123",
            set_label="memoryLeak",
            remove_label=None,
            api_url="http://localhost:8000",
            verbose=False,
            query=False,
            import_data=False,
        )

        with patch("cli.main.CommandHandler") as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler.label_manual.return_value = True
            mock_handler_class.return_value = mock_handler

            result = run_cli_command(args)

            assert result == 0
            mock_handler.label_manual.assert_called_once_with("test123", "memoryLeak", remove=False)

    def test_run_cli_command_label_manual_remove(self):
        """Test label manual remove."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=False,
            export=None,
            label_manual=True,
            id="test123",
            set_label=None,
            remove_label="memoryLeak",
            api_url="http://localhost:8000",
            verbose=False,
            query=False,
            import_data=False,
        )

        with patch("cli.main.CommandHandler") as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler.label_manual.return_value = True
            mock_handler_class.return_value = mock_handler

            result = run_cli_command(args)

            assert result == 0
            mock_handler.label_manual.assert_called_once_with("test123", "memoryLeak", remove=True)

    def test_run_cli_command_label_manual_missing_action(self):
        """Test label manual without set or remove."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=False,
            export=None,
            label_manual=True,
            id="test123",
            set_label=None,
            remove_label=None,
            api_url="http://localhost:8000",
            verbose=False,
            query=False,
            import_data=False,
        )

        with patch("cli.main.CommandHandler"):
            result = run_cli_command(args)

            assert result == 1

    def test_run_cli_command_query(self):
        """Test query command."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=False,
            export=None,
            label_manual=False,
            query=True,
            limit=50,
            api_url="http://localhost:8000",
            verbose=False,
            import_data=False,
            repo_url=None,
            commit_hash=None,
            code_hash=None,
            memory_management=None,
        )

        with patch("cli.main.CommandHandler") as mock_handler_class:
            with patch("cli.main.build_filter_dict") as mock_build_filter:
                mock_handler = MagicMock()
                mock_handler.query.return_value = [{"_id": "test"}]
                mock_handler_class.return_value = mock_handler
                mock_build_filter.return_value = {}

                result = run_cli_command(args)

                assert result == 0
                mock_handler.query.assert_called_once()

    def test_run_cli_command_import_data(self):
        """Test import data command."""
        from cli.main import run_cli_command
        from argparse import Namespace

        args = Namespace(
            scan=False,
            export=None,
            label_manual=False,
            query=False,
            import_data=True,
            output=None,
            limit=100,
            api_url="http://localhost:8000",
            verbose=False,
            repo_url=None,
            commit_hash=None,
            code_hash=None,
            memory_management=None,
        )

        with patch("cli.main.CommandHandler") as mock_handler_class:
            with patch("cli.main.build_filter_dict") as mock_build_filter:
                mock_handler = MagicMock()
                mock_handler.export_json.return_value = True
                mock_handler_class.return_value = mock_handler
                mock_build_filter.return_value = {}

                result = run_cli_command(args)

                assert result == 0


class TestMain:
    """Tests for main function."""

    @patch("cli.main.run_menu_loop")
    @patch("cli.main.manage_infrastructure")
    @patch("cli.main.parse_args")
    @patch("cli.main.has_action_args")
    def test_main_interactive_mode(self, mock_has_action, mock_parse, mock_infra, mock_loop):
        """Test main in interactive mode."""
        from cli.main import main
        from argparse import Namespace

        mock_parse.return_value = Namespace(
            interactive=True,
            no_docker=False,
        )
        mock_has_action.return_value = False

        main()

        mock_infra.assert_called()
        mock_loop.assert_called_once()

    @patch("cli.main.run_cli_command")
    @patch("cli.main.manage_infrastructure")
    @patch("cli.main.parse_args")
    @patch("cli.main.has_action_args")
    def test_main_command_mode(self, mock_has_action, mock_parse, mock_infra, mock_cli):
        """Test main in command mode."""
        from cli.main import main
        from argparse import Namespace

        mock_parse.return_value = Namespace(
            interactive=False,
            no_docker=False,
            scan=True,
        )
        mock_has_action.return_value = True
        mock_cli.return_value = 0

        main()

        mock_cli.assert_called_once()

    @patch("cli.main.run_menu_loop")
    @patch("cli.main.manage_infrastructure")
    @patch("cli.main.parse_args")
    @patch("cli.main.has_action_args")
    def test_main_no_docker(self, mock_has_action, mock_parse, mock_infra, mock_loop):
        """Test main with --no-docker flag."""
        from cli.main import main
        from argparse import Namespace

        mock_parse.return_value = Namespace(
            interactive=True,
            no_docker=True,
        )
        mock_has_action.return_value = False

        main()

        # manage_infrastructure should not be called for startup
        # It's still called on cleanup, so we check it wasn't called with 'up'
        for call in mock_infra.call_args_list:
            assert "up" not in call[0][0]

    @patch("cli.main.run_menu_loop")
    @patch("cli.main.manage_infrastructure")
    @patch("cli.main.parse_args")
    @patch("cli.main.has_action_args")
    def test_main_keyboard_interrupt(self, mock_has_action, mock_parse, mock_infra, mock_loop):
        """Test main handles keyboard interrupt."""
        from cli.main import main
        from argparse import Namespace

        mock_parse.return_value = Namespace(
            interactive=True,
            no_docker=False,
        )
        mock_has_action.return_value = False
        mock_loop.side_effect = KeyboardInterrupt()

        # Should not raise
        main()
