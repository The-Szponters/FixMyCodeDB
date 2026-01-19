"""
Scraper Main Entry Point with Repository-Based Parallelism and TUI Dashboard.

This module provides:
- ScraperOrchestrator: Manages downloader threads and analyzer processes
- TUI Dashboard: Real-time monitoring with rich
- Legacy mode: Backward-compatible sequential processing
"""

import atexit
import json
import logging
import multiprocessing as mp
import os
import signal
import sys
import threading
import time
from multiprocessing import Manager, Queue
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from scraper.core.engine import (
    AnalyzerProcess,
    DownloaderThread,
    TokenManager,
    run_scraper,
)
from scraper.network.server import start_server

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


class ScraperOrchestrator:
    """
    Orchestrates the repository-based parallel scraper architecture.

    Features:
    - 1 DownloaderThread per repository (I/O-bound, uses threading)
    - Tokens shared via round-robin with TokenManager
    - Analyzer processes for CPU-bound cppcheck analysis
    - Shared state for TUI dashboard updates
    """

    def __init__(self, config_path: str):
        """
        Initialize the orchestrator.

        Args:
            config_path: Path to the config.json file
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)

        # Multiprocessing manager for shared state
        self.manager = Manager()

        # Shared dictionaries
        self.status_dict = self.manager.dict()  # Process status for TUI
        self.stats_dict = self.manager.dict()   # Global statistics

        # Initialize stats
        self.stats_dict["total_processed"] = 0
        self.stats_dict["successful_findings"] = 0
        self.stats_dict["queue_size"] = 0
        self.stats_dict["start_time"] = time.time()

        # Analysis queue (downloaders -> analyzers)
        self.analysis_queue: Queue = self.manager.Queue()

        # Thread/Process lists
        self.downloaders: List[DownloaderThread] = []
        self.analyzers: List[AnalyzerProcess] = []

        # Token manager (initialized in start())
        self.token_manager: Optional[TokenManager] = None

        # Stop events
        self.thread_stop_event = threading.Event()  # For threads
        self.process_stop_event = mp.Event()  # For processes

        # Register cleanup
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load and validate configuration."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config: {e}")
            return {}

        # Validate required fields
        if "github_tokens" not in config or not config["github_tokens"]:
            logger.warning("No GitHub tokens found in config. Using GITHUB_TOKEN env var.")
            token = os.getenv("GITHUB_TOKEN")
            config["github_tokens"] = [token] if token else []

        if "repositories" not in config or not config["repositories"]:
            logger.error("No repositories found in config.")
            config["repositories"] = []

        # Set defaults
        config.setdefault("batch_size_per_repo", 10)
        config.setdefault("max_analysis_workers", 4)
        config.setdefault("state_file_path", "./data/scraper_state.json")
        config.setdefault("temp_storage_path", "/tmp/scraper")
        config.setdefault("target_record_count", 1000)

        return config

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.stop()

    def _cleanup(self):
        """Cleanup on exit."""
        logger.info("Cleaning up orchestrator...")

        # Cleanup temp storage
        temp_path = self.config.get("temp_storage_path", "/tmp/scraper")
        if os.path.exists(temp_path):
            import shutil
            shutil.rmtree(temp_path, ignore_errors=True)

    def start(self):
        """Start all downloader threads and analyzer processes."""
        tokens = self.config.get("github_tokens", [])
        repositories = self.config.get("repositories", [])

        if not tokens:
            logger.error("No GitHub tokens available. Cannot start.")
            return

        if not repositories:
            logger.error("No repositories to process. Cannot start.")
            return

        # Create temp storage directory
        temp_path = self.config.get("temp_storage_path", "/tmp/scraper")
        os.makedirs(temp_path, exist_ok=True)

        # Initialize TokenManager for thread-safe token sharing
        self.token_manager = TokenManager(tokens)

        logger.info(f"Starting {len(repositories)} downloader threads (1 per repo)")
        logger.info(f"Starting {self.config['max_analysis_workers']} analyzer processes")
        logger.info(f"Using {len(tokens)} tokens with round-robin distribution")

        # Start downloader threads - 1 thread per repository
        for i, repo_url in enumerate(repositories):
            # Round-robin token assignment
            token = self.token_manager.get_token_for_index(i)
            token_label = self.token_manager.get_token_label(token)

            downloader = DownloaderThread(
                thread_id=i + 1,
                repo_url=repo_url,
                token=token,
                token_manager=self.token_manager,
                analysis_queue=self.analysis_queue,
                status_dict=self.status_dict,
                stats_dict=self.stats_dict,
                config=self.config,
                stop_event=self.thread_stop_event,
            )
            self.downloaders.append(downloader)
            downloader.start()

            repo_slug = repo_url.split("github.com/")[-1].rstrip("/").rstrip(".git")
            logger.info(f"Started Downloader [{repo_slug}] with Token {token_label}")

        # Start analyzer processes
        num_analyzers = self.config.get("max_analysis_workers", 4)
        for i in range(num_analyzers):
            analyzer = AnalyzerProcess(
                process_id=i + 1,
                analysis_queue=self.analysis_queue,
                status_dict=self.status_dict,
                stats_dict=self.stats_dict,
                config=self.config,
                stop_event=self.process_stop_event,
            )
            self.analyzers.append(analyzer)
            analyzer.start()
            logger.info(f"Started Analyzer-{i + 1}")

    def stop(self):
        """Stop all threads and processes gracefully."""
        logger.info("Stopping all threads and processes...")

        # Signal stop
        self.thread_stop_event.set()
        self.process_stop_event.set()

        # Wait for downloader threads
        for downloader in self.downloaders:
            downloader.join(timeout=5)
            if downloader.is_alive():
                logger.warning(f"Downloader {downloader.name} did not stop cleanly")

        # Wait for analyzers to finish queue
        timeout = 30
        start_time = time.time()
        while not self.analysis_queue.empty() and (time.time() - start_time) < timeout:
            time.sleep(0.5)

        # Stop analyzers
        for analyzer in self.analyzers:
            analyzer.join(timeout=5)
            if analyzer.is_alive():
                analyzer.terminate()

        logger.info("All threads and processes stopped")

    def is_running(self) -> bool:
        """Check if any thread or process is still running."""
        for t in self.downloaders:
            if t.is_alive():
                return True
        for p in self.analyzers:
            if p.is_alive():
                return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get current status for TUI display."""
        return {
            "status": dict(self.status_dict),
            "stats": dict(self.stats_dict),
            "queue_size": self.analysis_queue.qsize() if self.analysis_queue else 0,
        }


