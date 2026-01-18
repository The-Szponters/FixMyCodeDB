import argparse
import os
import subprocess  # nosec B404
import sys

from cli.loop import run_menu_loop
from cli.handlers import (
    handle_scrape,
    handle_list_all,
    handle_list_labels,
    handle_import_all,
    handle_export_all,
    handle_edit_labels,
)


def manage_infrastructure(command, working_dir):
    """
    Runs docker compose commands securely using subprocess.
    """
    try:
        cmd = ["docker", "compose"] + command.split()

        subprocess.run(cmd, cwd=working_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)  # nosec B603
    except subprocess.CalledProcessError as e:
        print(f"\n[!] Error executing Docker command: {' '.join(cmd)}")
        print(f"[!] Docker Output: {e.stderr.decode().strip()}")
        sys.exit(1)
    except FileNotFoundError:
        print("\n[!] Error: 'docker' command not found. Is Docker installed and in your PATH?")
        sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="fixmycodedb",
        description="FixMyCodeDB CLI - Manage code entries and scraping operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Start interactive menu
  %(prog)s --scrape config.json               # Scrape with config file
  %(prog)s --list-all                         # List all entries
  %(prog)s --list-labels MemError LogicError  # List entries with specific labels
  %(prog)s --import-all ./data --JSON         # Import JSON files from folder
  %(prog)s --export-all ./backup --CSV        # Export all entries as CSV
  %(prog)s --export-all ./backup --labels MemError --JSON  # Export filtered entries
  %(prog)s --edit 507f1f77bcf86cd799439011 --add-label MemError
  %(prog)s --edit 507f1f77bcf86cd799439011 --remove-label LogicError
        """,
    )

    # Scrape command
    parser.add_argument(
        "--scrape",
        metavar="CONFIG_PATH",
        help="Scrape using the specified config file (connects to scraper socket)",
    )

    # List commands
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List all entries (displays _id and labels)",
    )

    parser.add_argument(
        "--list-labels",
        nargs="+",
        metavar="LABEL",
        help="List entries matching all specified labels (e.g., MemError LogicError)",
    )

    # Import/Export commands
    parser.add_argument(
        "--import-all",
        metavar="FOLDER_PATH",
        help="Import all files from the specified folder",
    )

    parser.add_argument(
        "--export-all",
        metavar="FOLDER_PATH",
        nargs="?",
        const="exported_files",
        help="Export all entries to the specified folder (default: exported_files)",
    )

    # Format flags for import/export
    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument(
        "--JSON",
        action="store_true",
        dest="json_format",
        help="Use JSON format for import/export",
    )
    format_group.add_argument(
        "--CSV",
        action="store_true",
        dest="csv_format",
        help="Use CSV format for import/export",
    )

    # Labels filter for export
    parser.add_argument(
        "--labels",
        nargs="+",
        metavar="LABEL",
        help="Filter by labels when exporting (use with --export-all)",
    )

    # Edit command
    parser.add_argument(
        "--edit",
        metavar="ENTRY_ID",
        help="Edit the entry with the specified ID",
    )

    parser.add_argument(
        "--add-label",
        nargs="+",
        metavar="LABEL",
        help="Add labels to the entry (use with --edit)",
    )

    parser.add_argument(
        "--remove-label",
        nargs="+",
        metavar="LABEL",
        help="Remove labels from the entry (use with --edit)",
    )

    # Infrastructure control
    parser.add_argument(
        "--no-infra",
        action="store_true",
        help="Skip starting/stopping infrastructure (assumes it's already running)",
    )

    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> bool:
    """Validate argument combinations."""
    # Check for conflicting commands
    commands = [
        args.scrape is not None,
        args.list_all,
        args.list_labels is not None,
        args.import_all is not None,
        args.export_all is not None,
        args.edit is not None,
    ]
    if sum(commands) > 1:
        parser.error("Cannot use multiple commands at once. Use one of: --scrape, --list-all, --list-labels, --import-all, --export-all, --edit")
        return False

    # Validate import-all requires format
    if args.import_all and not (args.json_format or args.csv_format):
        parser.error("--import-all requires --JSON or --CSV format flag")
        return False

    # Validate export-all requires format
    if args.export_all and not (args.json_format or args.csv_format):
        parser.error("--export-all requires --JSON or --CSV format flag")
        return False

    # Validate --labels only with export-all
    if args.labels and not args.export_all:
        parser.error("--labels can only be used with --export-all")
        return False

    # Validate edit requires add-label or remove-label
    if args.edit and not (args.add_label or args.remove_label):
        parser.error("--edit requires --add-label or --remove-label")
        return False

    # Validate add-label/remove-label require edit
    if (args.add_label or args.remove_label) and not args.edit:
        parser.error("--add-label and --remove-label require --edit")
        return False

    return True


def run_command(args: argparse.Namespace) -> int:
    """Execute the appropriate command based on parsed arguments."""
    if args.scrape:
        return handle_scrape(args.scrape)

    if args.list_all:
        return handle_list_all()

    if args.list_labels:
        return handle_list_labels(args.list_labels)

    if args.import_all:
        format_type = "JSON" if args.json_format else "CSV"
        return handle_import_all(args.import_all, format_type)

    if args.export_all:
        format_type = "JSON" if args.json_format else "CSV"
        return handle_export_all(args.export_all, format_type, args.labels)

    if args.edit:
        return handle_edit_labels(args.edit, args.add_label, args.remove_label)

    return 0


def has_cli_commands(args: argparse.Namespace) -> bool:
    """Check if any CLI command was specified."""
    return any([
        args.scrape is not None,
        args.list_all,
        args.list_labels is not None,
        args.import_all is not None,
        args.export_all is not None,
        args.edit is not None,
    ])


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Validate argument combinations
    if has_cli_commands(args) and not validate_args(args, parser):
        sys.exit(1)

    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_script_dir, os.pardir))

    # Start infrastructure unless --no-infra is set
    if not args.no_infra:
        print("Starting FixMyCodeDB Infrastructure...")
        manage_infrastructure("up -d --build --wait", project_root)
        print("Infrastructure started successfully.")

    exit_code = 0
    try:
        if has_cli_commands(args):
            # Run the specified command
            exit_code = run_command(args)
        else:
            # No arguments provided - run interactive menu
            run_menu_loop()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        exit_code = 130
    finally:
        if not args.no_infra:
            print("Stopping app services (keeping MongoDB running)...")
            manage_infrastructure("stop fastapi scraper", project_root)
            print("MongoDB left running. To stop it: docker compose stop mongo")

        print("Exiting. Goodbye!")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
