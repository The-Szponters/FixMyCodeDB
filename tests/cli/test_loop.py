"""
Unit tests for cli/loop.py
Tests the interactive menu loop functions.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestGetBreadcrumbs:
    """Tests for get_breadcrumbs function."""

    def test_breadcrumbs_root(self):
        """Test breadcrumbs at root returns Root."""
        from cli.loop import get_breadcrumbs

        mock_node = MagicMock()
        mock_node.name = "root"
        mock_node.parent = None

        result = get_breadcrumbs(mock_node)

        assert result == "Root"

    def test_breadcrumbs_one_level(self):
        """Test breadcrumbs one level deep."""
        from cli.loop import get_breadcrumbs

        mock_parent = MagicMock()
        mock_parent.name = "root"
        mock_parent.parent = None

        mock_node = MagicMock()
        mock_node.name = "Scrape"
        mock_node.parent = mock_parent

        result = get_breadcrumbs(mock_node)

        assert result == "Scrape"

    def test_breadcrumbs_multi_level(self):
        """Test breadcrumbs multiple levels deep."""
        from cli.loop import get_breadcrumbs

        mock_root = MagicMock()
        mock_root.name = "root"
        mock_root.parent = None

        mock_parent = MagicMock()
        mock_parent.name = "Data"
        mock_parent.parent = mock_root

        mock_node = MagicMock()
        mock_node.name = "Export"
        mock_node.parent = mock_parent

        result = get_breadcrumbs(mock_node)

        assert result == "Data / Export"


class TestRunMenuLoop:
    """Tests for run_menu_loop function."""

    def test_menu_loop_exit(self):
        """Test menu loop exits on EXIT selection."""
        from cli.loop import run_menu_loop

        with patch('cli.loop.CLIApp') as mock_app_class, \
             patch('cli.loop.questionary.select') as mock_select:

            mock_app = MagicMock()
            mock_root = MagicMock()
            mock_root.children = {}
            mock_root.parent = None
            mock_root.name = "root"
            mock_root.is_command = False
            mock_app.root = mock_root
            mock_app_class.return_value = mock_app

            # Simulate EXIT selection
            mock_select.return_value.ask.return_value = "EXIT"

            run_menu_loop()

            mock_select.assert_called()

    def test_menu_loop_keyboard_interrupt(self):
        """Test menu loop handles keyboard interrupt."""
        from cli.loop import run_menu_loop

        with patch('cli.loop.CLIApp') as mock_app_class, \
             patch('cli.loop.questionary.select') as mock_select:

            mock_app = MagicMock()
            mock_root = MagicMock()
            mock_root.children = {}
            mock_root.parent = None
            mock_root.name = "root"
            mock_root.is_command = False
            mock_app.root = mock_root
            mock_app_class.return_value = mock_app

            # Simulate KeyboardInterrupt
            mock_select.side_effect = KeyboardInterrupt()

            run_menu_loop()

            # Should exit gracefully
            mock_select.assert_called()

    def test_menu_loop_back_navigation(self):
        """Test menu loop back navigation."""
        from cli.loop import run_menu_loop

        with patch('cli.loop.CLIApp') as mock_app_class, \
             patch('cli.loop.questionary.select') as mock_select:

            mock_app = MagicMock()
            mock_root = MagicMock()
            mock_root.children = {}
            mock_root.parent = None
            mock_root.name = "root"
            mock_root.is_command = False
            mock_app.root = mock_root
            mock_app_class.return_value = mock_app

            # Simulate BACK then EXIT
            mock_select.return_value.ask.side_effect = ["BACK", "EXIT"]

            run_menu_loop()

            assert mock_select.call_count >= 1
