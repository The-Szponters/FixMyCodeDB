"""
CLI Application - Command Tree Setup and Action Handlers

This module defines the CLI command structure and action implementations
for both interactive and argument-parser modes.
"""

import csv
import json
import os
import socket
from pathlib import Path
from typing import Any, Dict

import requests
import questionary

from cli.command_tree import CommandTree, custom_style
from cli.handlers import CommandHandler

API_BASE = os.getenv("API_URL", "http://localhost:8000")
SCRAPER_ADDR = os.getenv("SCRAPER_ADDR", "127.0.0.1")
SCRAPER_PORT = int(os.getenv("SCRAPER_PORT", "8080"))

FILTER_PARAMS = {
    "limit": "100",
    "repo_url": "",
    "commit_hash": "",
    "code_hash": "",
    # Boolean flags matching labels_config.json categories
    "has_memory_management": "",
    "has_invalid_access": "",
    "has_uninitialized": "",
    "has_concurrency": "",
    "has_logic_error": "",
    "has_resource_leak": "",
    "has_security_portability": "",
    "has_code_quality_performance": "",
}

# Initialize shared handler
_handler = CommandHandler(api_url=API_BASE)


def build_api_payload(params: Dict[str, Any]) -> Dict:
    """
    Converts flat CLI params into a nested MongoDB/FastAPI query object.
    Removes empty keys so we don't filter by "" (which would match nothing).
    """
    mongo_filter = {}

    if params.get("repo_url"):
        mongo_filter["repo.url"] = params["repo_url"]

    if params.get("commit_hash"):
        mongo_filter["repo.commit_hash"] = params["commit_hash"]

    if params.get("code_hash"):
        mongo_filter["code_hash"] = params["code_hash"]

    bool_map = {
        "has_memory_management": "labels.groups.memory_management",
        "has_invalid_access": "labels.groups.invalid_access",
        "has_uninitialized": "labels.groups.uninitialized",
        "has_concurrency": "labels.groups.concurrency",
        "has_logic_error": "labels.groups.logic_error",
        "has_resource_leak": "labels.groups.resource_leak",
        "has_security_portability": "labels.groups.security_portability",
        "has_code_quality_performance": "labels.groups.code_quality_performance",
    }

    for cli_key, db_key in bool_map.items():
        val = params.get(cli_key, "").lower()
        if val in ["true", "1", "yes", "y"]:
            mongo_filter[db_key] = True
        elif val in ["false", "0", "no", "n"]:
            mongo_filter[db_key] = False

    return mongo_filter


def do_import(params: Dict[str, Any]) -> None:
    """Import data from database with filters."""
    print(f"\n[*] Connecting to API at {API_BASE}...")

    query_filter = build_api_payload(params)
    limit = int(params.get("limit", 100))

    payload = {"filter": query_filter, "limit": limit, "sort": {}}
    endpoint = f"{API_BASE}/entries/query/"

    try:
        response = requests.post(endpoint, json=payload, timeout=5)
        response.raise_for_status()

        data = response.json()
        count = len(data)
        print(f"Success! API returned {count} entries matching your criteria.")

        try:
            with open(params["target file"], "w") as f:
                json.dump(data, f, indent=2)
            print(f"Data imported to {params['target file']}")
        except Exception as e:
            print(f"Error writing to file: {e}")

        if count > 0:
            print(f"Sample ID: {data[0].get('_id')}")

    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {API_BASE}. Is the 'fastapi' container running?")
    except requests.exceptions.HTTPError as e:
        print(f"API Error: {e.response.text}")
    except Exception as e:
        print(f"Unexpected Error: {e}")


def do_scrape(params: Dict[str, Any]) -> None:
    """Execute repository scraping."""
    config_file = params.get("config_file", "config.json")
    _handler.scan(config_file=config_file, parallel=False)


def do_scrape_parallel(params: Dict[str, Any]) -> None:
    """Execute parallel repository scraping."""
    config_file = params.get("config_file", "config.json")
    _handler.scan(config_file=config_file, parallel=True)


