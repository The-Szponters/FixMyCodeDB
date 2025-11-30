from cli.command_tree import CommandTree
import os
import requests
import json
import socket


API_BASE = os.getenv("API_URL", "http://localhost:8000")
SCRAPER_ADDR = os.getenv("SCRAPER_ADDR", "127.0.0.1")
SCRAPER_PORT = os.getenv("SCRAPER_PORT", 8080)

FILTER_PARAMS = {
    "limit": "100",
    "repo_url": "",
    "commit_hash": "",
    "code_hash": "",
    # Boolean flags (User types 'true', '1', or leaves empty)
    "has_memory_errors": "",
    "has_undefined_behavior": "",
    "has_correctness_issues": "",
    "has_performance_issues": "",
    "has_style_issues": ""
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
        "has_memory_errors": "labels.groups.memory_errors",
        "has_undefined_behavior": "labels.groups.undefined_behavior",
        "has_correctness_issues": "labels.groups.correctness",
        "has_performance_issues": "labels.groups.performance",
        "has_style_issues": "labels.groups.style"
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

    payload = {
        "filter": query_filter,
        "limit": limit,
        "sort": {}
    }

    endpoint = f"{API_BASE}/entries/query/"

    try:
        response = requests.post(endpoint, json=payload, timeout=5)
        response.raise_for_status()

        data = response.json()
        count = len(data)
        print(f"✅ Success! API returned {count} entries matching your criteria.")

        try:
            with open(params['target file'], 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Data imported to {params['target file']}")
        except Exception as e:
            print(f"❌ Error writing to file: {e}")

        if count > 0:
            print(f"Sample ID: {data[0].get('_id')}")

    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Could not connect to {API_BASE}. Is the 'fastapi' container running?")
    except requests.exceptions.HTTPError as e:
        print(f"❌ API Error: {e.response.text}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")


def do_scrape(params):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", 0))
    s.settimeout(5)
    filename = params.get("config_file")

    try:
        s.sendto(f"SCRAPE {filename}".encode(), (SCRAPER_ADDR, int(SCRAPER_PORT)))
        print(f"Sent SCRAPE command to scraper at {SCRAPER_ADDR}:{SCRAPER_PORT} with config '{filename}'")
        print(f"SCRAPE {filename}")

        # Wait for a response (blocking)
        response, _ = s.recvfrom(4096)
        print(f"Received response from scraper: {response.decode()}")

    except socket.timeout:
        print("❌ Error: Scraper did not respond in time.")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
    finally:
        s.close()


def do_label(params):
    print("Labeling...")


class CLIApp(CommandTree):
    def __init__(self):
        super().__init__()

        self.add_command("scrape", do_scrape, param_set={"config_file": "config.json"})
        self.add_command("import", do_import, param_set={"sort by": "ingest_timestamp", **FILTER_PARAMS, "target file": "import.json"})
        self.add_command("label", do_label, param_set={})
