import os
import subprocess  # nosec B404
import sys

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


def main():
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
