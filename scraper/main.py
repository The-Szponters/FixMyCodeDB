from scraper.core.engine import run_scraper
from scraper.network.server import start_server


def main():
    start_server(run_scraper)


if __name__ == "__main__":
    main()
