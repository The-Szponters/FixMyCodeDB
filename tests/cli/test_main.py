"""
Unit tests for cli/main.py
Tests argument parsing and command execution.
"""
import pytest
from unittest.mock import patch, MagicMock
import sys


class TestArgumentParser:
    """Tests for argument parser configuration."""

    def test_create_parser(self):
        """Test parser creation."""
        from cli.main import create_parser

        parser = create_parser()

        assert parser.prog == "fixmycodedb"
        assert parser.description is not None

    def test_parse_scrape_argument(self):
        """Test parsing --scrape argument."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--scrape", "config.json"])

        assert args.scrape == "config.json"

    def test_parse_list_all_argument(self):
        """Test parsing --list-all argument."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--list-all"])

        assert args.list_all is True

    def test_parse_list_labels_argument(self):
        """Test parsing --list-labels argument."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--list-labels", "MemError", "LogicError"])

        assert args.list_labels == ["MemError", "LogicError"]

    def test_parse_import_json(self):
        """Test parsing --import-all with --JSON."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--import-all", "./data", "--JSON"])

        assert args.import_all == "./data"
        assert args.json_format is True
        assert args.csv_format is False

    def test_parse_import_csv(self):
        """Test parsing --import-all with --CSV."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--import-all", "./data", "--CSV"])

        assert args.import_all == "./data"
        assert args.csv_format is True
        assert args.json_format is False

    def test_parse_export_all(self):
        """Test parsing --export-all argument."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--export-all", "./backup"])

        assert args.export_all == "./backup"

    def test_parse_export_all_default(self):
        """Test parsing --export-all with default folder."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--export-all"])

        assert args.export_all == "exported_files"

    def test_parse_export_with_labels(self):
        """Test parsing --export-all with --labels."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--export-all", "./backup", "--labels", "MemError"])

        assert args.export_all == "./backup"
        assert args.labels == ["MemError"]

    def test_parse_edit_add_label(self):
        """Test parsing --edit with --add-label."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--edit", "123", "--add-label", "MemError"])

        assert args.edit == "123"
        assert args.add_label == ["MemError"]

    def test_parse_edit_remove_label(self):
        """Test parsing --edit with --remove-label."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--edit", "123", "--remove-label", "LogicError"])

        assert args.edit == "123"
        assert args.remove_label == ["LogicError"]

    def test_parse_no_infra(self):
        """Test parsing --no-infra flag."""
        from cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--list-all", "--no-infra"])

        assert args.no_infra is True

    def test_mutually_exclusive_format(self):
        """Test --JSON and --CSV are mutually exclusive."""
        from cli.main import create_parser

        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--import-all", "./data", "--JSON", "--CSV"])


class TestValidateArgs:
    """Tests for argument validation."""

    def test_validate_conflicting_commands(self):
        """Test validation catches conflicting commands."""
        from cli.main import create_parser, validate_args

        parser = create_parser()

        # Parse with list-all as it's valid
        args = parser.parse_args(["--list-all"])
        # Manually set conflicting values
        args.scrape = "config.json"

        # parser.error() causes SystemExit
        with pytest.raises(SystemExit):
            validate_args(args, parser)

    def test_validate_edit_without_labels(self):
        """Test validation catches --edit without label flags."""
        from cli.main import create_parser, validate_args

        parser = create_parser()
        args = parser.parse_args(["--edit", "123"])

        # parser.error() causes SystemExit
        with pytest.raises(SystemExit):
            validate_args(args, parser)

    def test_validate_labels_without_export(self):
        """Test validation catches --labels without --export-all."""
        from cli.main import create_parser, validate_args

        parser = create_parser()
        args = parser.parse_args(["--list-all"])
        args.labels = ["MemError"]  # Manually set

        # parser.error() causes SystemExit
        with pytest.raises(SystemExit):
            validate_args(args, parser)


class TestManageInfrastructure:
    """Tests for infrastructure management."""

    def test_manage_infrastructure_success(self, tmp_path):
        """Test successful docker compose command."""
        from cli.main import manage_infrastructure

        with patch('cli.main.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            # Should not raise
            manage_infrastructure("up -d", str(tmp_path))

            mock_run.assert_called_once()

    def test_manage_infrastructure_docker_error(self, tmp_path):
        """Test docker command failure."""
        from cli.main import manage_infrastructure
        import subprocess

        with patch('cli.main.subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "docker", stderr=b"error message"
            )

            with pytest.raises(SystemExit):
                manage_infrastructure("up -d", str(tmp_path))

    def test_manage_infrastructure_docker_not_found(self, tmp_path):
        """Test docker not installed."""
        from cli.main import manage_infrastructure

        with patch('cli.main.subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()

            with pytest.raises(SystemExit):
                manage_infrastructure("up -d", str(tmp_path))


class TestMainExecution:
    """Tests for main function execution."""

    def test_main_no_args_interactive(self):
        """Test main with no args starts interactive mode."""
        from cli.main import main

        with patch('cli.main.run_menu_loop') as mock_loop, \
             patch('cli.main.manage_infrastructure') as mock_infra, \
             patch('cli.main.os.path.dirname', return_value="/test"):

            with patch.object(sys, 'argv', ['fixmycodedb', '--no-infra']):
                with pytest.raises(SystemExit) as exc_info:
                    main()

            assert exc_info.value.code == 0
            mock_loop.assert_called_once()

    def test_main_list_all(self):
        """Test main with --list-all."""
        from cli.main import main

        with patch('cli.main.handle_list_all', return_value=0) as mock_handler, \
             patch('cli.main.manage_infrastructure'), \
             patch('cli.main.os.path.dirname', return_value="/test"):

            with patch.object(sys, 'argv', ['fixmycodedb', '--list-all', '--no-infra']):
                with pytest.raises(SystemExit) as exc_info:
                    main()

            assert exc_info.value.code == 0
            mock_handler.assert_called_once()

    def test_main_scrape(self):
        """Test main with --scrape."""
        from cli.main import main

        with patch('cli.main.handle_scrape', return_value=0) as mock_handler, \
             patch('cli.main.manage_infrastructure'), \
             patch('cli.main.os.path.dirname', return_value="/test"):

            with patch.object(sys, 'argv', ['fixmycodedb', '--scrape', 'config.json', '--no-infra']):
                with pytest.raises(SystemExit) as exc_info:
                    main()

            assert exc_info.value.code == 0
            mock_handler.assert_called_once_with("config.json")

    def test_main_export_json(self):
        """Test main with --export-all --JSON."""
        from cli.main import main

        with patch('cli.main.handle_export_all', return_value=0) as mock_handler, \
             patch('cli.main.manage_infrastructure'), \
             patch('cli.main.os.path.dirname', return_value="/test"):

            with patch.object(sys, 'argv', ['fixmycodedb', '--export-all', './out', '--JSON', '--no-infra']):
                with pytest.raises(SystemExit) as exc_info:
                    main()

            assert exc_info.value.code == 0
            mock_handler.assert_called_once()
