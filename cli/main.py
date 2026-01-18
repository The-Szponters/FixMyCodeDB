#!/usr/bin/env python3
"""
FixMyCodeDB CLI - Main Entry Point

Supports both interactive mode and one-liner argument-based execution.
"""

import os
import subprocess  # nosec B404
import sys
import time

import requests

from cli.argparser import parse_args, has_action_args, build_filter_dict
from cli.handlers import CommandHandler
from cli.loop import run_menu_loop


def manage_infrastructure(command: str, working_dir: str, timeout: int = 300) -> bool:
    """
    Runs docker compose commands securely using subprocess.

    Args:
        command: Docker compose command to run
        working_dir: Working directory for the command
        timeout: Timeout in seconds for the command

    Returns:
        True on success, False on failure
    """
    try:
        cmd = ["docker", "compose"] + command.split()
        # Use Popen for non-blocking execution with progress indication
        process = subprocess.Popen(
            cmd,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )  # nosec B603

        start_time = time.time()
        while process.poll() is None:
            elapsed = int(time.time() - start_time)
            if elapsed > timeout:
                process.kill()
                print(f"\n[!] Docker command timed out after {timeout}s")
                return False
            print(f"\rDocker: {command}... ({elapsed}s)", end="", flush=True)
            time.sleep(1)

        print()  # Newline after progress
        if process.returncode != 0:
            output = process.stdout.read() if process.stdout else ""
            print(f"[!] Docker command failed: {' '.join(cmd)}")
            if output:
                print(f"[!] Output: {output[:500]}")
            return False
        return True
    except FileNotFoundError:
        print("[!] Docker not found. Please ensure Docker is installed and in PATH.")
        return False
    except FileNotFoundError:
        print("\n[!] Error: 'docker' command not found. Is Docker installed and in your PATH?")
        return False


def wait_for_api(api_url: str, timeout: int = 60) -> bool:
    """
    Wait for the FastAPI service to become available.

    Args:
        api_url: URL of the API to check
        timeout: Maximum seconds to wait

    Returns:
        True if API is available, False if timeout
    """
    print(f"Waiting for API at {api_url}...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{api_url}/docs", timeout=2)
            if response.status_code == 200:
                print("API is ready!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        except requests.exceptions.Timeout:
            pass

        time.sleep(1)
        elapsed = int(time.time() - start_time)
        print(f"\rWaiting for API... ({elapsed}s)", end="", flush=True)

    print(f"\n[!] API did not become available within {timeout}s")
    return False


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
        # Use 'up -d --build' without --wait (services don't have health checks)
        if not manage_infrastructure("up -d --build", project_root):
            print("[!] Failed to start Docker infrastructure.")
            print("[!] You can run with --no-docker to skip Docker management.")
            sys.exit(1)

        # Wait for API to become available
        if not wait_for_api(args.api_url, timeout=60):
            print("[!] API service did not start in time.")
            print("[!] Check Docker logs with: docker compose logs fastapi")
            sys.exit(1)

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

