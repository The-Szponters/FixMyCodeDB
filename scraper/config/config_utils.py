import json
import logging
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

    for entry in raw_repos:
        if "url" not in entry or "target_record_count" not in entry:
            print(f"Skipped entry (missing url or target_record_count): {entry}")
            continue

        url = entry["url"]
        count = int(entry["target_record_count"])

        start_dt = parse_date(entry.get("start_date"))
        end_dt = parse_date(entry.get("end_date"))

        regexes = entry.get("fix_regexes")
        if not regexes:
            regexes = DEFAULT_FIX_REGEXES

        config_obj = RepoConfig(url=url, target_record_count=count, start_date=start_dt, end_date=end_dt, fix_regexes=regexes)
        repo_configs.append(config_obj)

    return ScraperConfig(repositories=repo_configs)


def parse_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        logging.warning(f"Invalid date format: {date_str}. Expected YYYY-MM-DD. Ignoring date.")
        return None
