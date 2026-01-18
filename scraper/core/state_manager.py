"""
StateManager: High-performance in-memory state with periodic disk persistence.

Manages the `last_scraped_commit` mapping using a shared multiprocessing dict
to avoid slow file I/O on every commit check.
"""

import atexit
import json
import logging
import multiprocessing as mp
import os
import threading
import time
from contextlib import contextmanager
from multiprocessing import Manager
from multiprocessing.managers import DictProxy
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from multiprocessing.managers import SyncManager

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages scraper state in shared memory with periodic persistence.

    Features:
    - Loads state from disk into multiprocessing.Manager().dict() at startup
    - Provides fast in-memory lookups for commit processing checks
    - Flushes state to disk periodically (configurable interval)
    - Ensures state is saved on exit (atexit hook)
    """

    def __init__(
        self,
        state_file_path: str,
        flush_interval: int = 60,
        flush_threshold: int = 100,
        manager: Optional["mp.managers.SyncManager"] = None
    ):
        """
        Initialize the StateManager.

        Args:
            state_file_path: Path to the JSON file for persistent storage
            flush_interval: Seconds between automatic flushes (default: 60)
            flush_threshold: Number of updates before triggering a flush (default: 100)
            manager: Optional multiprocessing.Manager instance (creates one if not provided)
        """
        self.state_file_path = Path(state_file_path)
        self.flush_interval = flush_interval
        self.flush_threshold = flush_threshold

        # Create manager if not provided
        self._owns_manager = manager is None
        self._manager = manager or Manager()

        # Shared state dictionary
        self._state: DictProxy = self._manager.dict()

        # Counters for flush logic
        self._update_count = self._manager.Value('i', 0)
        self._lock = self._manager.Lock()

        # Background flush thread
        self._stop_flush_thread = threading.Event()
        self._flush_thread: Optional[threading.Thread] = None

        # Load initial state
        self._load_state()

        # Register cleanup
        atexit.register(self._cleanup)

    def _load_state(self) -> None:
        """Load state from disk into the shared dictionary."""
        if self.state_file_path.exists():
            try:
                with open(self.state_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Load into shared dict
                if isinstance(data, dict):
                    for key, value in data.items():
                        self._state[key] = value
                    logger.info(f"Loaded {len(data)} entries from {self.state_file_path}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in state file: {e}. Starting fresh.")
            except Exception as e:
                logger.error(f"Error loading state file: {e}")
        else:
            logger.info(f"State file not found at {self.state_file_path}. Starting fresh.")
            # Ensure parent directory exists
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)

    def flush_to_disk(self) -> None:
        """Persist current state to disk."""
        with self._lock:
            try:
                # Convert proxy dict to regular dict for serialization
                data = dict(self._state)

                # Atomic write: write to temp file, then rename
                temp_path = self.state_file_path.with_suffix('.tmp')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)

                # Atomic rename
                temp_path.replace(self.state_file_path)

                self._update_count.value = 0
                logger.debug(f"Flushed {len(data)} entries to {self.state_file_path}")
            except Exception as e:
                logger.error(f"Error flushing state to disk: {e}")

    def start_background_flush(self) -> None:
        """Start the background thread that periodically flushes state."""
        if self._flush_thread is not None and self._flush_thread.is_alive():
            return

        self._stop_flush_thread.clear()
        self._flush_thread = threading.Thread(
            target=self._background_flush_loop,
            daemon=True,
            name="StateManager-Flush"
        )
        self._flush_thread.start()
        logger.info(f"Started background flush thread (interval: {self.flush_interval}s)")

    def stop_background_flush(self) -> None:
        """Stop the background flush thread."""
        self._stop_flush_thread.set()
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=5)
            self._flush_thread = None
        logger.info("Stopped background flush thread")

    def _background_flush_loop(self) -> None:
        """Background loop that flushes state periodically."""
        while not self._stop_flush_thread.is_set():
            time.sleep(self.flush_interval)
            if not self._stop_flush_thread.is_set():
                self.flush_to_disk()

    def _cleanup(self) -> None:
        """Cleanup on exit: stop thread, flush state, shutdown manager."""
        logger.info("StateManager cleanup: flushing final state...")
        self.stop_background_flush()
        self.flush_to_disk()
        if self._owns_manager:
            try:
                self._manager.shutdown()
            except Exception:
                pass

    # ========== Public API for state access ==========

    def get_last_commit(self, repo_slug: str) -> Optional[str]:
        """
        Get the last scraped commit SHA for a repository.

        Args:
            repo_slug: Repository identifier (e.g., "owner/repo")

        Returns:
            Commit SHA if found, None otherwise
        """
        return self._state.get(f"last_commit:{repo_slug}")

    def set_last_commit(self, repo_slug: str, commit_sha: str) -> None:
        """
        Update the last scraped commit for a repository.

        Args:
            repo_slug: Repository identifier
            commit_sha: The commit SHA that was just processed
        """
        self._state[f"last_commit:{repo_slug}"] = commit_sha
        self._increment_and_maybe_flush()

    def is_commit_processed(self, repo_slug: str, commit_sha: str) -> bool:
        """
        Check if a specific commit has already been processed.

        Args:
            repo_slug: Repository identifier
            commit_sha: The commit SHA to check

        Returns:
            True if the commit was processed, False otherwise
        """
        key = f"processed:{repo_slug}:{commit_sha}"
        return key in self._state

    def mark_commit_processed(self, repo_slug: str, commit_sha: str) -> None:
        """
        Mark a commit as processed.

        Args:
            repo_slug: Repository identifier
            commit_sha: The commit SHA that was processed
        """
        key = f"processed:{repo_slug}:{commit_sha}"
        self._state[key] = True
        self._increment_and_maybe_flush()

    def get_processed_count(self, repo_slug: str) -> int:
        """
        Get the count of processed commits for a repository.

        Args:
            repo_slug: Repository identifier

        Returns:
            Number of processed commits
        """
        return self._state.get(f"count:{repo_slug}", 0)

    def increment_processed_count(self, repo_slug: str) -> int:
        """
        Increment and return the processed count for a repository.

        Args:
            repo_slug: Repository identifier

        Returns:
            The new count after incrementing
        """
        key = f"count:{repo_slug}"
        with self._lock:
            current = self._state.get(key, 0)
            new_count = current + 1
            self._state[key] = new_count
        self._increment_and_maybe_flush()
        return new_count

    def _increment_and_maybe_flush(self) -> None:
        """Increment update counter and flush if threshold reached."""
        with self._lock:
            self._update_count.value += 1
            if self._update_count.value >= self.flush_threshold:
                # Trigger immediate flush in background
                threading.Thread(
                    target=self.flush_to_disk,
                    daemon=True
                ).start()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current state statistics.

        Returns:
            Dict with state statistics
        """
        state_dict = dict(self._state)
        return {
            "total_entries": len(state_dict),
            "processed_commits": sum(1 for k in state_dict if k.startswith("processed:")),
            "tracked_repos": sum(1 for k in state_dict if k.startswith("last_commit:")),
            "pending_updates": self._update_count.value
        }

    @property
    def shared_dict(self) -> DictProxy:
        """
        Get the underlying shared dictionary for direct access.

        Use with caution - prefer the typed methods above.
        """
        return self._state

    @property
    def lock(self):
        """Get the shared lock for external synchronization."""
        return self._lock


@contextmanager
def managed_state(state_file_path: str, **kwargs):
    """
    Context manager for StateManager with automatic cleanup.

    Usage:
        with managed_state("./data/state.json") as state:
            state.set_last_commit("owner/repo", "abc123")
    """
    manager = StateManager(state_file_path, **kwargs)
    manager.start_background_flush()
    try:
        yield manager
    finally:
        manager.stop_background_flush()
        manager.flush_to_disk()