# ============== TUI Dashboard ==============

class ScraperDashboard:
    """
    Real-time TUI dashboard using rich library.

    Displays:
    - Static header
    - Producer status table
    - Consumer status table
    - Live statistics footer
    """

    def __init__(self, orchestrator: ScraperOrchestrator):
        self.orchestrator = orchestrator
        self.console = Console()

    def create_header(self) -> Panel:
        """Create the static header panel."""
        header_text = Text("Scraper Running - FixMyCodeDB", style="bold white on blue")
        header_text.justify = "center"
        return Panel(header_text, style="blue", height=3)

    def create_producers_table(self, status_data: Dict[str, Any]) -> Table:
        """Create the downloaders status table."""
        table = Table(title="🚀 Downloaders (1 per Repository)", expand=True)
        table.add_column("Repository", style="cyan", width=25)
        table.add_column("Token", style="yellow", width=10)
        table.add_column("Status", style="green", width=12)
        table.add_column("Commit", style="magenta", width=10)
        table.add_column("Action", style="blue")

        for key, info in sorted(status_data.items()):
            if not isinstance(info, dict):
                continue
            # Match both "producer" and "downloader" types
            if info.get("type") not in ("producer", "downloader"):
                continue

            status = info.get("status", "unknown")
            status_style = {
                "working": "green",
                "idle": "yellow",
                "done": "blue",
                "error": "red",
                "rate_limited": "red bold",
                "starting": "cyan"
            }.get(status, "white")

            # Get token label (new format) or suffix (old format)
            token_display = info.get("token_label", "")
            if not token_display:
                token_display = f"...{info.get('token_suffix', 'N/A')}"
            else:
                token_display = f"Token {token_display}"

            repo = info.get("repo", "-")
            if len(repo) > 23:
                repo = "..." + repo[-20:]

            table.add_row(
                f"[{repo}]",
                token_display,
                Text(status, style=status_style),
                info.get("commit", "-"),
                info.get("action", "-")[:40]
            )

        return table

    def create_consumers_table(self, status_data: Dict[str, Any]) -> Table:
        """Create the consumers status table."""
        table = Table(title="⚙️  Consumers (Analyzers)", expand=True)
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Status", style="green", width=12)
        table.add_column("Repository", style="white", width=30)
        table.add_column("Commit", style="magenta", width=10)
        table.add_column("Action", style="blue")

        for key, info in sorted(status_data.items()):
            if not isinstance(info, dict):
                continue
            if info.get("type") != "consumer":
                continue

            status = info.get("status", "unknown")
            status_style = {
                "working": "green",
                "idle": "yellow",
                "done": "blue",
                "error": "red",
                "starting": "cyan"
            }.get(status, "white")

            table.add_row(
                key,
                Text(status, style=status_style),
                info.get("repo", "-")[:28],
                info.get("commit", "-"),
                info.get("action", "-")[:50]
            )

        return table

    def create_stats_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create the statistics footer panel."""
        elapsed = time.time() - stats.get("start_time", time.time())
        elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"

        stats_text = Text()
        stats_text.append("✅ Total Successful Findings: ", style="bold green")
        stats_text.append(str(stats.get("successful_findings", 0)), style="bold white")
        stats_text.append("  |  ", style="dim")
        stats_text.append("📦 Queue Size: ", style="bold yellow")
        stats_text.append(str(stats.get("queue_size", 0)), style="bold white")
        stats_text.append("  |  ", style="dim")
        stats_text.append("⏱️  Elapsed: ", style="bold cyan")
        stats_text.append(elapsed_str, style="bold white")
        stats_text.append("  |  ", style="dim")
        stats_text.append("📊 Commits Processed: ", style="bold magenta")
        stats_text.append(str(stats.get("total_processed", 0)), style="bold white")

        return Panel(stats_text, title="Statistics", style="green")

    def create_layout(self) -> Layout:
        """Create the dashboard layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=5)
        )
        layout["body"].split_row(
            Layout(name="producers"),
            Layout(name="consumers")
        )
        return layout

    def run(self):
        """Run the live dashboard."""
        layout = self.create_layout()

        with Live(layout, console=self.console, refresh_per_second=2) as live:
            while self.orchestrator.is_running():
                try:
                    status = self.orchestrator.get_status()

                    layout["header"].update(self.create_header())
                    layout["producers"].update(
                        Panel(self.create_producers_table(status["status"]), border_style="blue")
                    )
                    layout["consumers"].update(
                        Panel(self.create_consumers_table(status["status"]), border_style="cyan")
                    )
                    layout["footer"].update(self.create_stats_panel(status["stats"]))

                    time.sleep(0.5)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Dashboard error: {e}")
                    time.sleep(1)

        # Final status
        self.console.print("\n[bold green]Scraper completed![/bold green]")
        final_stats = self.orchestrator.get_status()["stats"]
        self.console.print(f"Total findings: {final_stats.get('successful_findings', 0)}")