def do_label(params: Dict[str, Any]) -> None:
    """Placeholder for automatic labeling."""
    print("Automatic labeling is performed during scraping.")
    print("Use 'label-manual' to manually review and modify labels.")


def do_label_manual(params: Dict[str, Any]) -> None:
    """
    Interactive manual labeling of database entries.
    Allows users to review and modify labels for specific records.
    """
    print("\n[*] Manual Labeling Mode")
    print("-" * 40)

    # Get list of entries to review
    entries = _handler.query(limit=10, display=False)
    if not entries:
        print("No entries found in database.")
        return

    # Let user select an entry
    choices = []
    for entry in entries:
        entry_id = entry.get("_id", "N/A")
        repo_url = entry.get("repo", {}).get("url", "N/A")
        cppcheck = entry.get("labels", {}).get("cppcheck", [])
        label_str = ", ".join(cppcheck[:3]) + ("..." if len(cppcheck) > 3 else "") if cppcheck else "No labels"

        choices.append(questionary.Choice(
            title=f"{entry_id[:12]}... | {repo_url.split('/')[-1]} | {label_str}",
            value=entry_id
        ))

    choices.append(questionary.Choice(title="Enter ID manually", value="MANUAL"))
    choices.append(questionary.Choice(title="Cancel", value="CANCEL"))

    selection = questionary.select(
        "Select an entry to label:",
        choices=choices,
        style=custom_style
    ).ask()

    if selection == "CANCEL":
        return

    if selection == "MANUAL":
        selection = questionary.text(
            "Enter record ID:",
            style=custom_style
        ).ask()
        if not selection:
            return

    # Fetch the selected entry
    entry = _handler.get_entry(selection)
    if not entry:
        return

    # Display entry details
    print("\n" + "=" * 60)
    print(f"Record ID: {entry.get('_id')}")
    print(f"Repository: {entry.get('repo', {}).get('url')}")
    print(f"Commit: {entry.get('repo', {}).get('commit_hash')}")
    print(f"\nCurrent Labels (cppcheck): {entry.get('labels', {}).get('cppcheck', [])}")
    print(f"\nLabel Groups:")
    groups = entry.get("labels", {}).get("groups", {})
    for group, value in groups.items():
        status = "✓" if value else "✗"
        print(f"  [{status}] {group}")
    print("=" * 60)

    # Ask what to do
    action = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice(title="Add a cppcheck label", value="ADD"),
            questionary.Choice(title="Remove a cppcheck label", value="REMOVE"),
            questionary.Choice(title="Toggle a label group", value="TOGGLE"),
            questionary.Choice(title="View code", value="VIEW"),
            questionary.Choice(title="Done", value="DONE"),
        ],
        style=custom_style
    ).ask()

    if action == "ADD":
        label = questionary.text(
            "Enter label to add (e.g., 'memleak', 'nullPointer'):",
            style=custom_style
        ).ask()
        if label:
            _handler.label_manual(selection, label, remove=False)

    elif action == "REMOVE":
        current_labels = entry.get("labels", {}).get("cppcheck", [])
        if not current_labels:
            print("No labels to remove.")
        else:
            label = questionary.select(
                "Select label to remove:",
                choices=current_labels,
                style=custom_style
            ).ask()
            if label:
                _handler.label_manual(selection, label, remove=True)

    elif action == "TOGGLE":
        group = questionary.select(
            "Select label group to toggle:",
            choices=list(groups.keys()),
            style=custom_style
        ).ask()
        if group:
            new_value = not groups.get(group, False)
            _handler.set_label_group(selection, group, new_value)

    elif action == "VIEW":
        print("\n--- Original Code (first 50 lines) ---")
        code = entry.get("code_original", "")
        lines = code.split("\n")[:50]
        for i, line in enumerate(lines, 1):
            print(f"{i:4d} | {line}")
        if len(code.split("\n")) > 50:
            print(f"... ({len(code.split(chr(10))) - 50} more lines)")


def _safe_filename(value: str) -> str:
    """Create a safe filename from a string."""
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", "."))


def do_export_all(params: Dict[str, Any]) -> None:
    """Export all entries as individual JSON files."""
    _handler.export_all_files("exported_files")


