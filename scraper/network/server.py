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
        except Exception:
            pass  # Ignore send errors


def start_server(callback: Callable[[str, Any], Any]) -> None:
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

            decoded_data = data.decode()

            if decoded_data.startswith("SCRAPE "):
                filename = decoded_data[7:]
                response = f"ACK: Scraping {filename}".encode()
                conn.sendall(response)
                callback(filename, send_progress)
                response = f"ACK: Finished Scraping {filename}".encode()
                conn.sendall(response)
            else:
                response = b"ERROR: Invalid format. Use: SCRAPE {filename}"
                conn.sendall(response)
            _current_conn = None
