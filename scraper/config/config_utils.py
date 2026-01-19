import json
import logging
import os
from datetime import date, datetime
from typing import Optional

from scraper.config.scraper_config import RepoConfig, ScraperConfig

DEFAULT_FIX_REGEXES = [r"(?i)\bfix(es|ed)?\b", r"(?i)\bbug(s)?\b", r"(?i)\bpatch(ed)?\b"]


def load_config(file_path: str) -> ScraperConfig:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File {file_path} not found")
        return ScraperConfig(repositories=[])
    except json.JSONDecodeError:
        print(f"Error: File {file_path} contains invalid JSON")
        return ScraperConfig(repositories=[])

    repo_configs = []

    raw_repos = data.get("repositories", [])
    if not isinstance(raw_repos, list):
        print("Error: Key 'repositories' must be a list.")
        return ScraperConfig(repositories=[])

    # Global fix_regexes (used if repo doesn't specify its own)
    global_fix_regexes = data.get("fix_regexes", DEFAULT_FIX_REGEXES)

    for entry in raw_repos:
        # Handle both formats:
        # 1. Simple URL string: "https://github.com/owner/repo"
        # 2. Object with url key: {"url": "...", "start_date": "...", ...}
        if isinstance(entry, str):
            # Simple URL string format
            url = entry
            start_dt = None
            end_dt = None
            regexes = global_fix_regexes
        elif isinstance(entry, dict):
            # Object format
            if "url" not in entry:
                print(f"Skipped entry (missing url): {entry}")
                continue
            url = entry["url"]
            start_dt = parse_date(entry.get("start_date"))
            end_dt = parse_date(entry.get("end_date"))
            regexes = entry.get("fix_regexes", global_fix_regexes)
        else:
            print(f"Skipped invalid entry: {entry}")
            continue

        config_obj = RepoConfig(
            url=url,
            start_date=start_dt,
            end_date=end_dt,
            fix_regexes=regexes
        )
        repo_configs.append(config_obj)

    # Parse GitHub tokens (list) - new format
    github_tokens = data.get("github_tokens", [])
    if not isinstance(github_tokens, list):
        github_tokens = []

    # Legacy single token support
    github_token = data.get("github_token")

    # Global target record count
    target_record_count = data.get("target_record_count", 1000)

    # Number of consumer workers
    num_consumer_workers = data.get("num_consumer_workers", max(1, (os.cpu_count() or 4) // 2))

    # Temp work directory (RAM disk)
    temp_work_dir = data.get("temp_work_dir", "/dev/shm" if os.path.exists("/dev/shm") else "/tmp")

    # Queue max size
    queue_max_size = data.get("queue_max_size", 100)

    return ScraperConfig(
        repositories=repo_configs,
        github_tokens=github_tokens,
        github_token=github_token,
        target_record_count=target_record_count,
        num_consumer_workers=num_consumer_workers,
        temp_work_dir=temp_work_dir,
        queue_max_size=queue_max_size
    )


def parse_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        logging.warning(f"Invalid date format: {date_str}. Expected YYYY-MM-DD. Ignoring date.")
        return None
