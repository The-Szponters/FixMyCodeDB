from scraper.network.server import start_server
from scraper.core.engine import run_scraper


def main():
    start_server(run_scraper)


if __name__ == "__main__":
    main()
