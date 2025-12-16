import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests

from github import Auth, Github, GithubException

from scraper.config.config_utils import load_config
from scraper.labeling.labeler import Labeler

API_URL = os.getenv("API_URL", "http://fastapi:8000")


def calculate_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_repo_slug(url: str) -> str:
    clean_url = url[:-4] if url.endswith(".git") else url
    match = re.search(r"github\.com/([^/]+)/([^/]+)", clean_url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    raise ValueError(f"Invalid GitHub URL: {url}")


def run_scraper(config_path: str) -> None:
    logging.info(f"Starting scraper with config: {config_path}")

    config = load_config(config_path)
    if not config.repositories:
        logging.warning("No valid repositories found in config.")
        return

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logging.warning("GITHUB_TOKEN not set. Rate limits will be strict.")
        g = Github()
    else:
        auth = Auth.Token(token)
        g = Github(auth=auth)

    for repo_config in config.repositories:
        process_repository(g, repo_config)


def get_github_content(repo: Any, sha: str, path: str) -> str:
    try:
        content_file = repo.get_contents(path, ref=sha)
        return content_file.decoded_content.decode("utf-8")
    except Exception:
        return ""


def get_all_repo_files(repo: Any, sha: str) -> List[str]:
    try:
        tree = repo.get_git_tree(sha, recursive=True)
        return [element.path for element in tree.tree]
    except Exception as e:
        logging.error(f"Failed to fetch file tree: {e}")
        return []


def find_corresponding_file(base_file_path: str, target_extensions: List[str], all_repo_files: List[str]) -> Optional[str]:
    base_dir = os.path.dirname(base_file_path)
    base_name = os.path.splitext(os.path.basename(base_file_path))[0]

    for ext in target_extensions:
        sibling_path = os.path.join(base_dir, base_name + ext)
        if sibling_path in all_repo_files:
            return sibling_path

    for file_path in all_repo_files:
        file_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(file_name)[0]
        file_ext = os.path.splitext(file_name)[1]

        if name_without_ext == base_name and file_ext in target_extensions:
            return file_path

    return None


def format_context(header: str, implementation: str) -> str:
    output = []
    if header.strip():
        output.append(header.strip())

    if implementation.strip():
        output.append(implementation.strip())

    return "\n".join(output)


def save_payload_to_file(payload: Dict[str, Any], output_dir: str = "extracted_data") -> None:
    try:
        os.makedirs(output_dir, exist_ok=True)

        file_hash = payload.get("code_hash", "unknown_hash")
        filename = f"{file_hash}.json"
        filepath = os.path.join(output_dir, filename)

        readable_payload = payload.copy()

        if isinstance(readable_payload.get("code_original"), str):
            readable_payload["code_original"] = readable_payload["code_original"].splitlines()

        if isinstance(readable_payload.get("code_fixed"), str):
            readable_payload["code_fixed"] = readable_payload["code_fixed"].splitlines()

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(readable_payload, f, indent=4, ensure_ascii=False)

        logging.info(f"Saved payload to file: {filepath}")

    except Exception as e:
        logging.error(f"Failed to save payload locally: {e}")


def insert_payload_to_db(payload: Dict[str, Any]) -> Optional[str]:
    """Insert a single payload into MongoDB via the FastAPI service.

    Returns:
        Inserted entry id (as string) on success, otherwise None.
    """
    endpoint = f"{API_URL}/entries/"
    try:
        resp = requests.post(endpoint, json=payload, timeout=15)
        if resp.status_code == 201:
            data = resp.json() if resp.content else {}
            return data.get("id")

        # Duplicate key is treated as a non-fatal condition.
        if resp.status_code == 409:
            logging.info("Entry already exists (duplicate code_hash). Skipping DB insert.")
            return None

        logging.warning(f"DB insert failed: HTTP {resp.status_code}: {resp.text}")
        return None
    except requests.exceptions.RequestException as e:
        logging.warning(f"DB insert request failed: {e}")
        return None


def process_repository(github_client: Any, repo_config: Any) -> None:
    logging.info(f"Processing repository: {repo_config.url}")

    # Initialize labeler for automatic code analysis with config-based mapping
    config_path = os.path.join(os.path.dirname(__file__), "..", "labels_config.json")
    labeler = Labeler(timeout=30, config_path=config_path)

    try:
        repo_slug = get_repo_slug(repo_config.url)
        repo = github_client.get_repo(repo_slug)
    except Exception as e:
        logging.error(f"Could not access repository {repo_config.url}: {e}")
        return

    since_dt = None
    if repo_config.start_date:
        since_dt = datetime.combine(repo_config.start_date, datetime.min.time())

    until_dt = datetime.now()
    if repo_config.end_date:
        until_dt = datetime.combine(repo_config.end_date, datetime.max.time())

    if not since_dt:
        since_dt = datetime(2020, 1, 1)

    processed_count = 0

    try:
        commits = repo.get_commits(since=since_dt, until=until_dt)

        for commit_wrapper in commits:
            if processed_count >= repo_config.target_record_count:
                logging.info(f"Target record count reached for {repo_config.url}")
                break

            msg = commit_wrapper.commit.message
            sha = commit_wrapper.sha

            if repo_config.fix_regexes:
                matched = False
                for pattern in repo_config.fix_regexes:
                    if re.search(pattern, msg, re.IGNORECASE | re.MULTILINE):
                        matched = True
                        break
                if not matched:
                    continue

            if not commit_wrapper.parents:
                continue
            parent_sha = commit_wrapper.parents[0].sha

            files_modified_in_commit = commit_wrapper.files
            processed_bases: Set[str] = set()
            repo_files_cache: Optional[List[str]] = None

            for f in files_modified_in_commit:
                path = f.filename

                if f.status == "removed":
                    continue
                if "test" in path.lower():
                    continue
                if not path.endswith((".cpp", ".cxx", ".cc", ".h", ".hpp")):
                    continue

                filename = os.path.basename(path)
                base_name = os.path.splitext(filename)[0]

                if base_name in processed_bases:
                    continue
                processed_bases.add(base_name)

                if repo_files_cache is None:
                    repo_files_cache = get_all_repo_files(repo, sha)

                header_path = None
                impl_path = None

                if path.endswith((".h", ".hpp")):
                    header_path = path
                    impl_path = find_corresponding_file(path, [".cpp", ".cxx", ".cc"], repo_files_cache)
                else:
                    impl_path = path
                    header_path = find_corresponding_file(path, [".h", ".hpp"], repo_files_cache)

                h_before = ""
                if header_path:
                    h_before = get_github_content(repo, parent_sha, header_path)

                h_after = ""
                if header_path:
                    h_after = get_github_content(repo, sha, header_path)

                cpp_before = ""
                if impl_path:
                    cpp_before = get_github_content(repo, parent_sha, impl_path)

                cpp_after = ""
                if impl_path:
                    cpp_after = get_github_content(repo, sha, impl_path)

                if not h_after and not cpp_after:
                    continue

                full_code_before = format_context(h_before, cpp_before)
                full_code_fixed = format_context(h_after, cpp_after)

                if full_code_before == full_code_fixed:
                    continue

                # ===== LABELING STAGE =====
                logging.info(f"Analyzing code for labeling: {sha[:7]} / {base_name}")
                try:
                    labels = labeler.analyze(full_code_before, full_code_fixed)

                    # Skip if no issues were found (empty cppcheck list after diff)
                    if not labels.get("cppcheck"):
                        logging.info(f"Skipping {sha[:7]} - no cppcheck issues found after diff")
                        continue
                    
                    # Provide an empty object when no clang details are available.
                    if isinstance(labels, dict):
                        labels.setdefault("clang", {})

                except Exception as e:
                    logging.warning(f"Labeling failed for {sha[:7]}: {e}. Skipping.")
                    continue

                payload = {
                    "code_original": full_code_before,
                    "code_fixed": full_code_fixed,
                    "code_hash": calculate_hash(full_code_before),
                    "repo": {"url": repo_config.url, "commit_hash": sha, "commit_date": (commit_wrapper.commit.author.date.isoformat())},
                    "ingest_timestamp": datetime.now().isoformat(),
                    "labels": labels,
                }

                save_payload_to_file(payload)

                inserted_id = insert_payload_to_db(payload)
                if not inserted_id:
                    logging.info(f"[SKIP] duplicate or insert failed (not counted): {sha[:7]} / {base_name}")
                    continue

                logging.info(f"Inserted entry into DB: id={inserted_id}")
                processed_count += 1
                logging.info(f"[READY] extracted+inserted: {sha[:7]} / {base_name}")

    except GithubException as e:
        logging.error(f"GitHub API Error for {repo_config.url}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error for {repo_config.url}: {e}")