def do_export_json(params: Dict[str, Any]) -> None:
    """Export entries to a single JSON file."""
    output = params.get("output_file", "export.json")
    limit = int(params.get("limit", "1000"))
    _handler.export_json(output, limit=limit)


def do_export_csv(params: Dict[str, Any]) -> None:
    """Export entries to a CSV file."""
    output = params.get("output_file", "export.csv")
    limit = int(params.get("limit", "1000"))
    _handler.export_csv(output, limit=limit)


def do_query(params: Dict[str, Any]) -> None:
    """Query and display entries from database."""
    query_filter = build_api_payload(params)
    limit = int(params.get("limit", 100))
    _handler.query(query_filter, limit, display=True)


class CLIApp(CommandTree):
    """
    CLI Application with command tree structure.
    Defines all available commands and their parameters.
    """

    def __init__(self):
        super().__init__()

        # Scraping commands
        self.add_command(
            "scrape",
            do_scrape,
            param_set={"config_file": "config.json"}
        )
        self.add_command(
            "scrape-parallel",
            do_scrape_parallel,
            param_set={"config_file": "config.json"}
        )

        # Import/Query commands
        self.add_command(
            "import",
            do_import,
            param_set={"sort by": "ingest_timestamp", **FILTER_PARAMS, "target file": "import.json"}
        )
        self.add_command(
            "import-all",
            do_import,
            param_set={"target file": "import.json"}
        )
        self.add_command(
            "query",
            do_query,
            param_set=FILTER_PARAMS
        )

        # Export commands
        self.add_command(
            "export-all",
            do_export_all,
            param_set={}
        )
        self.add_command(
            "export-json",
            do_export_json,
            param_set={"output_file": "export.json", "limit": "1000"}
        )
        self.add_command(
            "export-csv",
            do_export_csv,
            param_set={"output_file": "export.csv", "limit": "1000"}
        )

        # Labeling commands
        self.add_command(
            "label",
            do_label,
            param_set={}
        )
        self.add_command(
            "label-manual",
            do_label_manual,
            param_set={}
        )

        print(f"Error: Could not resolve scraper address '{SCRAPER_ADDR}'. Is the 'scraper' container running?")
        s.close()
        return
    except socket.timeout:
        print("Error: Scraper did not respond in time.")
    except Exception as e:
        print(f"Unexpected Error: {e}")
    finally:
        s.close()


def do_label(params):
    print("Labeling...")


def _safe_filename(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", "."))


def do_export_all(params):
    export_dir = Path("exported_files")
    export_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[*] Connecting to API at {API_BASE}...")

    endpoint = f"{API_BASE}/entries/export-all"
    try:
        with requests.get(endpoint, stream=True, timeout=(10, None)) as response:
            response.raise_for_status()

            written = 0
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                entry = json.loads(line)
                entry_id = entry.get("_id") or ""
                code_hash = entry.get("code_hash") or ""

                if entry_id:
                    name = _safe_filename(str(entry_id))
                elif code_hash:
                    name = _safe_filename(str(code_hash))
                else:
                    name = f"entry_{written}"

                out_path = export_dir / f"{name}.json"
                with out_path.open("w", encoding="utf-8") as f:
                    json.dump(entry, f, indent=2, ensure_ascii=False)

                written += 1

        print(f"Exported {written} entries to {export_dir.as_posix()}/")

    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {API_BASE}. Is the 'fastapi' container running?")
    except requests.exceptions.HTTPError as e:
        print(f"API Error: {e.response.text}")
    except Exception as e:
        print(f"Unexpected Error: {e}")


class CLIApp(CommandTree):
    def __init__(self):
        super().__init__()

        self.add_command("scrape", do_scrape, param_set={"config_file": "config.json"})
        self.add_command("import", do_import, param_set={"sort by": "ingest_timestamp", **FILTER_PARAMS, "target file": "import.json"})
        self.add_command("import-all", do_import, param_set={"target file": "import.json"})
        self.add_command("export-all", do_export_all, param_set={})
        self.add_command("label", do_label, param_set={})
