"""
Core scraper engine with Repository-Based Parallelism.

Architecture:
- 1 DownloaderThread per Repository (threading.Thread for I/O-bound)
- Tokens shared via round-robin with TokenManager
- AnalyzerProcess workers for CPU-bound cppcheck analysis
- NO StateManager - each downloader processes its repo fresh
"""

import hashlib
import json
import logging
import multiprocessing as mp
import os
import re
import shutil
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from multiprocessing import Queue
from multiprocessing.managers import DictProxy
from typing import Any, Dict, List, Optional, Set

import requests
from github import Auth, Github, GithubException

from scraper.labeling.labeler import Labeler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
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
    """Combine header and implementation into a single context."""
    output = []
    if header.strip():
        output.append(header.strip())
    if implementation.strip():
        output.append(implementation.strip())
    return "\n".join(output)


def save_file_to_tmpfs(content: str, temp_dir: str, filename: str) -> str:
    """Save content to a temp file."""
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
            logger.info("Entry already exists (duplicate). Skipping.")
            return None
        logger.warning(f"DB insert failed: HTTP {resp.status_code}")
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
    except Exception as e:
        logger.error(f"Failed to save payload locally: {e}")


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


# ============== Token Manager ==============

class TokenManager:
    """Thread-safe manager for GitHub API tokens with round-robin distribution."""

    def __init__(self, tokens: List[str]):
        if not tokens:
            raise ValueError("At least one GitHub token is required")
        self.tokens = tokens
        self.token_count = len(tokens)
        self._token_locks: Dict[str, threading.Lock] = {t: threading.Lock() for t in tokens}
        self._rate_limit_reset: Dict[str, float] = {t: 0.0 for t in tokens}
        self._token_labels = {t: chr(65 + i) for i, t in enumerate(tokens)}

    def get_token_for_index(self, index: int) -> str:
        """Get token for a downloader index (round-robin)."""
        return self.tokens[index % self.token_count]

    def get_token_label(self, token: str) -> str:
        """Get human-readable label (A, B, C, ...)."""
        return self._token_labels.get(token, "?")

    def acquire_token(self, token: str, timeout: float = 300) -> bool:
        """Wait for token to be available (not rate limited)."""
        start_time = time.time()
        while True:
            reset_time = self._rate_limit_reset.get(token, 0)
            now = time.time()
            if reset_time <= now:
                return True
            wait_time = min(reset_time - now, timeout - (now - start_time))
            if wait_time <= 0:
                return False
            time.sleep(min(wait_time, 5.0))

    def handle_rate_limit_error(self, token: str, reset_timestamp: float):
        """Mark token as rate limited."""
        self._rate_limit_reset[token] = reset_timestamp
        label = self.get_token_label(token)
        logger.warning(f"Token {label} rate limited until {datetime.fromtimestamp(reset_timestamp)}")


# ============== Downloader Thread (1 per Repository) ==============

