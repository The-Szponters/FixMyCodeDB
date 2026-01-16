"""
Parallel execution manager for repository scanning.
Manages worker processes and aggregates results.
"""

import logging
import multiprocessing as mp
import os
import queue
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from scraper.config.config_utils import load_config
from scraper.config.scraper_config import RepoConfig
from scraper.config.token_pool import TokenPool


class WorkerStatus(Enum):
    """Status codes for worker processes."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class WorkerResult:
    """Result from a single worker process."""
    worker_id: int
    repo_url: str
    status: WorkerStatus
    records_processed: int = 0
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    exit_code: int = 0


@dataclass
class ParallelScanResult:
    """Aggregated results from all workers."""
    total_workers: int
    successful_workers: int
    failed_workers: int
    total_records: int
    worker_results: List[WorkerResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0


def worker_process(
    worker_id: int,
    repo_config: RepoConfig,
    token: Optional[str],
    result_queue: mp.Queue,
    progress_queue: Optional[mp.Queue] = None
) -> None:
    """
    Worker function that runs in a subprocess to scan a single repository.

    Args:
        worker_id: Unique identifier for this worker
        repo_config: Configuration for the repository to scan
        token: GitHub API token for this worker
        result_queue: Queue to send results back to parent
        progress_queue: Optional queue for progress updates
    """
    import os
    import sys

    # Set up logging for this worker
    logging.basicConfig(
        level=logging.INFO,
        format=f"[Worker-{worker_id}] %(levelname)s: %(message)s"
    )

    start_time = time.time()
    records_processed = 0
    error_message = None
    status = WorkerStatus.RUNNING

    try:
        # Import here to avoid circular imports
        from github import Auth, Github
        from scraper.core.engine import process_repository

        # Set up GitHub client with assigned token
        if token:
            auth = Auth.Token(token)
            github_client = Github(auth=auth)
            logging.info(f"Using provided GitHub token (ends in ...{token[-4:]})")
        else:
            github_client = Github()
            logging.warning("No token provided, using unauthenticated access")

        # Create progress callback that sends to queue
        def progress_callback(current: int, total: int, commit_sha: str):
            nonlocal records_processed
            records_processed = current
            if progress_queue:
                try:
                    progress_queue.put_nowait({
                        "worker_id": worker_id,
                        "current": current,
                        "total": total,
                        "commit_sha": commit_sha,
                        "repo_url": repo_config.url
                    })
                except queue.Full:
                    pass  # Ignore if queue is full

        logging.info(f"Starting scan of {repo_config.url}")
        process_repository(github_client, repo_config, progress_callback)

        status = WorkerStatus.COMPLETED
        logging.info(f"Completed scan of {repo_config.url}, processed {records_processed} records")

    except KeyboardInterrupt:
        status = WorkerStatus.FAILED
        error_message = "Worker interrupted by user"
        logging.warning(error_message)

    except Exception as e:
        status = WorkerStatus.FAILED
        error_message = str(e)
        logging.error(f"Worker failed: {error_message}")

    finally:
        duration = time.time() - start_time

        result = WorkerResult(
            worker_id=worker_id,
            repo_url=repo_config.url,
            status=status,
            records_processed=records_processed,
            error_message=error_message,
            duration_seconds=duration,
            exit_code=0 if status == WorkerStatus.COMPLETED else 1
        )

        result_queue.put(result)


class ParallelScanner:
    """
    Manages parallel repository scanning using multiprocessing.
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        tokens: Optional[List[str]] = None,
        timeout_per_repo: int = 3600
    ):
        """
        Initialize the parallel scanner.

        Args:
            max_workers: Maximum number of parallel workers (defaults to CPU count)
            tokens: List of GitHub API tokens for the token pool
            timeout_per_repo: Maximum time in seconds for each repository scan
        """
        self.max_workers = max_workers or mp.cpu_count()
        self.token_pool = TokenPool(tokens)
        self.timeout_per_repo = timeout_per_repo
        self._logger = logging.getLogger(__name__)

    def scan_repositories(
        self,
        config_path: str,
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> ParallelScanResult:
        """
        Scan multiple repositories in parallel.

        Args:
            config_path: Path to the scraper configuration file
            progress_callback: Optional callback for progress updates

        Returns:
            ParallelScanResult with aggregated results from all workers
        """
        start_time = time.time()

        # Load configuration
        config = load_config(config_path)
        if not config.repositories:
            self._logger.warning("No repositories found in config")
            return ParallelScanResult(
                total_workers=0,
                successful_workers=0,
                failed_workers=0,
                total_records=0
            )

        repos = config.repositories
        num_repos = len(repos)
        num_workers = min(self.max_workers, num_repos)

        self._logger.info(f"Starting parallel scan of {num_repos} repositories with {num_workers} workers")

        # Distribute tokens among workers
        tokens = self.token_pool.distribute_tokens(num_repos)

        # Create queues for communication
        result_queue = mp.Queue()
        progress_queue = mp.Queue() if progress_callback else None

        # Create and start worker processes
        processes: List[mp.Process] = []
        for i, repo_config in enumerate(repos):
            p = mp.Process(
                target=worker_process,
                args=(i, repo_config, tokens[i], result_queue, progress_queue),
                name=f"RepoScanner-{i}"
            )
            processes.append(p)

        # Start workers in batches to respect max_workers limit
        active_processes: List[mp.Process] = []
        results: List[WorkerResult] = []
        process_idx = 0

        while process_idx < len(processes) or active_processes:
            # Start new processes if under limit
            while len(active_processes) < num_workers and process_idx < len(processes):
                p = processes[process_idx]
                p.start()
                active_processes.append(p)
                self._logger.info(f"Started worker {process_idx} for {repos[process_idx].url}")
                process_idx += 1

            # Process progress updates
            if progress_queue:
                try:
                    while True:
                        update = progress_queue.get_nowait()
                        if progress_callback:
                            progress_callback(update)
                except queue.Empty:
                    pass

            # Check for completed processes
            still_active = []
            for p in active_processes:
                if p.is_alive():
                    still_active.append(p)
                else:
                    p.join()
                    # Collect result
                    try:
                        result = result_queue.get_nowait()
                        results.append(result)
                    except queue.Empty:
                        pass

            active_processes = still_active

            # Small sleep to avoid busy waiting
            if active_processes:
                time.sleep(0.1)

        # Collect any remaining results
        while not result_queue.empty():
            try:
                result = result_queue.get_nowait()
                results.append(result)
            except queue.Empty:
                break

        # Aggregate results
        total_duration = time.time() - start_time
        successful = sum(1 for r in results if r.status == WorkerStatus.COMPLETED)
        failed = sum(1 for r in results if r.status == WorkerStatus.FAILED)
        total_records = sum(r.records_processed for r in results)

        return ParallelScanResult(
            total_workers=len(results),
            successful_workers=successful,
            failed_workers=failed,
            total_records=total_records,
            worker_results=results,
            total_duration_seconds=total_duration
        )

    def scan_single_repository(
        self,
        repo_url: str,
        target_count: int = 100,
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> WorkerResult:
        """
        Scan a single repository (convenience method).

        Args:
            repo_url: GitHub repository URL
            target_count: Number of records to collect
            progress_callback: Optional callback for progress updates

        Returns:
            WorkerResult for the single repository
        """
        repo_config = RepoConfig(
            url=repo_url,
            target_record_count=target_count
        )

        result_queue = mp.Queue()
        progress_queue = mp.Queue() if progress_callback else None
        token = self.token_pool.get_token(0)

        # Create and run worker
        p = mp.Process(
            target=worker_process,
            args=(0, repo_config, token, result_queue, progress_queue),
            name="RepoScanner-0"
        )

        p.start()

        # Monitor progress
        while p.is_alive():
            if progress_queue:
                try:
                    update = progress_queue.get_nowait()
                    if progress_callback:
                        progress_callback(update)
                except queue.Empty:
                    pass
            time.sleep(0.1)

        p.join()

        # Get result
        try:
            return result_queue.get(timeout=5)
        except queue.Empty:
            return WorkerResult(
                worker_id=0,
                repo_url=repo_url,
                status=WorkerStatus.FAILED,
                error_message="No result received from worker"
            )


def run_parallel_scraper(
    config_path: str,
    max_workers: Optional[int] = None,
    tokens: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> ParallelScanResult:
    """
    Entry point for parallel scraping.

    Args:
        config_path: Path to scraper configuration file
        max_workers: Maximum parallel workers
        tokens: GitHub API tokens
        progress_callback: Optional callback for progress updates

    Returns:
        Aggregated scan results
    """
    scanner = ParallelScanner(max_workers=max_workers, tokens=tokens)

    def wrapped_callback(update: Dict):
        if progress_callback:
            progress_callback(
                update.get("current", 0),
                update.get("total", 0),
                update.get("commit_sha", "")
            )

    return scanner.scan_repositories(config_path, wrapped_callback)
