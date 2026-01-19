"""
Producer-Consumer Parallel Scraper Engine

This module implements a parallel scraping architecture:
- Producers: One per repository, fetch commits and push candidate tasks to a queue
- Consumers: Configurable number of workers that label code and insert into DB
- Shared state: Global counter for records, stop event for graceful shutdown
"""

import hashlib
import json
import logging
import multiprocessing as mp
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from queue import Empty
from typing import Any, Callable, Dict, List, Optional, Set

import requests
from github import Auth, Github, GithubException

from scraper.config.config_utils import load_config
from scraper.config.scraper_config import RepoConfig

# Configure logging for multiprocessing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(processName)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

API_URL = os.getenv("API_URL", "http://fastapi:8000")

# Sentinel value to signal consumers to stop
POISON_PILL = None


@dataclass
class CandidateTask:
    """
    A candidate code pair to be processed by consumers.
    Contains all data needed for labeling and DB insertion.
    """
    code_original: str
    code_fixed: str
    repo_url: str
    commit_sha: str
    commit_date: str
    base_name: str  # For logging purposes


def calculate_hash(text: str) -> str:
    """Calculate SHA-256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_repo_slug(url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    clean_url = url[:-4] if url.endswith(".git") else url
    match = re.search(r"github\.com/([^/]+)/([^/]+)", clean_url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    raise ValueError(f"Invalid GitHub URL: {url}")


# =============================================================================
# PRODUCER FUNCTIONS (Fetchers)
# =============================================================================

def get_github_content(repo: Any, sha: str, path: str) -> str:
    """Fetch file content from GitHub at a specific commit."""
    try:
        content_file = repo.get_contents(path, ref=sha)
        return content_file.decoded_content.decode("utf-8")
    except Exception:
        return ""


def get_all_repo_files(repo: Any, sha: str) -> List[str]:
    """Get list of all files in repository at a specific commit."""
    try:
        tree = repo.get_git_tree(sha, recursive=True)
        return [element.path for element in tree.tree]
    except Exception as e:
        logging.error(f"Failed to fetch file tree: {e}")
        return []


def find_corresponding_file(base_file_path: str, target_extensions: List[str], all_repo_files: List[str]) -> Optional[str]:
    """Find corresponding header/implementation file."""
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
    """Combine header and implementation into single code block."""
    output = []
    if header.strip():
        output.append(header.strip())
    if implementation.strip():
        output.append(implementation.strip())
    return "\n".join(output)


def producer_task(
    repo_config: RepoConfig,
    token: Optional[str],
    task_queue: mp.Queue,
    stop_event: mp.Event,
    global_counter: mp.Value,
    target_count: int,
    producer_name: str
) -> None:
    """
    Producer process: Fetches commits from a repository and pushes candidate tasks to queue.

    Args:
        repo_config: Repository configuration
        token: GitHub API token for this producer
        task_queue: Shared queue to push candidate tasks
        stop_event: Event to signal stop
        global_counter: Shared counter for total records
        target_count: Global target record count
        producer_name: Name for logging
    """
    mp.current_process().name = producer_name
    logging.info(f"Starting producer for {repo_config.url}")

    try:
        # Initialize GitHub client
        if token:
            auth = Auth.Token(token.strip())
            g = Github(auth=auth)
            try:
                user = g.get_user().login
                logging.info(f"Authenticated as: {user}")
            except Exception as e:
                logging.warning(f"Auth check failed: {e}")
        else:
            logging.warning("No token - using unauthenticated API (strict rate limits)")
            g = Github()

        repo_slug = get_repo_slug(repo_config.url)
        repo = g.get_repo(repo_slug)

        # Date range setup
        since_dt = None
        if repo_config.start_date:
            since_dt = datetime.combine(repo_config.start_date, datetime.min.time())
        if not since_dt:
            since_dt = datetime(2020, 1, 1)

        until_dt = datetime.now()
        if repo_config.end_date:
            until_dt = datetime.combine(repo_config.end_date, datetime.max.time())

        commits = repo.get_commits(since=since_dt, until=until_dt)
        candidates_pushed = 0

        for commit_wrapper in commits:
            # Check if we should stop
            if stop_event.is_set():
                logging.info("Stop signal received, finishing producer")
                break

            # Check global counter
            with global_counter.get_lock():
                if global_counter.value >= target_count:
                    logging.info("Global target reached, finishing producer")
                    break

            msg = commit_wrapper.commit.message
            sha = commit_wrapper.sha

            # Apply fix regex filters
            if repo_config.fix_regexes:
                matched = False
                for pattern in repo_config.fix_regexes:
                    if re.search(pattern, msg, re.IGNORECASE | re.MULTILINE):
                        matched = True
                        break
                if not matched:
                    continue

            # Need parent commit for diff
            if not commit_wrapper.parents:
                continue
            parent_sha = commit_wrapper.parents[0].sha

            files_modified = commit_wrapper.files
            processed_bases: Set[str] = set()
            repo_files_cache: Optional[List[str]] = None

            for f in files_modified:
                path = f.filename

                # Skip removed files and test files
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

                # Find header and implementation files
                header_path = None
                impl_path = None

                if path.endswith((".h", ".hpp")):
                    header_path = path
                    impl_path = find_corresponding_file(path, [".cpp", ".cxx", ".cc"], repo_files_cache)
                else:
                    impl_path = path
                    header_path = find_corresponding_file(path, [".h", ".hpp"], repo_files_cache)

                # Get file contents before and after
                h_before = get_github_content(repo, parent_sha, header_path) if header_path else ""
                h_after = get_github_content(repo, sha, header_path) if header_path else ""
                cpp_before = get_github_content(repo, parent_sha, impl_path) if impl_path else ""
                cpp_after = get_github_content(repo, sha, impl_path) if impl_path else ""

                if not h_after and not cpp_after:
                    continue

                full_code_before = format_context(h_before, cpp_before)
                full_code_fixed = format_context(h_after, cpp_after)

                if full_code_before == full_code_fixed:
                    continue

                # Create candidate task and push to queue
                task = CandidateTask(
                    code_original=full_code_before,
                    code_fixed=full_code_fixed,
                    repo_url=repo_config.url,
                    commit_sha=sha,
                    commit_date=commit_wrapper.commit.author.date.isoformat(),
                    base_name=base_name
                )

                # Use put with timeout to allow checking stop_event
                while not stop_event.is_set():
                    try:
                        task_queue.put(task, timeout=1)
                        candidates_pushed += 1
                        logging.debug(f"Pushed task: {sha[:7]}/{base_name}")
                        break
                    except Exception:
                        continue

        logging.info(f"Producer finished. Pushed {candidates_pushed} candidates.")

    except GithubException as e:
        logging.error(f"GitHub API Error: {e}")
    except Exception as e:
        logging.error(f"Producer error: {e}")


# =============================================================================
# CONSUMER FUNCTIONS (Labelers/Workers)
# =============================================================================

def save_payload_to_file(payload: Dict[str, Any], output_dir: str = "extracted_data") -> None:
    """Save payload to local JSON file."""
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

        logging.debug(f"Saved payload to: {filepath}")
    except Exception as e:
        logging.error(f"Failed to save payload: {e}")


def insert_payload_to_db(payload: Dict[str, Any]) -> Optional[str]:
    """Insert payload into MongoDB via FastAPI."""
    endpoint = f"{API_URL}/entries/"
    try:
        resp = requests.post(endpoint, json=payload, timeout=15)
        if resp.status_code == 201:
            data = resp.json() if resp.content else {}
            return data.get("id")
        if resp.status_code == 409:
            logging.debug("Duplicate entry, skipping")
            return None
        logging.warning(f"DB insert failed: HTTP {resp.status_code}")
        return None
    except requests.exceptions.RequestException as e:
        logging.warning(f"DB request failed: {e}")
        return None


def consumer_task(
    task_queue: mp.Queue,
    global_counter: mp.Value,
    stop_event: mp.Event,
    target_count: int,
    temp_work_dir: str,
    consumer_id: int
) -> None:
    """
    Consumer process: Pops tasks from queue, labels code, and inserts into DB.

    Args:
        task_queue: Shared queue to pop candidate tasks from
        global_counter: Shared counter for successful inserts
        stop_event: Event to signal stop
        target_count: Global target record count
        temp_work_dir: Directory for temporary files (RAM disk)
        consumer_id: Worker ID for logging
    """
    consumer_name = f"Consumer-{consumer_id}"
    mp.current_process().name = consumer_name
    logging.info("Starting consumer worker")

    # Import labeler here to avoid pickling issues
    from scraper.labeling.labeler import Labeler

    # Initialize labeler with RAM-based temp directory
    config_path = os.path.join(os.path.dirname(__file__), "..", "labels_config.json")
    labeler = Labeler(timeout=30, config_path=config_path, temp_dir=temp_work_dir)

    processed_count = 0
    inserted_count = 0

    while True:
        # Check if target reached
        with global_counter.get_lock():
            if global_counter.value >= target_count:
                logging.info("Global target reached, stopping consumer")
                break

        try:
            task = task_queue.get(timeout=2)
        except Empty:
            # Check if stop event is set and queue is empty
            if stop_event.is_set() and task_queue.empty():
                logging.info("Queue empty and stop signal received, finishing")
                break
            continue

        # Check for poison pill
        if task is POISON_PILL:
            logging.info("Received poison pill, finishing")
            break

        if not isinstance(task, CandidateTask):
            continue

        processed_count += 1

        try:
            # Run labeling
            labels = labeler.analyze(task.code_original, task.code_fixed)

            # Skip if no issues found
            if not labels.get("cppcheck"):
                logging.debug(f"No issues found for {task.commit_sha[:7]}/{task.base_name}")
                continue

            labels.setdefault("clang", {})

            # Build payload
            payload = {
                "code_original": task.code_original,
                "code_fixed": task.code_fixed,
                "code_hash": calculate_hash(task.code_original),
                "repo": {
                    "url": task.repo_url,
                    "commit_hash": task.commit_sha,
                    "commit_date": task.commit_date
                },
                "ingest_timestamp": datetime.now().isoformat(),
                "labels": labels,
            }

            # Save locally
            save_payload_to_file(payload)

            # Insert to DB
            inserted_id = insert_payload_to_db(payload)

            if inserted_id:
                inserted_count += 1
                with global_counter.get_lock():
                    global_counter.value += 1
                    current_total = global_counter.value

                logging.info(f"Inserted {task.commit_sha[:7]}/{task.base_name} (Total: {current_total}/{target_count})")

                # Check if we hit target
                if current_total >= target_count:
                    logging.info("Target reached! Signaling stop.")
                    stop_event.set()
                    break

        except Exception as e:
            logging.warning(f"Consumer error processing {task.commit_sha[:7]}: {e}")
            continue

    logging.info(f"Consumer finished. Processed: {processed_count}, Inserted: {inserted_count}")


# =============================================================================
# MONITOR FUNCTION
# =============================================================================

def monitor_progress(
    global_counter: mp.Value,
    target_count: int,
    task_queue: mp.Queue,
    stop_event: mp.Event,
    progress_callback: Optional[Callable] = None,
    interval: float = 5.0
) -> None:
    """
    Monitor thread: Logs progress and calls progress callback.

    Args:
        global_counter: Shared counter for total records
        target_count: Global target
        task_queue: Task queue (to report size)
        stop_event: Stop event
        progress_callback: Optional callback for external progress reporting
        interval: Seconds between progress updates
    """
    last_count = 0

    while not stop_event.is_set():
        time.sleep(interval)

        with global_counter.get_lock():
            current = global_counter.value

        queue_size = task_queue.qsize() if hasattr(task_queue, 'qsize') else -1
        rate = (current - last_count) / interval

        logging.info(f"Progress: {current}/{target_count} records | Queue: {queue_size} | Rate: {rate:.1f}/s")

        if progress_callback:
            progress_callback(current, target_count, f"queue:{queue_size}")

        last_count = current

        if current >= target_count:
            break


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

def run_scraper(config_path: str, progress_callback: Optional[Callable] = None) -> None:
    """
    Main entry point: Orchestrates producer-consumer parallel scraping.

    Args:
        config_path: Path to configuration JSON file
        progress_callback: Optional callback for progress updates
    """
    logging.info(f"Starting parallel scraper with config: {config_path}")

    config = load_config(config_path)
    if not config.repositories:
        logging.warning("No repositories found in config.")
        return

    tokens = config.get_effective_tokens()
    target_count = config.target_record_count
    num_consumers = config.num_consumer_workers
    temp_dir = config.temp_work_dir

    logging.info("Configuration:")
    logging.info(f"  - Repositories: {len(config.repositories)}")
    logging.info(f"  - GitHub tokens: {len(tokens)}")
    logging.info(f"  - Consumer workers: {num_consumers}")
    logging.info(f"  - Target records: {target_count}")
    logging.info(f"  - Temp directory: {temp_dir}")

    # Ensure temp directory exists
    os.makedirs(temp_dir, exist_ok=True)

    # Create shared state
    task_queue = mp.Queue(maxsize=config.queue_max_size)
    global_counter = mp.Value('i', 0)
    stop_event = mp.Event()

    # Assign tokens to repositories (round-robin)
    repo_token_pairs = []
    for i, repo_config in enumerate(config.repositories):
        token = tokens[i % len(tokens)] if tokens else None
        repo_token_pairs.append((repo_config, token))

    # Start producer processes
    producers = []
    for i, (repo_config, token) in enumerate(repo_token_pairs):
        repo_name = get_repo_slug(repo_config.url).split('/')[-1]
        producer_name = f"Producer-{repo_name}"

        p = mp.Process(
            target=producer_task,
            args=(repo_config, token, task_queue, stop_event, global_counter, target_count, producer_name),
            name=producer_name
        )
        p.start()
        producers.append(p)
        logging.info(f"Started {producer_name}")

    # Start consumer processes
    consumers = []
    for i in range(num_consumers):
        c = mp.Process(
            target=consumer_task,
            args=(task_queue, global_counter, stop_event, target_count, temp_dir, i),
            name=f"Consumer-{i}"
        )
        c.start()
        consumers.append(c)
        logging.info(f"Started Consumer-{i}")

    # Start monitor in main thread
    try:
        while True:
            # Check if all producers finished
            producers_alive = any(p.is_alive() for p in producers)

            # Check progress
            with global_counter.get_lock():
                current = global_counter.value

            queue_size = task_queue.qsize() if hasattr(task_queue, 'qsize') else -1

            logging.info(f"Progress: {current}/{target_count} | Queue: {queue_size} | Producers alive: {producers_alive}")

            if progress_callback:
                progress_callback(current, target_count, f"q:{queue_size}")

            # Check stop conditions
            if current >= target_count:
                logging.info("Target reached! Initiating shutdown...")
                stop_event.set()
                break

            if not producers_alive and task_queue.empty():
                logging.info("All producers finished and queue empty. Initiating shutdown...")
                stop_event.set()
                break

            time.sleep(5)

    except KeyboardInterrupt:
        logging.info("Interrupted! Initiating graceful shutdown...")
        stop_event.set()

    # Wait for producers to finish
    logging.info("Waiting for producers to finish...")
    for p in producers:
        p.join(timeout=10)
        if p.is_alive():
            logging.warning(f"Force terminating {p.name}")
            p.terminate()

    # Send poison pills to consumers
    logging.info("Sending shutdown signal to consumers...")
    for _ in consumers:
        try:
            task_queue.put(POISON_PILL, timeout=1)
        except Exception:
            pass

    # Wait for consumers to finish
    logging.info("Waiting for consumers to finish...")
    for c in consumers:
        c.join(timeout=30)
        if c.is_alive():
            logging.warning(f"Force terminating {c.name}")
            c.terminate()

    # Final report
    with global_counter.get_lock():
        final_count = global_counter.value

    logging.info("=" * 50)
    logging.info("SCRAPING COMPLETE")
    logging.info(f"Total records inserted: {final_count}/{target_count}")
    logging.info("=" * 50)
