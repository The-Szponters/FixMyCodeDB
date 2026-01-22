"""
CLI Handlers for non-interactive command-line operations.
Each handler corresponds to a CLI command (--scrape, --list-all, etc.)
"""

import csv
import json
import os
import socket
from pathlib import Path
from typing import List, Optional

import requests

API_BASE = os.getenv("API_URL", "http://localhost:8000")
SCRAPER_ADDR = os.getenv("SCRAPER_ADDR", "127.0.0.1")
SCRAPER_PORT = int(os.getenv("SCRAPER_PORT", 8080))


# ============================================================================
# Label Mapping (CLI label names -> backend field paths)
# ============================================================================
LABEL_TO_GROUP_FIELD = {
    "MemError": "memory_management",
    "MemoryManagement": "memory_management",
    "memory_management": "memory_management",
    "InvalidAccess": "invalid_access",
    "invalid_access": "invalid_access",
    "Uninitialized": "uninitialized",
    "uninitialized": "uninitialized",
    "Concurrency": "concurrency",
    "concurrency": "concurrency",
    "LogicError": "logic_error",
    "logic_error": "logic_error",
    "ResourceLeak": "resource_leak",
    "resource_leak": "resource_leak",
    "SecurityPortability": "security_portability",
    "security_portability": "security_portability",
    "CodeQualityPerformance": "code_quality_performance",
    "code_quality_performance": "code_quality_performance",
}


def labels_to_filter(labels: List[str]) -> dict:
    """
    Convert a list of CLI label names to a MongoDB filter dictionary.
    E.g., ["MemError", "LogicError"] -> {"labels.groups.memory_management": True, "labels.groups.logic_error": True}
    """
    mongo_filter = {}
    for label in labels:
        if label in LABEL_TO_GROUP_FIELD:
            field = f"labels.groups.{LABEL_TO_GROUP_FIELD[label]}"
            mongo_filter[field] = True
        else:
            # Treat as cppcheck label - search in labels.cppcheck array
            mongo_filter["labels.cppcheck"] = {"$in": [label]}
    return mongo_filter


