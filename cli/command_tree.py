from typing import Callable, Optional, Dict, Any
import questionary


# Define the visual style (Underlining the selected option)
custom_style = questionary.Style([
    ('qmark', 'fg:#E91E63 bold'),       # Token for the question mark
    ('question', 'bold'),               # Token for the question text
    ('answer', 'fg:#2196f3 bold'),      # Token for the answer
    ('pointer', 'fg:#673ab7 bold'),     # Token for the pointer
    ('highlighted', 'fg:#673ab7 bold underline'),  # <--- UNDERLINE SELECTED
    ('selected', 'fg:#cc5454'),         # Token for the selected item
    ('separator', 'fg:#cc5454'),
    ('instruction', ''),                # Token for the instruction
    ('text', ''),                       # Token for the plain text
])


class CommandNode:
    def __init__(self, name, parent=None):
        self.name = name
        self.children = {}
        self.parent = parent
        self.is_command = False
        self.param_set: Dict[str, Any] = {}
        self.action: Optional[Callable] = None

    def add_child(self, child_node):
        self.children[child_node.name] = child_node
        child_node.parent = self

    def get_child(self, name):
        return self.children.get(name)

    def execute(self):
        """Executes the bound action if it exists."""
        if self.action:
            params = self.collect_params()
            print(f"\n[*] Executing: {self.name}...\n")
            self.action(params)

            questionary.press_any_key_to_continue().ask()
        else:
            print(f"Error: No action bound to command '{self.name}'")

    def collect_params(self):
        """Interactive prompt for parameters using Questionary."""
        if not self.param_set:
            return {}

        print(f"\n--- Configure {self.name} ---")
        new_params = {}
        for key, default in self.param_set.items():
            # Use text input with default value
            val = questionary.text(
                f"Enter {key}:",
                default=str(default),
                style=custom_style
            ).ask()

            if val is not None:
                new_params[key] = val

        return new_params

    def __repr__(self):
        return f"<Node: {self.name}>"


class CommandTree:
    def __init__(self):
        self.root = CommandNode("root")

    def add_command(self, command_path, action: Callable = None, param_set: Optional[set] = None):
        parts = command_path.split()
        node = self.root

        for part in parts:
            if part not in node.children:
                new_node = CommandNode(part, parent=node)
                node.add_child(new_node)
            node = node.get_child(part)

        node.is_command = True
        node.action = action

        if param_set:
            node.param_set = param_set
