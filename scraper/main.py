import os

from scraper.core.engine import run_scraper
from scraper.core.parallel import run_parallel_scraper, ParallelScanResult
from scraper.network.server import start_server


def run_scraper_with_progress(config_path: str, progress_callback) -> None:
    """Wrapper that passes progress callback to run_scraper."""
    run_scraper(config_path, progress_callback=progress_callback)


def run_parallel_scraper_with_progress(config_path: str, progress_callback) -> ParallelScanResult:
    """Wrapper that runs parallel scraper with progress callback."""
    # Get max workers from environment or use default
    max_workers = int(os.getenv("SCRAPER_MAX_WORKERS", "4"))

    return run_parallel_scraper(
        config_path=config_path,
        max_workers=max_workers,
        progress_callback=progress_callback
    )


def main():
    start_server(
        callback=run_scraper_with_progress,
        parallel_callback=run_parallel_scraper_with_progress
    )


if __name__ == "__main__":
    main()