class DownloaderThread(threading.Thread):
    """
    Downloads commits from exactly ONE repository.
    Uses the SAME proven logic as engine_old.py.
    """

    def __init__(
        self,
        thread_id: int,
        repo_url: str,
        token: str,
        token_manager: TokenManager,
        analysis_queue: Queue,
        status_dict: DictProxy,
        stats_dict: DictProxy,
        config: Dict[str, Any],
        stop_event: threading.Event,
    ):
        self.repo_slug = get_repo_slug(repo_url)
        super().__init__(name=f"DL-{self.repo_slug}", daemon=True)

        self.thread_id = thread_id
        self.repo_url = repo_url
        self.token = token
        self.token_manager = token_manager
        self.analysis_queue = analysis_queue
        self.status_dict = status_dict
        self.stats_dict = stats_dict
        self.config = config
        self.stop_event = stop_event

        # Config
        self.target_record_count = config.get("target_record_count", 10)
        self.temp_storage_path = config.get("temp_storage_path", "/tmp/fixmycodedb_scraper")
        self.fix_regexes = config.get("fix_regexes", [])

        self.processed_count = 0

    def _update_status(self, status: str, commit: str = "", action: str = ""):
        """Update status for TUI."""
        key = f"D{self.thread_id}"
        self.status_dict[key] = {
            "type": "downloader",
            "status": status,
            "repo": self.repo_slug,
            "commit": commit,
            "action": action,
            "token_label": self.token_manager.get_token_label(self.token),
            "timestamp": time.time()
        }

    def run(self):
        """Main thread loop - uses OLD PROVEN LOGIC."""
        logger.info(f"[{self.repo_slug}] Starting downloader")
        self._update_status("starting", action="Connecting...")

        # Initialize GitHub client
        try:
            auth = Auth.Token(self.token)
            github_client = Github(auth=auth)
            repo = github_client.get_repo(self.repo_slug)
        except Exception as e:
            logger.error(f"[{self.repo_slug}] Failed to connect: {e}")
            self._update_status("error", action=str(e)[:40])
            return

        self._update_status("working", action="Fetching commits...")

        try:
            # Get commits (same as old logic)
            commits = repo.get_commits()

            for commit_wrapper in commits:
                if self.stop_event.is_set():
                    break
                if self.processed_count >= self.target_record_count:
                    logger.info(f"[{self.repo_slug}] Target count reached: {self.processed_count}")
                    break

                sha = commit_wrapper.sha
                msg = commit_wrapper.commit.message

                # Fix pattern matching - EXACT same as old logic
                if self.fix_regexes:
                    matched = False
                    for pattern in self.fix_regexes:
                        if re.search(pattern, msg, re.IGNORECASE | re.MULTILINE):
                            matched = True
                            break
                    if not matched:
                        continue

                # Need parent for diff
                if not commit_wrapper.parents:
                    continue
                parent_sha = commit_wrapper.parents[0].sha

                self._update_status("working", commit=sha[:7], action=f"Processing ({self.processed_count + 1}/{self.target_record_count})")

                # Process files - EXACT same as old logic
                files_modified = commit_wrapper.files
                processed_bases: Set[str] = set()
                repo_files_cache: Optional[List[str]] = None

                for f in files_modified:
                    if self.stop_event.is_set():
                        break

                    path = f.filename

                    # Skip criteria - EXACT same as old logic
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

                    # Find header/impl pairs - EXACT same as old logic
                    header_path = None
                    impl_path = None

                    if path.endswith((".h", ".hpp")):
                        header_path = path
                        impl_path = find_corresponding_file(path, [".cpp", ".cxx", ".cc"], repo_files_cache)
                    else:
                        impl_path = path
                        header_path = find_corresponding_file(path, [".h", ".hpp"], repo_files_cache)

                    # Download content - EXACT same as old logic
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

                    # Create temp dir and save files
                    temp_dir = os.path.join(
                        self.temp_storage_path,
                        f"{self.repo_slug.replace('/', '_')}_{sha[:8]}_{base_name}"
                    )
                    os.makedirs(temp_dir, exist_ok=True)

                    if h_before:
                        save_file_to_tmpfs(h_before, temp_dir, f"before_{os.path.basename(header_path)}")
                    if cpp_before:
                        save_file_to_tmpfs(cpp_before, temp_dir, f"before_{os.path.basename(impl_path)}")
                    if h_after:
                        save_file_to_tmpfs(h_after, temp_dir, f"after_{os.path.basename(header_path)}")
                    if cpp_after:
                        save_file_to_tmpfs(cpp_after, temp_dir, f"after_{os.path.basename(impl_path)}")

                    # Queue for analysis
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
                        commit_message=msg[:200],
                        commit_date=commit_wrapper.commit.author.date.isoformat(),
                        fix_regexes=self.fix_regexes
                    )
                    self.analysis_queue.put(task)
                    self.processed_count += 1

                    # Update stats
                    current = self.stats_dict.get("total_processed", 0)
                    self.stats_dict["total_processed"] = current + 1
                    self.stats_dict["queue_size"] = self.analysis_queue.qsize()

        except GithubException as e:
            if e.status == 403:
                reset_time = time.time() + 60
                self.token_manager.handle_rate_limit_error(self.token, reset_time)
                self._update_status("rate_limited", action="Waiting...")
            else:
                logger.error(f"[{self.repo_slug}] GitHub error: {e}")
                self._update_status("error", action=str(e)[:40])
        except Exception as e:
            logger.error(f"[{self.repo_slug}] Error: {e}")
            self._update_status("error", action=str(e)[:40])

        self._update_status("done", action=f"Done: {self.processed_count} commits")
        logger.info(f"[{self.repo_slug}] Finished: {self.processed_count} commits processed")


