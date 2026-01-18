"""
Tests for cli/loop.py module.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestGetBreadcrumbs:
    """Tests for get_breadcrumbs function."""

    def test_root_node(self):
        """Test breadcrumbs for root node."""
        from cli.loop import get_breadcrumbs
        from cli.command_tree import CommandNode

        root = CommandNode("root")

        result = get_breadcrumbs(root)

        assert result == "Root"

    def test_single_level(self):
        """Test breadcrumbs for single level."""
        from cli.loop import get_breadcrumbs
        from cli.command_tree import CommandNode

        root = CommandNode("root")
        child = CommandNode("scrape")
        child.parent = root

        result = get_breadcrumbs(child)

        assert result == "scrape"

    def test_multi_level(self):
        """Test breadcrumbs for multiple levels."""
        from cli.loop import get_breadcrumbs
        from cli.command_tree import CommandNode

        root = CommandNode("root")
        parent = CommandNode("parent")
        parent.parent = root
        child = CommandNode("child")
        child.parent = parent

        result = get_breadcrumbs(child)

        assert result == "parent / child"


class TestRunMenuLoop:
    """Tests for run_menu_loop function."""

    @patch("cli.loop.questionary")
    @patch("cli.loop.CLIApp")
    def test_run_menu_loop_exit(self, mock_cli_app, mock_questionary):
        """Test menu loop exits on EXIT."""
        from cli.loop import run_menu_loop

        # Setup mock
        mock_app = MagicMock()
        mock_app.root.is_command = False
        mock_app.root.children = {}
        mock_app.root.parent = None
        mock_cli_app.return_value = mock_app
        mock_questionary.select.return_value.ask.return_value = "EXIT"

        # Run
        run_menu_loop()

        # Verify select was called
        mock_questionary.select.assert_called()

    @patch("cli.loop.questionary")
    @patch("cli.loop.CLIApp")
    def test_run_menu_loop_navigate_back(self, mock_cli_app, mock_questionary):
        """Test menu loop navigates back."""
        from cli.loop import run_menu_loop
        from cli.command_tree import CommandNode

        # Setup mock
        mock_app = MagicMock()
        root = CommandNode("root")
        child = CommandNode("child")
        root.add_child(child)

        mock_app.root = root
        mock_cli_app.return_value = mock_app

        # First call returns child node, second returns BACK, third returns EXIT
        mock_questionary.select.return_value.ask.side_effect = [child, "BACK", "EXIT"]

        # Run
        run_menu_loop()

    @patch("cli.loop.questionary")
    @patch("cli.loop.CLIApp")
    def test_run_menu_loop_execute_command(self, mock_cli_app, mock_questionary):
        """Test menu loop executes command."""
        from cli.loop import run_menu_loop
        from cli.command_tree import CommandNode

        # Setup mock
        mock_app = MagicMock()
        root = CommandNode("root")
        child = CommandNode("test")
        child.is_command = True
        child.action = MagicMock()
        root.add_child(child)

        mock_app.root = root
        mock_cli_app.return_value = mock_app

        # Navigate to child, execute, then exit
        mock_questionary.select.return_value.ask.side_effect = [child, "EXECUTE_CURRENT", "EXIT"]
        mock_questionary.press_any_key_to_continue.return_value.ask.return_value = None

        # Run
        run_menu_loop()

        # Verify action was called
        child.action.assert_called_once()
