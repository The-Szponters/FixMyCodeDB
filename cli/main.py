import os
import subprocess  # nosec B404
import sys
import argparse

from cli.loop import run_menu_loop


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


def run_tui_dashboard():
    """
    Run the parallel scraper with TUI dashboard.
    This imports and runs the scraper in-process for local development/testing.
    """
    try:
        from scraper.main import run_parallel_scraper

        # Default config path
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            os.pardir,
            "scraper",
            "config.json"
        )

        print("Starting parallel scraper with TUI dashboard...")
        print(f"Using config: {config_path}")
        print("Press Ctrl+C to stop\n")

        run_parallel_scraper(config_path, with_tui=True)

    except ImportError as e:
        print(f"Error: Could not import scraper module: {e}")
        print("Make sure 'rich' is installed: pip install rich")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nScraper stopped by user.")
    except Exception as e:
        print(f"Error running TUI dashboard: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="FixMyCodeDB CLI - Manage infrastructure and run scraper"
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Run the parallel scraper with TUI dashboard (local mode)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to scraper config.json (used with --tui)"
    )

    args = parser.parse_args()

    if args.tui:
        # Run TUI dashboard directly (local mode)
        if args.config:
            os.environ["SCRAPER_CONFIG"] = args.config
        run_tui_dashboard()
        return

    # Standard mode: start infrastructure and run menu
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_script_dir, os.pardir))
    print("Starting FixMyCodeDB Infrastructure...")

    manage_infrastructure("up -d --build --wait", project_root)

    print("Infrastructure started successfully.")

    try:
        run_menu_loop()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        print("Stopping app services (keeping MongoDB running)...")
        manage_infrastructure("stop fastapi scraper", project_root)
        print("MongoDB left running. To stop it: docker compose stop mongo")

        print("Exiting. Goodbye!")


if __name__ == "__main__":
    main()
