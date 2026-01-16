#!/usr/bin/env python3
"""
FixMyCodeDB CLI - Main Entry Point

Supports both interactive mode and one-liner argument-based execution.
"""

import os
import subprocess  # nosec B404
import sys

from cli.argparser import parse_args, has_action_args, build_filter_dict
from cli.handlers import CommandHandler
from cli.loop import run_menu_loop


def manage_infrastructure(command: str, working_dir: str) -> None:
    """
    Runs docker compose commands securely using subprocess.

    Args:
        command: Docker compose command to run
        working_dir: Working directory for the command
    """
    try:
        cmd = ["docker", "compose"] + command.split()
        subprocess.run(
            cmd,
            cwd=working_dir,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )  # nosec B603
    except subprocess.CalledProcessError as e:
        print(f"\n[!] Error executing Docker command: {' '.join(cmd)}")
        print(f"[!] Docker Output: {e.stderr.decode().strip()}")
        sys.exit(1)
    except FileNotFoundError:
        print("\n[!] Error: 'docker' command not found. Is Docker installed and in your PATH?")
        sys.exit(1)


def run_cli_command(args) -> int:
    """
    Execute a CLI command based on parsed arguments.

    Args:
        args: Parsed argparse namespace

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    handler = CommandHandler(api_url=args.api_url, verbose=args.verbose)

    # Handle scan command
    if args.scan:
        success = handler.scan(
            config_file=args.config,
            parallel=args.parallel,
            repo_url=args.repo_url,
            target_count=args.target_count,
        )
        return 0 if success else 1

    # Handle export commands
    if args.export:
        filter_dict = build_filter_dict(args)
        output_path = args.output or f"export.{args.export}"

        if args.export == "json":
            success = handler.export_json(output_path, filter_dict, args.limit)
        else:  # csv
            success = handler.export_csv(output_path, filter_dict, args.limit)

        return 0 if success else 1

    # Handle manual labeling
    if args.label_manual:
        if not args.id:
            print("Error: --id is required for manual labeling")
            return 1

        if args.set_label:
            success = handler.label_manual(args.id, args.set_label, remove=False)
        elif args.remove_label:
            success = handler.label_manual(args.id, args.remove_label, remove=True)
        else:
            print("Error: --set-label or --remove-label is required")
            return 1

        return 0 if success else 1

    # Handle query command
    if args.query:
        filter_dict = build_filter_dict(args)
        entries = handler.query(filter_dict, args.limit, display=True)
        return 0 if entries is not None else 1

    # Handle import command
    if args.import_data:
        filter_dict = build_filter_dict(args)
        output_path = args.output or "import.json"
        success = handler.export_json(output_path, filter_dict, args.limit)
        return 0 if success else 1

    return 0


def main() -> None:
    """Main entry point for the CLI application."""
    args = parse_args()

    # Determine if we should run in interactive mode
    run_interactive = args.interactive or not has_action_args(args)

    # Get project root directory
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_script_dir, os.pardir))

    # Start infrastructure unless --no-docker is specified
    if not args.no_docker:
        print("Starting FixMyCodeDB Infrastructure...")
        manage_infrastructure("up -d --build --wait", project_root)
        print("Infrastructure started successfully.")

    try:
        if run_interactive:
            # Interactive mode
            run_menu_loop()
        else:
            # One-liner command mode
            exit_code = run_cli_command(args)
            if exit_code != 0:
                sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    finally:
        if not args.no_docker:
            print("Stopping app services (keeping MongoDB running)...")
            manage_infrastructure("stop fastapi scraper", project_root)
            print("MongoDB left running. To stop it: docker compose stop mongo")

    print("Exiting. Goodbye!")


if __name__ == "__main__":
    main()

