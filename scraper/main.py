import time
from scraper.network.server import start_server
from scraper.core.engine import run_scraper
from scraper.config.scraper_config import ScraperConfig, RepoConfig


def main():
    start_server(run_scraper)
    # run_scraper("./scraper/config.json")


if __name__ == "__main__":
    main()
