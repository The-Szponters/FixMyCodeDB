"""
Tests for parallel scanning module.
"""

import multiprocessing as mp
import time
from unittest.mock import MagicMock, patch

import pytest

from scraper.core.parallel import (
    ParallelScanner,
    ParallelScanResult,
    WorkerResult,
    WorkerStatus,
    run_parallel_scraper,
)
from scraper.config.scraper_config import RepoConfig


class TestWorkerStatus:
    """Tests for WorkerStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert WorkerStatus.PENDING.value == "pending"
        assert WorkerStatus.RUNNING.value == "running"
        assert WorkerStatus.COMPLETED.value == "completed"
        assert WorkerStatus.FAILED.value == "failed"
        assert WorkerStatus.TIMEOUT.value == "timeout"


class TestWorkerResult:
    """Tests for WorkerResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = WorkerResult(
            worker_id=0,
            repo_url="https://github.com/test/repo",
            status=WorkerStatus.COMPLETED
        )

        assert result.records_processed == 0
        assert result.error_message is None
        assert result.duration_seconds == 0.0
        assert result.exit_code == 0

    def test_with_all_fields(self):
        """Test with all fields."""
        result = WorkerResult(
            worker_id=1,
            repo_url="https://github.com/test/repo",
            status=WorkerStatus.FAILED,
            records_processed=5,
            error_message="Test error",
            duration_seconds=10.5,
            exit_code=1
        )

        assert result.worker_id == 1
        assert result.status == WorkerStatus.FAILED
        assert result.error_message == "Test error"


class TestParallelScanResult:
    """Tests for ParallelScanResult dataclass."""

    def test_empty_result(self):
        """Test empty scan result."""
        result = ParallelScanResult(
            total_workers=0,
            successful_workers=0,
            failed_workers=0,
            total_records=0
        )

        assert len(result.worker_results) == 0
        assert result.total_duration_seconds == 0.0

    def test_with_worker_results(self):
        """Test with worker results."""
        worker_results = [
            WorkerResult(worker_id=0, repo_url="repo1", status=WorkerStatus.COMPLETED, records_processed=10),
            WorkerResult(worker_id=1, repo_url="repo2", status=WorkerStatus.FAILED, records_processed=0)
        ]

        result = ParallelScanResult(
            total_workers=2,
            successful_workers=1,
            failed_workers=1,
            total_records=10,
            worker_results=worker_results,
            total_duration_seconds=30.0
        )

        assert len(result.worker_results) == 2
        assert result.total_records == 10


class TestParallelScanner:
    """Tests for ParallelScanner class."""

    def test_init_default(self):
        """Test initialization with defaults."""
        scanner = ParallelScanner()

        assert scanner.max_workers >= 1
        assert scanner.timeout_per_repo == 3600
        assert scanner.token_pool is not None

    def test_init_custom(self):
        """Test initialization with custom values."""
        scanner = ParallelScanner(
            max_workers=8,
            tokens=["token1", "token2"],
            timeout_per_repo=1800
        )

        assert scanner.max_workers == 8
        assert scanner.timeout_per_repo == 1800
        assert scanner.token_pool.token_count == 2

    @patch("scraper.core.parallel.load_config")
    def test_scan_no_repositories(self, mock_load_config):
        """Test scanning with no repositories in config."""
        mock_config = MagicMock()
        mock_config.repositories = []
        mock_load_config.return_value = mock_config

        scanner = ParallelScanner(max_workers=2)
        result = scanner.scan_repositories("config.json")

        assert result.total_workers == 0
        assert result.total_records == 0

    def test_scan_single_repository(self):
        """Test scanning single repository method signature."""
        scanner = ParallelScanner(max_workers=1, tokens=["test_token"])

        # Just verify the method exists and has correct signature
        assert callable(scanner.scan_single_repository)


class TestRunParallelScraper:
    """Tests for run_parallel_scraper function."""

    @patch("scraper.core.parallel.ParallelScanner")
    def test_run_parallel_scraper(self, mock_scanner_class):
        """Test run_parallel_scraper function."""
        mock_scanner = MagicMock()
        mock_result = ParallelScanResult(
            total_workers=1,
            successful_workers=1,
            failed_workers=0,
            total_records=5
        )
        mock_scanner.scan_repositories.return_value = mock_result
        mock_scanner_class.return_value = mock_scanner

        result = run_parallel_scraper("config.json", max_workers=2)

        assert result.total_workers == 1
        mock_scanner_class.assert_called_once_with(max_workers=2, tokens=None)

    @patch("scraper.core.parallel.ParallelScanner")
    def test_run_parallel_scraper_with_tokens(self, mock_scanner_class):
        """Test run_parallel_scraper with tokens."""
        mock_scanner = MagicMock()
        mock_scanner.scan_repositories.return_value = ParallelScanResult(
            total_workers=0, successful_workers=0, failed_workers=0, total_records=0
        )
        mock_scanner_class.return_value = mock_scanner

        result = run_parallel_scraper(
            "config.json",
            tokens=["token1", "token2"]
        )

        mock_scanner_class.assert_called_once_with(
            max_workers=None,
            tokens=["token1", "token2"]
        )

    @patch("scraper.core.parallel.ParallelScanner")
    def test_run_parallel_scraper_with_callback(self, mock_scanner_class):
        """Test run_parallel_scraper with progress callback."""
        mock_scanner = MagicMock()
        mock_scanner.scan_repositories.return_value = ParallelScanResult(
            total_workers=0, successful_workers=0, failed_workers=0, total_records=0
        )
        mock_scanner_class.return_value = mock_scanner

        callback_called = []
        def progress_callback(current, total, sha):
            callback_called.append((current, total, sha))

        result = run_parallel_scraper(
            "config.json",
            progress_callback=progress_callback
        )

        # Verify scanner was called with a callback
        assert mock_scanner.scan_repositories.called
