from scraper.core.engine import run_scraper
from scraper.network.server import start_server


def run_scraper_with_progress(config_path: str, progress_callback) -> None:
    """Wrapper that passes progress callback to run_scraper."""
    run_scraper(config_path, progress_callback=progress_callback)


def main():
    start_server(run_scraper_with_progress)


if __name__ == "__main__":
    main()
