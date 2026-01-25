"""
Unit tests for cli/command_tree.py
Tests the CommandNode and CommandTree classes.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestCommandNode:
    """Tests for CommandNode class."""

    def test_create_node(self):
        """Test creating a command node."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")

        assert node.name == "test"
        assert node.children == {}
        assert node.parent is None
        assert node.is_command is False
        assert node.param_set == {}
        assert node.action is None

    def test_create_node_with_parent(self):
        """Test creating a node with parent."""
        from cli.command_tree import CommandNode

        parent = CommandNode("parent")
        child = CommandNode("child", parent=parent)

        assert child.parent == parent

    def test_add_child(self):
        """Test adding child node."""
        from cli.command_tree import CommandNode

        parent = CommandNode("parent")
        child = CommandNode("child")

        parent.add_child(child)

        assert "child" in parent.children
        assert parent.children["child"] == child
        assert child.parent == parent

    def test_get_child(self):
        """Test getting child by name."""
        from cli.command_tree import CommandNode

        parent = CommandNode("parent")
        child = CommandNode("child")
        parent.add_child(child)

        result = parent.get_child("child")

        assert result == child

    def test_get_child_not_found(self):
        """Test getting non-existent child."""
        from cli.command_tree import CommandNode

        parent = CommandNode("parent")

        result = parent.get_child("missing")

        assert result is None

    def test_repr(self):
        """Test node string representation."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")

        result = repr(node)

        assert "<Node: test>" == result

    def test_execute_with_action(self):
        """Test executing node with action."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")
        node.is_command = True
        mock_action = MagicMock()
        node.action = mock_action

        with patch('cli.command_tree.questionary.press_any_key_to_continue') as mock_press:
            mock_press.return_value.ask.return_value = None
            node.execute()

        mock_action.assert_called_once()

    def test_execute_without_action(self, capsys):
        """Test executing node without action."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")
        node.is_command = True

        node.execute()

        captured = capsys.readouterr()
        assert "Error: No action bound" in captured.out

    def test_collect_params_empty(self):
        """Test collecting params when empty."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")

        result = node.collect_params()

        assert result == {}

    def test_collect_params_with_values(self):
        """Test collecting params with user input."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")
        node.param_set = {"path": "./data", "format": "json"}

        with patch('cli.command_tree.questionary.text') as mock_text:
            mock_text.return_value.ask.side_effect = ["./output", "csv"]
            result = node.collect_params()

        assert result["path"] == "./output"
        assert result["format"] == "csv"


class TestCommandTree:
    """Tests for CommandTree class."""

    def test_create_tree(self):
        """Test creating a command tree."""
        from cli.command_tree import CommandTree

        tree = CommandTree()

        assert tree.root is not None
        assert tree.root.name == "root"

    def test_add_command_simple(self):
        """Test adding a simple command."""
        from cli.command_tree import CommandTree

        tree = CommandTree()
        mock_action = MagicMock()

        tree.add_command("Scrape", action=mock_action)

        assert "Scrape" in tree.root.children
        assert tree.root.children["Scrape"].is_command is True
        assert tree.root.children["Scrape"].action == mock_action

    def test_add_command_nested(self):
        """Test adding a nested command."""
        from cli.command_tree import CommandTree

        tree = CommandTree()
        mock_action = MagicMock()

        tree.add_command("Data Export", action=mock_action)

        assert "Data" in tree.root.children
        data_node = tree.root.children["Data"]
        assert "Export" in data_node.children
        assert data_node.children["Export"].is_command is True

    def test_add_command_with_params(self):
        """Test adding command with parameters."""
        from cli.command_tree import CommandTree

        tree = CommandTree()
        params = {"path": "./data"}

        tree.add_command("Export", action=MagicMock(), param_set=params)

        export_node = tree.root.children["Export"]
        assert export_node.param_set == params

    def test_add_multiple_commands_shared_parent(self):
        """Test adding multiple commands with shared parent."""
        from cli.command_tree import CommandTree

        tree = CommandTree()

        tree.add_command("Data Import", action=MagicMock())
        tree.add_command("Data Export", action=MagicMock())

        data_node = tree.root.children["Data"]
        assert "Import" in data_node.children
        assert "Export" in data_node.children


class TestCustomStyle:
    """Tests for custom_style questionary style."""

    def test_custom_style_exists(self):
        """Test custom_style is defined."""
        from cli.command_tree import custom_style

        assert custom_style is not None
