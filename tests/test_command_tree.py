"""
Tests for cli/command_tree.py module.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestCommandNode:
    """Tests for CommandNode class."""

    def test_node_initialization(self):
        """Test basic node initialization."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")

        assert node.name == "test"
        assert node.parent is None
        assert node.children == {}
        assert node.is_command is False
        assert node.param_set == {}
        assert node.action is None

    def test_node_with_parent(self):
        """Test node with parent."""
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
        """Test getting child node."""
        from cli.command_tree import CommandNode

        parent = CommandNode("parent")
        child = CommandNode("child")
        parent.add_child(child)

        result = parent.get_child("child")

        assert result == child

    def test_get_child_not_found(self):
        """Test getting non-existent child."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")

        result = node.get_child("nonexistent")

        assert result is None

    @patch("cli.command_tree.questionary")
    def test_execute_with_action(self, mock_questionary):
        """Test executing node with action."""
        from cli.command_tree import CommandNode

        mock_action = MagicMock()
        node = CommandNode("test")
        node.action = mock_action
        node.is_command = True
        mock_questionary.press_any_key_to_continue.return_value.ask.return_value = None

        node.execute()

        mock_action.assert_called_once_with({})

    def test_execute_without_action(self, capsys):
        """Test executing node without action."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")

        node.execute()

        captured = capsys.readouterr()
        assert "No action bound to command" in captured.out

    @patch("cli.command_tree.questionary")
    def test_collect_params_empty(self, mock_questionary):
        """Test collecting params when empty."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")

        result = node.collect_params()

        assert result == {}

    @patch("cli.command_tree.questionary")
    def test_collect_params_with_values(self, mock_questionary):
        """Test collecting params with param_set."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")
        node.param_set = {"param1": "default1", "param2": "default2"}

        mock_questionary.text.return_value.ask.side_effect = ["value1", "value2"]

        result = node.collect_params()

        assert result == {"param1": "value1", "param2": "value2"}

    def test_repr(self):
        """Test string representation."""
        from cli.command_tree import CommandNode

        node = CommandNode("test")

        assert repr(node) == "<Node: test>"


class TestCommandTree:
    """Tests for CommandTree class."""

    def test_tree_initialization(self):
        """Test tree initialization."""
        from cli.command_tree import CommandTree

        tree = CommandTree()

        assert tree.root is not None
        assert tree.root.name == "root"

    def test_add_simple_command(self):
        """Test adding a simple command."""
        from cli.command_tree import CommandTree

        tree = CommandTree()
        action = MagicMock()

        tree.add_command("test", action)

        assert "test" in tree.root.children
        assert tree.root.children["test"].action == action
        assert tree.root.children["test"].is_command is True

    def test_add_nested_command(self):
        """Test adding a nested command."""
        from cli.command_tree import CommandTree

        tree = CommandTree()
        action = MagicMock()

        tree.add_command("parent child", action)

        assert "parent" in tree.root.children
        assert "child" in tree.root.children["parent"].children
        assert tree.root.children["parent"].children["child"].action == action

    def test_add_command_with_params(self):
        """Test adding command with parameters."""
        from cli.command_tree import CommandTree

        tree = CommandTree()
        action = MagicMock()
        params = {"file": "default.txt", "limit": "100"}

        tree.add_command("test", action, param_set=params)

        assert tree.root.children["test"].param_set == params

    def test_add_multiple_commands_same_parent(self):
        """Test adding multiple commands under same parent."""
        from cli.command_tree import CommandTree

        tree = CommandTree()
        action1 = MagicMock()
        action2 = MagicMock()

        tree.add_command("parent cmd1", action1)
        tree.add_command("parent cmd2", action2)

        assert "cmd1" in tree.root.children["parent"].children
        assert "cmd2" in tree.root.children["parent"].children


class TestCustomStyle:
    """Tests for custom style."""

    def test_custom_style_exists(self):
        """Test that custom_style is defined."""
        from cli.command_tree import custom_style

        assert custom_style is not None