# ============== Analyzer Process (Consumer) ==============

class AnalyzerProcess(mp.Process):
    """
    Analyzes downloaded code using cppcheck.
    Uses the SAME proven logic as engine_old.py.
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
        """Update status for TUI."""
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
        """Main analyzer loop."""
        signal.signal(signal.SIGTERM, lambda s, f: None)
        logger.info(f"Analyzer {self.process_id} starting")
        self._update_status("starting")

        # Initialize labeler
        try:
            config_path = os.path.join(os.path.dirname(__file__), "..", "labels_config.json")
            self.labeler = Labeler(timeout=30, config_path=config_path)
        except Exception as e:
            logger.error(f"Analyzer {self.process_id} failed to init labeler: {e}")
            self._update_status("error", action=f"Labeler init failed")
            return

        while not self.stop_event.is_set():
            try:
                try:
                    task: AnalysisTask = self.analysis_queue.get(timeout=1.0)
                except:
                    self._update_status("idle", action="Waiting for tasks")
                    continue

                self._update_status("working", repo=task.repo_slug, commit=task.commit_sha[:7], action="Analyzing")

                try:
                    self._analyze_task(task)
                except Exception as e:
                    logger.error(f"Error analyzing {task.commit_sha[:7]}: {e}")
                finally:
                    shutil.rmtree(task.temp_dir, ignore_errors=True)

                self.stats_dict["queue_size"] = self.analysis_queue.qsize()

            except Exception as e:
                logger.error(f"Analyzer {self.process_id} error: {e}")

        self._update_status("done")
        logger.info(f"Analyzer {self.process_id} finished")

    def _analyze_task(self, task: AnalysisTask):
        """Analyze a task - EXACT same logic as engine_old.py."""
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

        full_code_before = format_context(h_before, cpp_before)
        full_code_fixed = format_context(h_after, cpp_after)

        if not full_code_before or not full_code_fixed:
            return

        if full_code_before == full_code_fixed:
            return

        # Run labeling - EXACT same as old logic
        self._update_status("working", repo=task.repo_slug, commit=task.commit_sha[:7], action="Running Cppcheck")

        try:
            labels = self.labeler.analyze(full_code_before, full_code_fixed)

            if not labels.get("cppcheck"):
                logger.info(f"Skipping {task.commit_sha[:7]} - no cppcheck issues found")
                return

            labels.setdefault("clang", {})

        except Exception as e:
            logger.warning(f"Labeling failed for {task.commit_sha[:7]}: {e}")
            return

        # Build payload - EXACT same as old logic
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

        self._update_status("working", repo=task.repo_slug, commit=task.commit_sha[:7], action="Saving to DB")

        save_payload_to_file(payload)

        inserted_id = insert_payload_to_db(payload)
        if inserted_id:
            logger.info(f"Inserted entry: id={inserted_id}")
            current = self.stats_dict.get("successful_findings", 0)
            self.stats_dict["successful_findings"] = current + 1


# ============== Legacy run_scraper (for backward compatibility) ==============

def run_scraper(config_path: str, progress_callback=None) -> None:
    """Legacy sequential scraper - kept for backward compatibility."""
    from scraper.config.config_utils import load_config

    config = load_config(config_path)
    if not config.repositories:
        logger.warning("No repositories found.")
        return

    token = config.github_token or os.getenv("GITHUB_TOKEN")
    if not token:
        logger.warning("No GitHub token.")
        g = Github()
    else:
        auth = Auth.Token(token.strip())
        g = Github(auth=auth)

    # Use the old process_repository function for legacy mode
    for repo_config in config.repositories:
        logger.info(f"Processing: {repo_config.url}")
