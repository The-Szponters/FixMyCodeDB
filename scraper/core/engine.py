"""
Core scraper engine with Repository-Based Parallelism.

This module implements:
- 1 Downloader Thread per Repository (threading.Thread for I/O-bound operations)
- Multiple downloaders share tokens via round-robin with thread-safe rate limiting
- Analyzer processes (Consumers): Process commits with cppcheck and save to DB
- TokenManager for thread-safe GitHub API access with rate limit handling
"""

import hashlib
import json
import logging
import multiprocessing as mp
import os
import re
import shutil
import signal
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from multiprocessing import Queue
from multiprocessing.managers import DictProxy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import requests
from github import Auth, Github, GithubException

from scraper.config.config_utils import load_config
from scraper.labeling.labeler import Labeler

DEBUG_MODE = os.getenv("SCRAPER_DEBUG", "0") == "1"

if DEBUG_MODE:
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
    )
else:
    logging.basicConfig(level=logging.CRITICAL)

logger = logging.getLogger(__name__)

API_URL = os.getenv("API_URL", "http://fastapi:8000")


# ============== Utility Functions ==============

def calculate_hash(text: str) -> str:
    """Calculate SHA256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_repo_slug(url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    clean_url = url[:-4] if url.endswith(".git") else url
    match = re.search(r"github\.com/([^/]+)/([^/]+)", clean_url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    raise ValueError(f"Invalid GitHub URL: {url}")


# ============== Data Classes ==============

@dataclass
class AnalysisTask:
    """Task item for the analysis queue."""
    repo_slug: str
    repo_url: str
    commit_sha: str
    parent_sha: str
    file_path: str
    base_name: str
    header_path: Optional[str]
    impl_path: Optional[str]
    temp_dir: str
    commit_message: str
    commit_date: str
    fix_regexes: List[str] = field(default_factory=list)


@dataclass
class ProcessStatus:
    """Status info for a single process (for TUI display)."""
    process_id: str
    process_type: str  # "producer" or "consumer"
    status: str  # "idle", "working", "done", "error"
    current_repo: str = ""
    current_commit: str = ""
    current_action: str = ""
    items_processed: int = 0
    last_update: float = field(default_factory=time.time)


def run_scraper(config_path: str, progress_callback=None) -> None:
    """
    Legacy interface - runs the scraper sequentially.
    For the new parallel architecture, use ScraperOrchestrator instead.
    """
    logger.info(f"Starting scraper (legacy mode) with config: {config_path}")

    config = load_config(config_path)
    if not config.repositories:
        logger.warning("No valid repositories found in config.")
        return

    token = config.github_token or os.getenv("GITHUB_TOKEN")
    if token:
        token = token.strip()

    if not token:
        logger.warning("GITHUB_TOKEN not set (config or env). Rate limits will be strict.")
        g = Github()
    else:
        auth = Auth.Token(token)
        g = Github(auth=auth)
        try:
            user = g.get_user().login
            logger.info(f"Authenticated as GitHub user: {user}")
            rate_limit = g.get_rate_limit()

            # Handle different PyGithub versions/structures
            limit_data = None
            if hasattr(rate_limit, 'core'):
                limit_data = rate_limit.core
            elif hasattr(rate_limit, 'rate'):
                limit_data = rate_limit.rate

            if limit_data:
                logger.info(f"Rate Limit: {limit_data.remaining}/{limit_data.limit} (Resets at {limit_data.reset})")
            else:
                logger.warning(f"Could not determine rate limit structure from: {type(rate_limit)}")

        except Exception as e:
            logger.error(f"Authentication check failed: {e}")
            # Continue even if check failed

    for repo_config in config.repositories:
        _process_repository_legacy(g, repo_config, progress_callback)


# ============== File Content Helpers ==============

def get_github_content(repo: Any, sha: str, path: str) -> str:
    """Fetch file content from GitHub at a specific commit."""
    try:
        content_file = repo.get_contents(path, ref=sha)
        return content_file.decoded_content.decode("utf-8")
    except Exception:
        return ""


def get_all_repo_files(repo: Any, sha: str) -> List[str]:
    """Get list of all files in repo at a specific commit."""
    try:
        tree = repo.get_git_tree(sha, recursive=True)
        return [element.path for element in tree.tree]
    except Exception as e:
        logger.error(f"Failed to fetch file tree: {e}")
        return []


def find_corresponding_file(
    base_file_path: str,
    target_extensions: List[str],
    all_repo_files: List[str]
) -> Optional[str]:
    """Find a corresponding header/implementation file."""
    base_dir = os.path.dirname(base_file_path)
    base_name = os.path.splitext(os.path.basename(base_file_path))[0]

    # Check sibling first
    for ext in target_extensions:
        sibling_path = os.path.join(base_dir, base_name + ext)
        if sibling_path in all_repo_files:
            return sibling_path

    # Then search all files
    for file_path in all_repo_files:
        file_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(file_name)[0]
        file_ext = os.path.splitext(file_name)[1]

        if name_without_ext == base_name and file_ext in target_extensions:
            return file_path

    return None


def format_context(header: str, implementation: str) -> str:
    """Combine header and implementation into a single context."""
    output = []
    if header.strip():
        output.append(header.strip())
    if implementation.strip():
        output.append(implementation.strip())
    return "\n".join(output)


def save_file_to_tmpfs(content: str, temp_dir: str, filename: str) -> str:
    """Save content to a temp file in tmpfs (RAM disk)."""
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return file_path


# ============== Database Operations ==============

def insert_payload_to_db(payload: Dict[str, Any]) -> Optional[str]:
    """Insert a single payload into MongoDB via the FastAPI service."""
    endpoint = f"{API_URL}/entries/"
    try:
        resp = requests.post(endpoint, json=payload, timeout=15)
        if resp.status_code == 201:
            data = resp.json() if resp.content else {}
            return data.get("id")

        if resp.status_code == 409:
            logger.info("Entry already exists (duplicate). Skipping DB insert.")
            return None

        logger.warning(f"DB insert failed: HTTP {resp.status_code}: {resp.text}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"DB insert request failed: {e}")
        return None


def save_payload_to_file(payload: Dict[str, Any], output_dir: str = "extracted_data") -> None:
    """Save payload to a JSON file."""
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

        logger.debug(f"Saved payload to file: {filepath}")
    except Exception as e:
        logger.error(f"Failed to save payload locally: {e}")


# ============== Token Manager for Thread-Safe Token Sharing ==============

class TokenManager:
    """
    Thread-safe manager for GitHub API tokens.

    Handles:
    - Round-robin token assignment to downloaders
    - Per-token rate limit tracking and blocking
    - Thread-safe access via locks
    """

    def __init__(self, tokens: List[str]):
        if not tokens:
            raise ValueError("At least one GitHub token is required")

        self.tokens = tokens
        self.token_count = len(tokens)

        # Per-token locks and rate limit info
        self._token_locks: Dict[str, threading.Lock] = {t: threading.Lock() for t in tokens}
        self._rate_limit_reset: Dict[str, float] = {t: 0.0 for t in tokens}  # Unix timestamp
        self._rate_limit_remaining: Dict[str, int] = {t: 5000 for t in tokens}

        # Global lock for status updates
        self._status_lock = threading.Lock()

        # Token labels (A, B, C, ...)
        self._token_labels = {t: chr(65 + i) for i, t in enumerate(tokens)}

    def get_token_for_index(self, index: int) -> str:
        """Get token for a downloader index (round-robin assignment)."""
        return self.tokens[index % self.token_count]

    def get_token_label(self, token: str) -> str:
        """Get human-readable label for a token (A, B, C, ...)."""
        return self._token_labels.get(token, "?")

    def acquire_token(self, token: str, timeout: float = 300) -> bool:
        """
        Acquire permission to use a token (thread-safe).
        Blocks if rate limited until reset time or timeout.

        Returns True if acquired, False if timeout.
        """
        start_time = time.time()

        while True:
            # Check if rate limited
            reset_time = self._rate_limit_reset.get(token, 0)
            now = time.time()

            if reset_time > now:
                # Token is rate limited - wait
                wait_time = min(reset_time - now, timeout - (now - start_time))
                if wait_time <= 0:
                    return False  # Timeout

                label = self.get_token_label(token)
                logger.debug(f"Token {label} rate limited, waiting {wait_time:.1f}s")
                time.sleep(min(wait_time, 5.0))  # Check every 5s max
                continue

            # Token available
            return True

    def update_rate_limit(self, token: str, remaining: int, reset_timestamp: float):
        """Update rate limit info after an API call."""
        with self._status_lock:
            self._rate_limit_remaining[token] = remaining
            if remaining <= 0:
                self._rate_limit_reset[token] = reset_timestamp
            else:
                self._rate_limit_reset[token] = 0.0

    def handle_rate_limit_error(self, token: str, reset_timestamp: float):
        """Handle a 403 rate limit error - mark token as blocked."""
        with self._status_lock:
            self._rate_limit_reset[token] = reset_timestamp
            self._rate_limit_remaining[token] = 0

        label = self.get_token_label(token)
        logger.warning(f"Token {label} rate limited until {datetime.fromtimestamp(reset_timestamp)}")

    def get_token_status(self, token: str) -> Dict[str, Any]:
        """Get current status of a token."""
        return {
            "label": self.get_token_label(token),
            "remaining": self._rate_limit_remaining.get(token, 0),
            "reset_time": self._rate_limit_reset.get(token, 0),
            "is_limited": self._rate_limit_reset.get(token, 0) > time.time()
        }


# ============== Downloader Thread (1 per Repository) ==============

class DownloaderThread(threading.Thread):
    """
    Downloader thread that handles exactly ONE repository.

    Features:
    - Uses shared TokenManager for thread-safe API access
    - Automatically handles rate limiting without blocking other threads
    - Reports status to shared dict for TUI display
    """

    def __init__(
        self,
        thread_id: int,
        repo_url: str,
        token: str,
        token_manager: TokenManager,
        analysis_queue: Queue,
        state_dict: DictProxy,
        status_dict: DictProxy,
        stats_dict: DictProxy,
        config: Dict[str, Any],
        stop_event: threading.Event,
    ):
        repo_slug = get_repo_slug(repo_url)
        super().__init__(name=f"DL-{repo_slug}", daemon=True)

        self.thread_id = thread_id
        self.repo_url = repo_url
        self.repo_slug = repo_slug
        self.token = token
        self.token_manager = token_manager
        self.analysis_queue = analysis_queue
        self.state_dict = state_dict
        self.status_dict = status_dict
        self.stats_dict = stats_dict
        self.config = config
        self.stop_event = stop_event

        # Config values
        self.batch_size = config.get("batch_size_per_repo", 10)
        self.temp_storage_path = config.get("temp_storage_path", "/tmp/scraper")
        self.fix_regexes = config.get("fix_regexes", [])
        self.target_record_count = config.get("target_record_count", 1000)

        # Track progress
        self.commits_processed = 0
        self.total_commits = 0

    def _update_status(self, status: str, commit: str = "", action: str = "",
                       progress: str = ""):
        """Update status in shared dict for TUI display."""
        key = f"D{self.thread_id}"
        token_label = self.token_manager.get_token_label(self.token)

        self.status_dict[key] = {
            "type": "downloader",
            "status": status,
            "repo": self.repo_slug,
            "commit": commit,
            "action": action,
            "progress": progress,
            "token_label": token_label,
            "timestamp": time.time()
        }

    def _is_commit_processed(self, commit_sha: str) -> bool:
        """Check if commit was already processed."""
        key = f"processed:{self.repo_slug}:{commit_sha}"
        return key in self.state_dict

    def _mark_commit_processed(self, commit_sha: str):
        """Mark commit as processed."""
        key = f"processed:{self.repo_slug}:{commit_sha}"
        self.state_dict[key] = True

    def run(self):
        """Main downloader thread loop."""
        logger.info(f"Downloader [{self.repo_slug}] starting")
        self._update_status("starting", action="Initializing...")

        # Initialize GitHub client
        try:
            auth = Auth.Token(self.token)
            github_client = Github(auth=auth)
            # Verify authentication
            user = github_client.get_user().login
            logger.debug(f"[{self.repo_slug}] Authenticated as: {user}")
        except Exception as e:
            logger.error(f"[{self.repo_slug}] Auth failed: {e}")
            self._update_status("error", action=f"Auth failed: {e}")
            return

        # Process repository until stop or batch complete
        try:
            self._process_repository(github_client)
        except Exception as e:
            logger.error(f"[{self.repo_slug}] Error: {e}")
            self._update_status("error", action=str(e)[:50])

        self._update_status("done", action=f"Completed {self.commits_processed} commits")
        logger.info(f"Downloader [{self.repo_slug}] finished: {self.commits_processed} commits")

    def _process_repository(self, github_client: Github):
        """Process commits from the assigned repository."""
        self._update_status("working", action="Fetching commits...")

        # Acquire token before API call
        if not self.token_manager.acquire_token(self.token):
            logger.warning(f"[{self.repo_slug}] Timeout waiting for token")
            return

        try:
            repo = github_client.get_repo(self.repo_slug)
        except GithubException as e:
            self._handle_github_error(e)
            return
        except Exception as e:
            logger.error(f"[{self.repo_slug}] Could not access repo: {e}")
            return

        # Get commits
        try:
            commits = repo.get_commits()
            # Estimate total (may not be accurate for large repos)
            self.total_commits = min(commits.totalCount, self.batch_size)
        except GithubException as e:
            self._handle_github_error(e)
            return

        # Process commits
        for commit_wrapper in commits:
            if self.stop_event.is_set():
                break

            if self.commits_processed >= self.batch_size:
                break

            sha = commit_wrapper.sha

            # Skip if already processed
            if self._is_commit_processed(sha):
                continue

            msg = commit_wrapper.commit.message

            # Check fix patterns
            if self.fix_regexes:
                matched = any(
                    re.search(pattern, msg, re.IGNORECASE | re.MULTILINE)
                    for pattern in self.fix_regexes
                )
                if not matched:
                    continue

            # Need parent for diff
            if not commit_wrapper.parents:
                continue
            parent_sha = commit_wrapper.parents[0].sha

            # Update progress
            progress = f"{self.commits_processed + 1}/{self.batch_size}"
            self._update_status("working", commit=sha[:7],
                              action=f"Downloading Commit {progress}")

            # Acquire token before processing
            if not self.token_manager.acquire_token(self.token):
                logger.warning(f"[{self.repo_slug}] Timeout waiting for token")
                break

            try:
                self._process_commit_files(
                    repo, commit_wrapper, parent_sha, github_client
                )
                self.commits_processed += 1
                self._mark_commit_processed(sha)

                # Update global stats
                with threading.Lock():
                    current = self.stats_dict.get("total_processed", 0)
                    self.stats_dict["total_processed"] = current + 1

            except GithubException as e:
                if not self._handle_github_error(e):
                    break  # Unrecoverable error

    def _handle_github_error(self, e: GithubException) -> bool:
        """
        Handle GitHub API errors.
        Returns True if should continue, False if should stop.
        """
        if e.status == 403:
            # Rate limited
            reset_time = time.time() + 60  # Default: wait 60s

            # Try to get actual reset time from headers
            if hasattr(e, 'headers') and 'X-RateLimit-Reset' in e.headers:
                reset_time = float(e.headers['X-RateLimit-Reset'])

            self.token_manager.handle_rate_limit_error(self.token, reset_time)
            self._update_status("rate_limited",
                              action=f"Rate limited, waiting...")

            # Wait for rate limit reset
            if self.token_manager.acquire_token(self.token, timeout=300):
                return True  # Recovered
            return False  # Timeout

        elif e.status == 404:
            logger.warning(f"[{self.repo_slug}] Repository not found or no access")
            return False

        else:
            logger.error(f"[{self.repo_slug}] GitHub error {e.status}: {e}")
            return False

    def _process_commit_files(
        self,
        repo: Any,
        commit_wrapper: Any,
        parent_sha: str,
        github_client: Github
    ):
        """Process files in a commit and queue them for analysis."""
        sha = commit_wrapper.sha
        files_modified = commit_wrapper.files
        processed_bases: Set[str] = set()
        repo_files_cache: Optional[List[str]] = None

        for f in files_modified:
            if self.stop_event.is_set():
                break

            path = f.filename

            # Skip removed files, test files, non-C++ files
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

            # Get repo file list if needed
            if repo_files_cache is None:
                repo_files_cache = get_all_repo_files(repo, sha)

            # Find header/implementation pairs
            header_path = None
            impl_path = None

            if path.endswith((".h", ".hpp")):
                header_path = path
                impl_path = find_corresponding_file(path, [".cpp", ".cxx", ".cc"], repo_files_cache)
            else:
                impl_path = path
                header_path = find_corresponding_file(path, [".h", ".hpp"], repo_files_cache)

            # Create temp directory for this file pair
            temp_dir = os.path.join(
                self.temp_storage_path,
                f"{self.repo_slug.replace('/', '_')}_{sha[:8]}_{base_name}"
            )
            os.makedirs(temp_dir, exist_ok=True)

            # Download files to tmpfs
            try:
                # Before (parent) versions
                if header_path:
                    h_before = get_github_content(repo, parent_sha, header_path)
                    if h_before:
                        save_file_to_tmpfs(h_before, temp_dir, f"before_{os.path.basename(header_path)}")

                if impl_path:
                    cpp_before = get_github_content(repo, parent_sha, impl_path)
                    if cpp_before:
                        save_file_to_tmpfs(cpp_before, temp_dir, f"before_{os.path.basename(impl_path)}")

                # After (current) versions
                if header_path:
                    h_after = get_github_content(repo, sha, header_path)
                    if h_after:
                        save_file_to_tmpfs(h_after, temp_dir, f"after_{os.path.basename(header_path)}")

                if impl_path:
                    cpp_after = get_github_content(repo, sha, impl_path)
                    if cpp_after:
                        save_file_to_tmpfs(cpp_after, temp_dir, f"after_{os.path.basename(impl_path)}")

                # Create and queue analysis task
                task = AnalysisTask(
                    repo_slug=self.repo_slug,
                    repo_url=self.repo_url,
                    commit_sha=sha,
                    parent_sha=parent_sha,
                    file_path=path,
                    base_name=base_name,
                    header_path=header_path,
                    impl_path=impl_path,
                    temp_dir=temp_dir,
                    commit_message=commit_wrapper.commit.message[:200],
                    commit_date=commit_wrapper.commit.author.date.isoformat(),
                    fix_regexes=self.fix_regexes
                )

                self.analysis_queue.put(task)

                # Update queue size stat
                self.stats_dict["queue_size"] = self.analysis_queue.qsize()

            except Exception as e:
                logger.error(f"[{self.repo_slug}] Error downloading files for {sha[:7]}: {e}")
                shutil.rmtree(temp_dir, ignore_errors=True)


# ============== Analyzer Process (Consumer) ==============

class AnalyzerProcess(mp.Process):
    """
    Consumer process that analyzes downloaded code.

    Each analyzer:
    - Pulls tasks from the shared queue (FIFO)
    - Runs Cppcheck analysis
    - Labels and saves results to DB
    - Cleans up temp files
    """

    def __init__(
        self,
        process_id: int,
        analysis_queue: Queue,
        status_dict: DictProxy,
        stats_dict: DictProxy,
        config: Dict[str, Any],
        stop_event: "mp.synchronize.Event",
    ):
        super().__init__(name=f"Analyzer-{process_id}")
        self.process_id = process_id
        self.analysis_queue = analysis_queue
        self.status_dict = status_dict
        self.stats_dict = stats_dict
        self.config = config
        self.stop_event = stop_event

        self.labeler = None

    def _update_status(self, status: str, repo: str = "", commit: str = "", action: str = ""):
        """Update status in shared dict for TUI display."""
        key = f"C{self.process_id}"
        self.status_dict[key] = {
            "type": "consumer",
            "status": status,
            "repo": repo,
            "commit": commit,
            "action": action,
            "timestamp": time.time()
        }

    def run(self):
        """Main consumer loop."""
        signal.signal(signal.SIGTERM, lambda s, f: None)

        logger.info(f"Analyzer {self.process_id} starting")
        self._update_status("starting")

        # Initialize labeler
        try:
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "labels_config.json"
            )
            self.labeler = Labeler(timeout=30, config_path=config_path)
        except Exception as e:
            logger.error(f"Analyzer {self.process_id} failed to init labeler: {e}")
            self._update_status("error", action=f"Labeler init failed: {e}")
            return

        while not self.stop_event.is_set():
            try:
                # Get task from queue with timeout
                try:
                    task: AnalysisTask = self.analysis_queue.get(timeout=1.0)
                except Exception:  # Queue.Empty
                    self._update_status("idle", action="Waiting for tasks")
                    continue

                self._update_status(
                    "working",
                    repo=task.repo_slug,
                    commit=task.commit_sha[:7],
                    action="Analyzing"
                )

                # Process the task
                try:
                    self._analyze_task(task)
                except Exception as e:
                    logger.error(f"Error analyzing {task.commit_sha[:7]}: {e}")
                finally:
                    # Always cleanup temp files
                    shutil.rmtree(task.temp_dir, ignore_errors=True)

                # Update queue size
                self.stats_dict["queue_size"] = self.analysis_queue.qsize()

            except Exception as e:
                logger.error(f"Analyzer {self.process_id} error: {e}")
                self._update_status("error", action=str(e))

        self._update_status("done")
        logger.info(f"Analyzer {self.process_id} finished")

    def _analyze_task(self, task: AnalysisTask):
        """Analyze a single task: run cppcheck, label, save to DB."""
        temp_dir = task.temp_dir

        # Read files from temp directory
        h_before = ""
        h_after = ""
        cpp_before = ""
        cpp_after = ""

        for filename in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if filename.startswith("before_"):
                if filename.endswith((".h", ".hpp")):
                    h_before = content
                else:
                    cpp_before = content
            elif filename.startswith("after_"):
                if filename.endswith((".h", ".hpp")):
                    h_after = content
                else:
                    cpp_after = content

        # Format full context
        full_code_before = format_context(h_before, cpp_before)
        full_code_fixed = format_context(h_after, cpp_after)

        if not full_code_before or not full_code_fixed:
            logger.debug(f"Skipping {task.commit_sha[:7]} - no code content")
            return

        if full_code_before == full_code_fixed:
            logger.debug(f"Skipping {task.commit_sha[:7]} - no changes")
            return

        # Run labeling
        self._update_status(
            "working",
            repo=task.repo_slug,
            commit=task.commit_sha[:7],
            action="Running Cppcheck"
        )

        try:
            labels = self.labeler.analyze(full_code_before, full_code_fixed)

            # Skip if no issues found
            if not labels.get("cppcheck"):
                logger.debug(f"Skipping {task.commit_sha[:7]} - no cppcheck issues")
                return

            labels.setdefault("clang", {})

        except Exception as e:
            logger.warning(f"Labeling failed for {task.commit_sha[:7]}: {e}")
            return

        # Build payload
        payload = {
            "code_original": full_code_before,
            "code_fixed": full_code_fixed,
            "code_hash": calculate_hash(full_code_before),
            "repo": {
                "url": task.repo_url,
                "commit_hash": task.commit_sha,
                "commit_date": task.commit_date
            },
            "ingest_timestamp": datetime.now().isoformat(),
            "labels": labels,
        }

        # Save to file and DB
        self._update_status(
            "working",
            repo=task.repo_slug,
            commit=task.commit_sha[:7],
            action="Saving to DB"
        )

        save_payload_to_file(payload)

        inserted_id = insert_payload_to_db(payload)
        if inserted_id:
            logger.info(f"Inserted entry: id={inserted_id}")

            # Update success count
            current = self.stats_dict.get("successful_findings", 0)
            self.stats_dict["successful_findings"] = current + 1


# ============== Legacy Repository Processing ==============

def _process_repository_legacy(github_client: Any, repo_config: Any, progress_callback=None) -> None:
    """Legacy single-threaded repository processing."""
    logger.info(f"Processing repository: {repo_config.url}")

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
    target_count = repo_config.target_record_count

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

                if progress_callback:
                    progress_callback(processed_count, target_count, sha[:7])

    except GithubException as e:
        logging.error(f"GitHub API Error for {repo_config.url}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error for {repo_config.url}: {e}")