# ============================================================================
# Scrape Handler
# ============================================================================
def handle_scrape(config_path: str) -> int:
    """Send SCRAPE command to scraper socket."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(10)
        s.connect((SCRAPER_ADDR, SCRAPER_PORT))
        s.sendall(f"SCRAPE {config_path}".encode())
        print(f"[*] Sent SCRAPE command with config '{config_path}'")

        # Wait for confirmation response
        response = s.recv(4096)
        if not response:
            print("[!] Error: No response from scraper.")
            return 1
        print(f"[*] Scraper response: {response.decode()}")

        # Listen for progress updates
        s.settimeout(5)
        buffer = ""
        while True:
            try:
                response = s.recv(4096)
                if not response:
                    print("[!] Connection closed by scraper.")
                    break
            except socket.timeout:
                continue

            buffer += response.decode()

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line.startswith("PROGRESS:"):
                    print(f"\r{line}", end="", flush=True)
                elif line.startswith("ACK: Finished"):
                    print(f"\n[✓] Scraper finished: {line}")
                    return 0
            else:
                if "ACK: Finished" in buffer:
                    print(f"\n[✓] Scraper finished: {buffer.strip()}")
                    return 0
                continue
            break
        return 0

    except socket.gaierror:
        print(f"[!] Error: Could not resolve scraper address '{SCRAPER_ADDR}'")
        return 1
    except socket.timeout:
        print("[!] Error: Scraper did not respond in time.")
        return 1
    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user.")
        return 130
    except Exception as e:
        print(f"[!] Unexpected Error: {e}")
        return 1
    finally:
        s.close()


# ============================================================================
# List Handlers
# ============================================================================
def handle_list_all() -> int:
    """Fetch and display all records from the backend."""
    try:
        response = requests.get(f"{API_BASE}/entries/", params={"limit": 0}, timeout=10)
        response.raise_for_status()
        entries = response.json()
        _print_entries_table(entries)
        return 0
    except requests.exceptions.ConnectionError:
        print(f"[!] Error: Could not connect to {API_BASE}")
        return 1
    except requests.exceptions.HTTPError as e:
        print(f"[!] API Error: {e.response.text}")
        return 1
    except Exception as e:
        print(f"[!] Unexpected Error: {e}")
        return 1


def handle_list_labels(labels: List[str]) -> int:
    """Fetch and display records matching all specified labels."""
    try:
        mongo_filter = labels_to_filter(labels)
        payload = {"filter": mongo_filter, "limit": 0, "sort": {}}
        response = requests.post(f"{API_BASE}/entries/query/", json=payload, timeout=10)
        response.raise_for_status()
        entries = response.json()
        print(f"[*] Found {len(entries)} entries matching labels: {', '.join(labels)}")
        _print_entries_table(entries)
        return 0
    except requests.exceptions.ConnectionError:
        print(f"[!] Error: Could not connect to {API_BASE}")
        return 1
    except requests.exceptions.HTTPError as e:
        print(f"[!] API Error: {e.response.text}")
        return 1
    except Exception as e:
        print(f"[!] Unexpected Error: {e}")
        return 1


def _print_entries_table(entries: list) -> None:
    """Print entries as a formatted table."""
    if not entries:
        print("No entries found.")
        return

    print(f"\n{'_id':<26} | {'Labels':<50}")
    print("-" * 80)
    for entry in entries:
        entry_id = entry.get("_id", "N/A")
        labels = entry.get("labels", {})
        groups = labels.get("groups", {})
        # Get active group labels
        active_groups = [k for k, v in groups.items() if v is True]

        labels_str = ", ".join(active_groups[:5])
        if len(active_groups) > 5:
            labels_str += f" (+{len(active_groups) - 5} more)"
        print(f"{entry_id:<26} | {labels_str:<50}")
    print(f"\nTotal: {len(entries)} entries")


# ============================================================================
# Import Handlers
# ============================================================================
def handle_import_all(folder_path: str, format_type: str) -> int:
    """Import all files from a folder to the backend."""
    folder = Path(folder_path)
    if not folder.exists():
        print(f"[!] Error: Folder '{folder_path}' does not exist.")
        return 1

    if format_type == "JSON":
        files = list(folder.glob("*.json"))
    else:  # CSV
        files = list(folder.glob("*.csv"))

    if not files:
        print(f"[!] No {format_type} files found in '{folder_path}'")
        return 1

    print(f"[*] Found {len(files)} {format_type} files to import")
    success_count = 0
    error_count = 0

    for file_path in files:
        try:
            if format_type == "JSON":
                entry = _read_json_entry(file_path)
            else:
                entry = _read_csv_entry(file_path)

            if entry is None:
                error_count += 1
                continue

            # Remove _id if present (let MongoDB generate new one)
            entry.pop("_id", None)

            response = requests.post(f"{API_BASE}/entries/", json=entry, timeout=10)
            if response.status_code == 201:
                success_count += 1
                print(f"  [✓] Imported: {file_path.name}")
            elif response.status_code == 409:
                print(f"  [!] Duplicate: {file_path.name}")
                error_count += 1
            else:
                print(f"  [!] Failed: {file_path.name} - {response.text}")
                error_count += 1

        except Exception as e:
            print(f"  [!] Error processing {file_path.name}: {e}")
            error_count += 1

    print(f"\n[*] Import complete: {success_count} success, {error_count} errors")
    return 0 if error_count == 0 else 1


def _read_json_entry(file_path: Path) -> Optional[dict]:
    """Read a JSON file and return as a dictionary."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [!] Error reading {file_path.name}: {e}")
        return None


