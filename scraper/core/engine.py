"""
Refactored Engine with Producer-Consumer Architecture.

This module implements a high-performance sharded scraper with:
- Downloader processes (Producers): One per GitHub token, each handles a shard of repositories
- Analyzer processes (Consumers): Worker pool that processes files from the queue
- Shared in-memory state for fast commit deduplication
- TUI-compatible status updates via shared dictionary
"""

import hashlib
import json
import logging
import multiprocessing as mp
import os
import re
import shutil
import signal
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


def shard_repositories(repositories: List[str], num_shards: int) -> List[List[str]]:
    """
    Split repository list into N even chunks for sharding.

    Args:
        repositories: List of repository URLs
        num_shards: Number of shards (equal to number of tokens)

    Returns:
        List of repository lists, one per shard
    """
    if num_shards <= 0:
        return [repositories]

    shards = [[] for _ in range(num_shards)]
    for i, repo in enumerate(repositories):
        shards[i % num_shards].append(repo)

    return shards


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


# ============== Downloader Process (Producer) ==============

class DownloaderProcess(mp.Process):
    """
    Producer process that downloads commits from assigned repositories.

    Each downloader:
    - Has exactly one GitHub token assigned
    - Handles a shard of repositories (round-robin)
    - Downloads files to tmpfs
    - Pushes analysis tasks to the shared queue
    """

    def __init__(
        self,
        process_id: int,
        token: str,
        repositories: List[str],
        analysis_queue: Queue,
        state_dict: DictProxy,
        status_dict: DictProxy,
        stats_dict: DictProxy,
        config: Dict[str, Any],
        stop_event: "mp.synchronize.Event",
    ):
        super().__init__(name=f"Downloader-{process_id}")
        self.process_id = process_id
        self.token = token
        self.repositories = repositories
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

    def _update_status(self, status: str, repo: str = "", commit: str = "", action: str = ""):
        """Update status in shared dict for TUI display."""
        key = f"P{self.process_id}"
        self.status_dict[key] = {
            "type": "producer",
            "status": status,
            "repo": repo,
            "commit": commit,
            "action": action,
            "token_suffix": self.token[-6:] if self.token else "N/A",
            "timestamp": time.time()
        }

    def _is_commit_processed(self, repo_slug: str, commit_sha: str) -> bool:
        """Check if commit was already processed (from shared memory)."""
        key = f"processed:{repo_slug}:{commit_sha}"
        return key in self.state_dict

    def _mark_commit_processed(self, repo_slug: str, commit_sha: str):
        """Mark commit as processed in shared memory."""
        key = f"processed:{repo_slug}:{commit_sha}"
        self.state_dict[key] = True

    def run(self):
        """Main producer loop."""
        # Set up signal handling
        signal.signal(signal.SIGTERM, lambda s, f: None)

        logger.info(f"Downloader {self.process_id} starting with {len(self.repositories)} repos")
        self._update_status("starting")

        # Initialize GitHub client
        try:
            auth = Auth.Token(self.token)
            github_client = Github(auth=auth)
            user = github_client.get_user().login
            logger.info(f"Downloader {self.process_id} authenticated as: {user}")
        except Exception as e:
            logger.error(f"Downloader {self.process_id} auth failed: {e}")
            self._update_status("error", action=f"Auth failed: {e}")
            return

        # Round-robin through repositories
        repo_index = 0
        while not self.stop_event.is_set():
            if not self.repositories:
                logger.warning(f"Downloader {self.process_id}: No repositories assigned")
                break

            # Get current repo (round-robin)
            repo_url = self.repositories[repo_index % len(self.repositories)]
            repo_index += 1

            try:
                self._process_repository(github_client, repo_url)
            except Exception as e:
                logger.error(f"Error processing {repo_url}: {e}")
                self._update_status("error", repo=repo_url, action=str(e))

        self._update_status("done")
        logger.info(f"Downloader {self.process_id} finished")

    def _process_repository(self, github_client: Github, repo_url: str):
        """Process a single repository - fetch and queue commits."""
        repo_slug = get_repo_slug(repo_url)
        self._update_status("working", repo=repo_slug, action="Fetching commits")

        try:
            repo = github_client.get_repo(repo_slug)
        except Exception as e:
            logger.error(f"Could not access {repo_url}: {e}")
            return

        # Get commits
        commits = repo.get_commits()

        processed_in_batch = 0
        commit_index = 0

        for commit_wrapper in commits:
            if self.stop_event.is_set():
                break

            if processed_in_batch >= self.batch_size:
                break

            sha = commit_wrapper.sha
            commit_index += 1

            # Skip if already processed
            if self._is_commit_processed(repo_slug, sha):
                continue

            msg = commit_wrapper.commit.message

            # Check if commit message matches fix patterns
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

            self._update_status(
                "working",
                repo=repo_slug,
                commit=sha[:7],
                action=f"Downloading {processed_in_batch + 1}/{self.batch_size}"
            )

            # Process files in this commit
            try:
                self._process_commit_files(
                    repo, repo_url, repo_slug, commit_wrapper, parent_sha
                )
                processed_in_batch += 1
                self._mark_commit_processed(repo_slug, sha)

                # Update stats
                current = self.stats_dict.get("total_processed", 0)
                self.stats_dict["total_processed"] = current + 1

            except GithubException as e:
                if e.status == 403:
                    logger.warning(f"Rate limited on {repo_slug}")
                    time.sleep(60)  # Wait for rate limit
                else:
                    raise

    def _process_commit_files(
        self,
        repo: Any,
        repo_url: str,
        repo_slug: str,
        commit_wrapper: Any,
        parent_sha: str
    ):
        """Process files in a commit and queue them for analysis."""
        sha = commit_wrapper.sha
        files_modified = commit_wrapper.files
        processed_bases: Set[str] = set()
        repo_files_cache: Optional[List[str]] = None

        for f in files_modified:
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
                f"{repo_slug.replace('/', '_')}_{sha[:8]}_{base_name}"
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
                    repo_slug=repo_slug,
                    repo_url=repo_url,
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
                logger.error(f"Error downloading files for {sha[:7]}: {e}")
                # Cleanup on error
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
