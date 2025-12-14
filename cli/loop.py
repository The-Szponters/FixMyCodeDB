import questionary

from cli.cli_app import CLIApp
from cli.command_tree import CommandNode, custom_style


def run_menu_loop():
    app = CLIApp()
    current_node = app.root

    while True:
        choices = []

        # Option A: If this node is executable, offer to run it
        if current_node.is_command and current_node != app.root:
            choices.append(questionary.Choice(title=f"▶ Run '{current_node.name}'", value="EXECUTE_CURRENT"))
            choices.append(questionary.Separator())

        # Option B: List Children (Sub-commands)
        for child_name in current_node.children:
            choices.append(questionary.Choice(title=child_name, value=current_node.children[child_name]))

        # Option C: Navigation (Back/Exit)
        choices.append(questionary.Separator())
        if current_node.parent:
            choices.append(questionary.Choice(title=".. (Back)", value="BACK"))
            choices.append(questionary.Choice(title="Exit", value="EXIT"))
        else:
            choices.append(questionary.Choice(title="Exit", value="EXIT"))

        # 2. Display the Menu
        # The 'pointer' and 'highlighted' style handles the arrow keys and underlining
        selection = questionary.select(
            message=f"Location: {get_breadcrumbs(current_node)}", choices=choices, style=custom_style, use_indicator=True, instruction="(Use arrow keys)"  # Shows the arrow >
        ).ask()

        # 3. Handle Selection logic
        if selection == "EXIT":
            print("Goodbye.")
            break

        elif selection == "BACK":
            if current_node.parent:
                current_node = current_node.parent

        elif selection == "EXECUTE_CURRENT":
            current_node.execute()

        elif isinstance(selection, CommandNode):
            current_node = selection


def get_breadcrumbs(node):
    path = []
    curr = node
    while curr and curr.name != "root":
        path.append(curr.name)
        curr = curr.parent
    return " / ".join(reversed(path)) or "Root"
