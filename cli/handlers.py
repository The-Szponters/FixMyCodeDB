"""
Command handlers for CLI actions.
Shared logic between interactive and argument parser modes.
"""

import csv
import json
import os
import socket
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests


# Configuration
API_BASE = os.getenv("API_URL", "http://localhost:8000")
SCRAPER_ADDR = os.getenv("SCRAPER_ADDR", "127.0.0.1")
SCRAPER_PORT = int(os.getenv("SCRAPER_PORT", "8080"))


class CommandHandler:
    """
    Unified command handler for both interactive and CLI modes.
    """

    def __init__(self, api_url: str = None, verbose: bool = False):
        """
        Initialize the command handler.

        Args:
            api_url: FastAPI server URL
            verbose: Enable verbose output
        """
        self.api_url = api_url or API_BASE
        self.verbose = verbose

    def scan(
        self,
        config_file: str = "config.json",
        parallel: bool = False,
        repo_url: Optional[str] = None,
        target_count: int = 100,
    ) -> bool:
        """
        Execute repository scanning.

        Args:
            config_file: Path to scraper configuration
            parallel: Use parallel scanning mode
            repo_url: Single repository URL (overrides config)
            target_count: Target record count per repository

        Returns:
            True on success, False on failure
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            s.settimeout(10)
            s.connect((SCRAPER_ADDR, SCRAPER_PORT))

            # Determine command based on mode
            if parallel:
                command = f"SCRAPE_PARALLEL {config_file}"
            else:
                command = f"SCRAPE {config_file}"

            s.sendall(command.encode())
            print(f"Sent command to scraper: {command}")

            # Wait for acknowledgment
            response = s.recv(4096)
            if not response:
                print("Error: No response from scraper.")
                return False
            print(f"Received: {response.decode()}")

            # Long timeout for scraping
            s.settimeout(3600)
            buffer = ""

            while True:
                response = s.recv(4096)
                if not response:
                    print("Error: Connection closed by scraper.")
                    break

                buffer += response.decode()

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if line.startswith("PROGRESS:"):
                        print(f"\r{line}", end="", flush=True)
                    elif line.startswith("RESULT:"):
                        print(f"\n{line}")
                    elif line.startswith("ACK: Finished"):
                        print(f"\nScraper finished: {line}")
                        return True
                else:
                    if "ACK: Finished" in buffer:
                        print(f"\nScraper finished: {buffer.strip()}")
                        return True
                    continue
                break

            return True

        except socket.gaierror:
            print(f"Error: Could not resolve scraper address '{SCRAPER_ADDR}'")
            return False
        except socket.timeout:
            print("Error: Scraper did not respond in time.")
            return False
        except Exception as e:
            print(f"Unexpected Error: {e}")
            return False
        finally:
            s.close()

    def export_json(
        self,
        output_path: str,
        filter_dict: Optional[Dict] = None,
        limit: int = 100,
    ) -> bool:
        """
        Export data to JSON file.

        Args:
            output_path: Path to output file
            filter_dict: MongoDB filter dictionary
            limit: Maximum number of entries

        Returns:
            True on success, False on failure
        """
        print(f"Exporting data to {output_path}...")

        try:
            entries = self._fetch_entries(filter_dict, limit)
            if entries is None:
                return False

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False, default=str)

            print(f"Successfully exported {len(entries)} entries to {output_path}")
            return True

        except Exception as e:
            print(f"Export failed: {e}")
            return False

    def export_csv(
        self,
        output_path: str,
        filter_dict: Optional[Dict] = None,
        limit: int = 100,
    ) -> bool:
        """
        Export data to CSV file.

        Args:
            output_path: Path to output file
            filter_dict: MongoDB filter dictionary
            limit: Maximum number of entries

        Returns:
            True on success, False on failure
        """
        print(f"Exporting data to {output_path}...")

        try:
            entries = self._fetch_entries(filter_dict, limit)
            if entries is None:
                return False

            if not entries:
                print("No entries to export.")
                return True

            # Flatten entries for CSV
            flattened = []
            for entry in entries:
                flat = {
                    "id": entry.get("_id", ""),
                    "code_hash": entry.get("code_hash", ""),
                    "code_original": entry.get("code_original", ""),
                    "code_fixed": entry.get("code_fixed", ""),
                    "repo_url": entry.get("repo", {}).get("url", ""),
                    "commit_hash": entry.get("repo", {}).get("commit_hash", ""),
                    "commit_date": entry.get("repo", {}).get("commit_date", ""),
                    "ingest_timestamp": entry.get("ingest_timestamp", ""),
                    "cppcheck_labels": "|".join(entry.get("labels", {}).get("cppcheck", [])),
                    "memory_management": entry.get("labels", {}).get("groups", {}).get("memory_management", False),
                    "invalid_access": entry.get("labels", {}).get("groups", {}).get("invalid_access", False),
                    "uninitialized": entry.get("labels", {}).get("groups", {}).get("uninitialized", False),
                    "concurrency": entry.get("labels", {}).get("groups", {}).get("concurrency", False),
                    "logic_error": entry.get("labels", {}).get("groups", {}).get("logic_error", False),
                    "resource_leak": entry.get("labels", {}).get("groups", {}).get("resource_leak", False),
                    "security_portability": entry.get("labels", {}).get("groups", {}).get("security_portability", False),
                    "code_quality_performance": entry.get("labels", {}).get("groups", {}).get("code_quality_performance", False),
                }
                flattened.append(flat)

            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=flattened[0].keys())
                writer.writeheader()
                writer.writerows(flattened)

            print(f"Successfully exported {len(entries)} entries to {output_path}")
            return True

        except Exception as e:
            print(f"Export failed: {e}")
            return False

    def export_all_files(self, output_dir: str = "exported_files") -> bool:
        """
        Export all entries as individual JSON files.

        Args:
            output_dir: Directory to export files to

        Returns:
            True on success, False on failure
        """
        export_path = Path(output_dir)
        export_path.mkdir(parents=True, exist_ok=True)

        print(f"Exporting all entries to {export_path}...")

        endpoint = f"{self.api_url}/entries/export-all"
        try:
            with requests.get(endpoint, stream=True, timeout=(10, None)) as response:
                response.raise_for_status()

                written = 0
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue

                    entry = json.loads(line)
                    entry_id = entry.get("_id") or entry.get("code_hash") or f"entry_{written}"
                    name = self._safe_filename(str(entry_id))

                    out_path = export_path / f"{name}.json"
                    with out_path.open("w", encoding="utf-8") as f:
                        json.dump(entry, f, indent=2, ensure_ascii=False)

                    written += 1

            print(f"Exported {written} entries to {export_path}/")
            return True

        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to {self.api_url}")
            return False
        except Exception as e:
            print(f"Export failed: {e}")
            return False

    def label_manual(
        self,
        record_id: str,
        label: str,
        remove: bool = False,
    ) -> bool:
        """
        Manually add or remove a label from a record.

        Args:
            record_id: Database record ID
            label: Label to add/remove
            remove: If True, remove the label instead of adding

        Returns:
            True on success, False on failure
        """
        print(f"{'Removing' if remove else 'Adding'} label '{label}' for record {record_id}...")

        try:
            # First, get the current entry
            response = requests.get(
                f"{self.api_url}/entries/{record_id}",
                timeout=10
            )
            response.raise_for_status()
            entry = response.json()

            # Get current labels
            labels = entry.get("labels", {})
            cppcheck = labels.get("cppcheck", [])

            # Modify labels
            if remove:
                if label in cppcheck:
                    cppcheck.remove(label)
                    print(f"Removed '{label}' from cppcheck labels")
                else:
                    print(f"Label '{label}' not found in record")
                    return True
            else:
                if label not in cppcheck:
                    cppcheck.append(label)
                    print(f"Added '{label}' to cppcheck labels")
                else:
                    print(f"Label '{label}' already exists")
                    return True

            # Update the record
            update_data = {"labels.cppcheck": cppcheck}
            response = requests.put(
                f"{self.api_url}/entries/{record_id}",
                json=update_data,
                timeout=10
            )
            response.raise_for_status()

            print(f"Successfully updated record {record_id}")
            return True

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"Error: Record {record_id} not found")
            else:
                print(f"API Error: {e.response.text}")
            return False
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to {self.api_url}")
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False

    def set_label_group(
        self,
        record_id: str,
        group: str,
        value: bool,
    ) -> bool:
        """
        Set a label group boolean value.

        Args:
            record_id: Database record ID
            group: Label group name (e.g., 'memory_management')
            value: Boolean value to set

        Returns:
            True on success, False on failure
        """
        valid_groups = [
            "memory_management",
            "invalid_access",
            "uninitialized",
            "concurrency",
            "logic_error",
            "resource_leak",
            "security_portability",
            "code_quality_performance",
        ]

        if group not in valid_groups:
            print(f"Error: Invalid group '{group}'. Valid groups: {valid_groups}")
            return False

        try:
            update_data = {f"labels.groups.{group}": value}
            response = requests.put(
                f"{self.api_url}/entries/{record_id}",
                json=update_data,
                timeout=10
            )
            response.raise_for_status()

            print(f"Set labels.groups.{group} = {value} for record {record_id}")
            return True

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"Error: Record {record_id} not found")
            else:
                print(f"API Error: {e.response.text}")
            return False
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to {self.api_url}")
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False

    def query(
        self,
        filter_dict: Optional[Dict] = None,
        limit: int = 100,
        display: bool = True,
    ) -> Optional[List[Dict]]:
        """
        Query entries from database.

        Args:
            filter_dict: MongoDB filter dictionary
            limit: Maximum results
            display: Print results to console

        Returns:
            List of entries or None on error
        """
        entries = self._fetch_entries(filter_dict, limit)

        if entries is not None and display:
            print(f"\nFound {len(entries)} entries:\n")
            for entry in entries:
                entry_id = entry.get("_id", "N/A")
                repo_url = entry.get("repo", {}).get("url", "N/A")
                commit = entry.get("repo", {}).get("commit_hash", "N/A")[:7]
                cppcheck = entry.get("labels", {}).get("cppcheck", [])

                print(f"  ID: {entry_id}")
                print(f"  Repo: {repo_url}")
                print(f"  Commit: {commit}")
                print(f"  Labels: {', '.join(cppcheck) if cppcheck else 'None'}")
                print("-" * 40)

        return entries

    def get_entry(self, record_id: str) -> Optional[Dict]:
        """
        Get a single entry by ID.

        Args:
            record_id: Database record ID

        Returns:
            Entry dictionary or None
        """
        try:
            response = requests.get(
                f"{self.api_url}/entries/{record_id}",
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"Error: Record {record_id} not found")
            return None
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to {self.api_url}")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def _fetch_entries(
        self,
        filter_dict: Optional[Dict] = None,
        limit: int = 100,
    ) -> Optional[List[Dict]]:
        """
        Fetch entries from API.

        Args:
            filter_dict: MongoDB filter dictionary
            limit: Maximum results

        Returns:
            List of entries or None on error
        """
        payload = {
            "filter": filter_dict or {},
            "limit": limit,
            "sort": {},
        }

        try:
            response = requests.post(
                f"{self.api_url}/entries/query/",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to {self.api_url}")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"API Error: {e.response.text}")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    @staticmethod
    def _safe_filename(value: str) -> str:
        """Create a safe filename from a string."""
        return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", "."))