def _read_csv_entry(file_path: Path) -> Optional[dict]:
    """Read a CSV file and unflatten to nested CodeEntry structure."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader, None)
            if row is None:
                return None
            return _unflatten_csv_row(row)
    except Exception as e:
        print(f"  [!] Error reading {file_path.name}: {e}")
        return None


def _unflatten_csv_row(row: dict) -> dict:
    """Convert a flat CSV row back to nested CodeEntry structure."""
    entry = {
        "code_original": row.get("code_original", ""),
        "code_fixed": row.get("code_fixed") or None,
        "code_hash": row.get("code_hash", ""),
        "repo": {
            "url": row.get("repo_url", ""),
            "commit_hash": row.get("repo_commit_hash", ""),
            "commit_date": row.get("repo_commit_date", ""),
        },
        "ingest_timestamp": row.get("ingest_timestamp", ""),
        "labels": {
            "cppcheck": json.loads(row.get("labels_cppcheck", "[]")),
            "clang": json.loads(row.get("labels_clang", "{}")),
            "groups": {
                "memory_management": row.get("labels_memory_management", "").lower()
                == "true",
                "invalid_access": row.get("labels_invalid_access", "").lower()
                == "true",
                "uninitialized": row.get("labels_uninitialized", "").lower() == "true",
                "concurrency": row.get("labels_concurrency", "").lower() == "true",
                "logic_error": row.get("labels_logic_error", "").lower() == "true",
                "resource_leak": row.get("labels_resource_leak", "").lower() == "true",
                "security_portability": row.get(
                    "labels_security_portability", ""
                ).lower()
                == "true",
                "code_quality_performance": row.get(
                    "labels_code_quality_performance", ""
                ).lower()
                == "true",
            },
        },
    }
    return entry


# ============================================================================
# Export Handlers
# ============================================================================
def handle_export_all(
    folder_path: str, format_type: str, labels: Optional[List[str]] = None
) -> int:
    """Export all (or filtered) records from the backend to files."""
    folder = Path(folder_path)
    folder.mkdir(parents=True, exist_ok=True)

    try:
        if labels:
            # Filter by labels
            mongo_filter = labels_to_filter(labels)
            payload = {"filter": mongo_filter, "limit": 10000, "sort": {}}
            response = requests.post(
                f"{API_BASE}/entries/query/", json=payload, timeout=30
            )
            response.raise_for_status()
            entries = response.json()
            print(
                f"[*] Found {len(entries)} entries matching labels: {', '.join(labels)}"
            )
        else:
            # Export all via streaming endpoint
            entries = []
            with requests.get(
                f"{API_BASE}/entries/export-all", stream=True, timeout=(10, None)
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if line:
                        entries.append(json.loads(line))
            print(f"[*] Found {len(entries)} entries to export")

        if not entries:
            print("[*] No entries to export.")
            return 0

        for entry in entries:
            entry_id = entry.get("_id", "unknown")
            safe_name = _safe_filename(str(entry_id))

            if format_type == "JSON":
                out_path = folder / f"{safe_name}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(entry, f, indent=2, ensure_ascii=False)
            else:  # CSV
                out_path = folder / f"{safe_name}.csv"
                _write_csv_entry(out_path, entry)

        print(f"[✓] Exported {len(entries)} entries to {folder.as_posix()}/")
        return 0

    except requests.exceptions.ConnectionError:
        print(f"[!] Error: Could not connect to {API_BASE}")
        return 1
    except requests.exceptions.HTTPError as e:
        print(f"[!] API Error: {e.response.text}")
        return 1
    except Exception as e:
        print(f"[!] Unexpected Error: {e}")
        return 1


def _safe_filename(value: str) -> str:
    """Create a safe filename from a string."""
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", "."))


def _write_csv_entry(file_path: Path, entry: dict) -> None:
    """Write a single entry to a CSV file with flattened structure."""
    flat = _flatten_entry(entry)
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=flat.keys())
        writer.writeheader()
        writer.writerow(flat)


def _flatten_entry(entry: dict) -> dict:
    """Flatten a nested CodeEntry to flat CSV columns."""
    repo = entry.get("repo", {})
    labels = entry.get("labels", {})
    groups = labels.get("groups", {})

    flat = {
        "_id": entry.get("_id", ""),
        "code_original": entry.get("code_original", ""),
        "code_fixed": entry.get("code_fixed", ""),
        "code_hash": entry.get("code_hash", ""),
        "repo_url": repo.get("url", ""),
        "repo_commit_hash": repo.get("commit_hash", ""),
        "repo_commit_date": repo.get("commit_date", ""),
        "ingest_timestamp": entry.get("ingest_timestamp", ""),
        "labels_cppcheck": json.dumps(labels.get("cppcheck", [])),
        "labels_clang": json.dumps(labels.get("clang", {})),
        "labels_memory_management": str(groups.get("memory_management", False)),
        "labels_invalid_access": str(groups.get("invalid_access", False)),
        "labels_uninitialized": str(groups.get("uninitialized", False)),
        "labels_concurrency": str(groups.get("concurrency", False)),
        "labels_logic_error": str(groups.get("logic_error", False)),
        "labels_resource_leak": str(groups.get("resource_leak", False)),
        "labels_security_portability": str(groups.get("security_portability", False)),
        "labels_code_quality_performance": str(
            groups.get("code_quality_performance", False)
        ),
    }
    return flat


# ============================================================================
# Edit Handlers
# ============================================================================
def handle_edit_labels(
    entry_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> int:
    """Add or remove labels from an entry via the backend PATCH endpoint."""
    if not add_labels and not remove_labels:
        print("[!] Error: Must specify --add-label or --remove-label")
        return 1

    payload = {
        "add": add_labels or [],
        "remove": remove_labels or [],
    }

    try:
        response = requests.patch(
            f"{API_BASE}/entries/{entry_id}/labels", json=payload, timeout=10
        )
        if response.status_code == 404:
            print(f"[!] Error: Entry '{entry_id}' not found.")
            return 1
        response.raise_for_status()
        _ = response.json()  # Consume response (updated entry returned)
        print(f"[✓] Updated entry '{entry_id}'")
        if add_labels:
            print(f"    Added labels: {', '.join(add_labels)}")
        if remove_labels:
            print(f"    Removed labels: {', '.join(remove_labels)}")
        return 0

    except requests.exceptions.ConnectionError:
        print(f"[!] Error: Could not connect to {API_BASE}")
        return 1
    except requests.exceptions.HTTPError as e:
        print(f"[!] API Error: {e.response.text}")
        return 1
    except Exception as e:
        print(f"[!] Unexpected Error: {e}")
        return 1
