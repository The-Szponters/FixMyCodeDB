"""
Token Pool Manager for GitHub API rate limit management.
Distributes tokens evenly among worker processes.
"""

import logging
import os
from multiprocessing import Manager
from typing import List, Optional


class TokenPool:
    """
    Manages a pool of GitHub API tokens for parallel processing.
    Distributes tokens evenly among workers to avoid rate limiting.
    """

    def __init__(self, tokens: Optional[List[str]] = None):
        """
        Initialize the token pool.

        Args:
            tokens: List of GitHub API tokens. If None, tries to load from
                   GITHUB_TOKENS (comma-separated) or GITHUB_TOKEN env vars.
        """
        if tokens is None:
            tokens = self._load_tokens_from_env()

        self._tokens = [t.strip() for t in tokens if t and t.strip()]
        self._index = 0

        if not self._tokens:
            logging.warning("No GitHub tokens provided. Rate limits will be strict.")
        else:
            logging.info(f"Token pool initialized with {len(self._tokens)} token(s)")

    def _load_tokens_from_env(self) -> List[str]:
        """Load tokens from environment variables."""
        # First try GITHUB_TOKENS (comma-separated list)
        tokens_str = os.getenv("GITHUB_TOKENS", "")
        if tokens_str:
            return tokens_str.split(",")

        # Fall back to single GITHUB_TOKEN
        single_token = os.getenv("GITHUB_TOKEN", "")
        if single_token:
            return [single_token]

        return []

    @property
    def token_count(self) -> int:
        """Return the number of tokens in the pool."""
        return len(self._tokens)

    def get_token(self, worker_id: int) -> Optional[str]:
        """
        Get a token for a specific worker.
        Distributes tokens evenly using round-robin assignment.

        Args:
            worker_id: The worker process identifier

        Returns:
            A GitHub token string, or None if no tokens available
        """
        if not self._tokens:
            return None

        # Assign token based on worker ID (round-robin)
        token_index = worker_id % len(self._tokens)
        return self._tokens[token_index]

    def get_all_tokens(self) -> List[str]:
        """Return all tokens (for debugging/logging purposes)."""
        return self._tokens.copy()

    def distribute_tokens(self, num_workers: int) -> List[Optional[str]]:
        """
        Distribute tokens to a given number of workers.

        Args:
            num_workers: Number of worker processes

        Returns:
            List of tokens (one per worker), may contain duplicates if
            workers > tokens, or None entries if no tokens available
        """
        if not self._tokens:
            return [None] * num_workers

        return [self.get_token(i) for i in range(num_workers)]


class SharedTokenPool:
    """
    A multiprocessing-safe token pool that can be shared across processes.
    Uses Manager for inter-process communication.
    """

    def __init__(self, tokens: Optional[List[str]] = None):
        """
        Initialize the shared token pool.

        Args:
            tokens: List of GitHub API tokens
        """
        self._manager = Manager()

        if tokens is None:
            tokens = self._load_tokens_from_env()

        cleaned_tokens = [t.strip() for t in tokens if t and t.strip()]
        self._tokens = self._manager.list(cleaned_tokens)
        self._usage_counts = self._manager.dict({i: 0 for i in range(len(cleaned_tokens))})
        self._lock = self._manager.Lock()

    def _load_tokens_from_env(self) -> List[str]:
        """Load tokens from environment variables."""
        tokens_str = os.getenv("GITHUB_TOKENS", "")
        if tokens_str:
            return tokens_str.split(",")

        single_token = os.getenv("GITHUB_TOKEN", "")
        if single_token:
            return [single_token]

        return []

    def get_least_used_token(self) -> Optional[str]:
        """
        Get the token with the lowest usage count.
        Thread-safe and process-safe.

        Returns:
            A GitHub token string, or None if no tokens available
        """
        with self._lock:
            if not self._tokens:
                return None

            # Find token with minimum usage
            min_idx = min(self._usage_counts.keys(), key=lambda k: self._usage_counts[k])
            self._usage_counts[min_idx] = self._usage_counts[min_idx] + 1

            return self._tokens[min_idx]

    @property
    def token_count(self) -> int:
        """Return the number of tokens in the pool."""
        return len(self._tokens)