# ============== Entry Points ==============

def run_parallel_scraper(config_path: str, with_tui: bool = True) -> None:
    """
    Run the scraper in parallel mode with producer-consumer architecture.

    Args:
        config_path: Path to config.json
        with_tui: Whether to show the TUI dashboard
    """
    orchestrator = ScraperOrchestrator(config_path)

    try:
        orchestrator.start()

        if with_tui:
            dashboard = ScraperDashboard(orchestrator)
            dashboard.run()
        else:
            # Simple wait mode
            while orchestrator.is_running():
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        orchestrator.stop()


def run_scraper_with_progress(config_path: str, progress_callback: Callable) -> None:
    """
    Legacy wrapper that passes progress callback to run_scraper.
    Used by the network server for backward compatibility.
    """
    run_scraper(config_path, progress_callback=progress_callback)


def main():
    """Main entry point - starts the TCP server for CLI communication."""
    start_server(run_scraper_with_progress)


def main_parallel():
    """Main entry point for parallel mode with TUI."""
    import argparse

    parser = argparse.ArgumentParser(description="FixMyCodeDB Parallel Scraper")
    parser.add_argument(
        "--config", "-c",
        default="scraper/config.json",
        help="Path to config.json"
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Disable TUI dashboard"
    )

    args = parser.parse_args()

    run_parallel_scraper(args.config, with_tui=not args.no_tui)


if __name__ == "__main__":
    main()
