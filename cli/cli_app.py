import json
import os
import socket
from pathlib import Path

import requests

from cli.command_tree import CommandTree

API_BASE = os.getenv("API_URL", "http://localhost:8000")
SCRAPER_ADDR = os.getenv("SCRAPER_ADDR", "127.0.0.1")
SCRAPER_PORT = os.getenv("SCRAPER_PORT", 8080)

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


def build_api_payload(params):
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


def do_import(params):
    print(f"\n[*] Connecting to API at {API_BASE}...")

    # This turns flat CLI params ("has_memory_errors") into nested DB keys ("labels.groups...")
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


def do_scrape(params):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    filename = params.get("config_file")

    try:
        s.settimeout(10)
        s.connect((SCRAPER_ADDR, SCRAPER_PORT))
        s.sendall(f"SCRAPE {filename}".encode())
        print(f"Sent SCRAPE command to scraper at {SCRAPER_ADDR}:{SCRAPER_PORT} with config '{filename}'")
        print(f"SCRAPE {filename}")

        # Wait for a confirmation response
        response = s.recv(4096)
        if not response:
            print("Error: No response from scraper.")
            s.close()
            return
        print(f"Received response from scraper: {response.decode()}")

        s.settimeout(5)  # Short timeout to allow Ctrl+C to interrupt
        buffer = ""
        while True:
            try:
                response = s.recv(4096)
                if not response:
                    print("Error: Connection closed by scraper.")
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
                    print(f"\nScraper finished: {line}")
                    break
            else:
                if "ACK: Finished" in buffer:
                    print(f"\nScraper finished: {buffer.strip()}")
                    break
                continue
            break

    except socket.gaierror:
        print(f"Error: Could not resolve scraper address '{SCRAPER_ADDR}'. Is the 'scraper' container running?")
        s.close()
        return
    except socket.timeout:
        print("Error: Scraper did not respond in time.")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
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
