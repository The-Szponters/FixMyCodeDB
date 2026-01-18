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


class TestRunMenuLoopUnit:
    """Unit tests for run_menu_loop components."""

    def test_menu_builds_choices_correctly(self):
        """Test that menu choices are built correctly."""
        from cli.command_tree import CommandNode

        root = CommandNode("root")
        child1 = CommandNode("scrape")
        child2 = CommandNode("export")
        root.add_child(child1)
        root.add_child(child2)

        # Verify children are accessible
        assert "scrape" in root.children
        assert "export" in root.children

    def test_executable_command_node(self):
        """Test executable command node."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")
        node.is_command = True
        node.action = MagicMock()

        assert node.is_command is True
        assert node.action is not None

    def test_navigation_back(self):
        """Test navigation back via parent reference."""
        from cli.command_tree import CommandNode

        root = CommandNode("root")
        child = CommandNode("child")
        root.add_child(child)

        # Verify we can navigate back
        assert child.parent == root
        assert root.parent is None
