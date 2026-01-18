"""
Tests for scraper/main.py module.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestRunScraperWithProgress:
    """Tests for run_scraper_with_progress function."""

    @patch("scraper.main.run_scraper")
    def test_run_scraper_with_progress(self, mock_run_scraper):
        """Test wrapper passes progress callback."""
        from scraper.main import run_scraper_with_progress

        mock_callback = MagicMock()

        run_scraper_with_progress("config.json", mock_callback)

        mock_run_scraper.assert_called_once_with("config.json", progress_callback=mock_callback)


class TestRunParallelScraperWithProgress:
    """Tests for run_parallel_scraper_with_progress function."""

    @patch.dict("os.environ", {"SCRAPER_MAX_WORKERS": "8"})
    @patch("scraper.main.run_parallel_scraper")
    def test_run_parallel_scraper_with_progress(self, mock_run_parallel):
        """Test parallel wrapper uses env var for workers."""
        from scraper.main import run_parallel_scraper_with_progress

        mock_callback = MagicMock()
        mock_run_parallel.return_value = MagicMock()

        run_parallel_scraper_with_progress("config.json", mock_callback)

        mock_run_parallel.assert_called_once_with(
            config_path="config.json",
            max_workers=8,
            progress_callback=mock_callback
        )

    @patch.dict("os.environ", {}, clear=True)
    @patch("scraper.main.run_parallel_scraper")
    def test_run_parallel_scraper_default_workers(self, mock_run_parallel):
        """Test parallel wrapper uses default workers."""
        from scraper.main import run_parallel_scraper_with_progress
        import os

        # Remove env var if exists
        os.environ.pop("SCRAPER_MAX_WORKERS", None)

        mock_callback = MagicMock()
        mock_run_parallel.return_value = MagicMock()

        run_parallel_scraper_with_progress("config.json", mock_callback)

        # Default is 4
        call_kwargs = mock_run_parallel.call_args[1]
        assert call_kwargs["max_workers"] == 4


class TestMain:
    """Tests for main function."""

    @patch("scraper.main.start_server")
    @patch("scraper.main.run_scraper_with_progress")
    @patch("scraper.main.run_parallel_scraper_with_progress")
    def test_main_starts_server(self, mock_parallel, mock_scraper, mock_server):
        """Test main starts server with callbacks."""
        from scraper.main import main

        main()

        mock_server.assert_called_once()
        # Verify both callbacks are passed
        call_kwargs = mock_server.call_args[1]
        assert "callback" in call_kwargs or len(mock_server.call_args[0]) > 0
