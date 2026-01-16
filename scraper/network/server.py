import logging
import socket
from typing import Any, Callable, Optional


# Global reference to current client connection for progress updates
_current_conn: Optional[socket.socket] = None


def send_progress(current: int, total: int, commit_sha: str) -> None:
    """Send progress update to connected client."""
    if _current_conn:
        try:
            msg = f"PROGRESS: {current}/{total} (commit: {commit_sha})\n"
            _current_conn.sendall(msg.encode())
        except OSError as e:
            logging.debug(f"Failed to send progress update: {e}")


def send_parallel_progress(update: dict) -> None:
    """Send parallel scan progress update to connected client."""
    if _current_conn:
        try:
            worker_id = update.get("worker_id", 0)
            current = update.get("current", 0)
            total = update.get("total", 0)
            commit_sha = update.get("commit_sha", "")
            repo_url = update.get("repo_url", "")

            msg = f"PROGRESS: Worker-{worker_id} {current}/{total} (commit: {commit_sha}) [{repo_url}]\n"
            _current_conn.sendall(msg.encode())
        except OSError as e:
            logging.debug(f"Failed to send parallel progress update: {e}")


def start_server(callback: Callable[[str, Any], Any], parallel_callback: Callable[[str, Any], Any] = None) -> None:
    """
    Start the TCP server that listens for scrape commands.

    Args:
        callback: Function to handle sequential scraping (config_path, progress_callback)
        parallel_callback: Function to handle parallel scraping (config_path, progress_callback)
    """
    global _current_conn
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # nosec B104: Binding to all interfaces is required for Docker networking
    sock.bind(("0.0.0.0", 8080))  # nosec B104
    sock.listen()

    print("TCP Server listening...")

    while True:
        conn, addr = sock.accept()
        with conn:
            _current_conn = conn
            data = conn.recv(1024)
            if not data:
                _current_conn = None
                continue

            decoded_data = data.decode().strip()

            if decoded_data.startswith("SCRAPE_PARALLEL "):
                # Parallel scraping command
                filename = decoded_data[16:]
                response = f"ACK: Parallel scraping {filename}".encode()
                conn.sendall(response)

                if parallel_callback:
                    result = parallel_callback(filename, send_parallel_progress)
                    # Send summary
                    summary = (
                        f"RESULT: Completed {result.successful_workers}/{result.total_workers} repos, "
                        f"{result.total_records} records in {result.total_duration_seconds:.1f}s\n"
                    )
                    conn.sendall(summary.encode())
                else:
                    conn.sendall(b"ERROR: Parallel scraping not available\n")

                response = f"ACK: Finished Parallel Scraping {filename}".encode()
                conn.sendall(response)

            elif decoded_data.startswith("SCRAPE "):
                # Sequential scraping command (original behavior)
                filename = decoded_data[7:]
                response = f"ACK: Scraping {filename}".encode()
                conn.sendall(response)
                callback(filename, send_progress)
                response = f"ACK: Finished Scraping {filename}".encode()
                conn.sendall(response)
            else:
                response = b"ERROR: Invalid format. Use: SCRAPE {filename} or SCRAPE_PARALLEL {filename}"
                conn.sendall(response)
            _current_conn = None

