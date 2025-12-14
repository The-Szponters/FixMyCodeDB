import socket
from typing import Any, Callable


def start_server(callback: Callable[[str], Any]) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # nosec B104: Binding to all interfaces is required for Docker networking
    sock.bind(("0.0.0.0", 8080))  # nosec B104
    sock.listen()

    print("TCP Server listening...")

    while True:
        conn, addr = sock.accept()
        with conn:
            data = conn.recv(1024)
            if not data:
                continue

            decoded_data = data.decode()

            if decoded_data.startswith("SCRAPE "):
                filename = decoded_data[7:]
                response = f"ACK: Scraping {filename}".encode()
                conn.sendall(response)
                callback(filename)
                response = f"ACK: Finished Scraping {filename}".encode()
                conn.sendall(response)
            else:
                response = b"ERROR: Invalid format. Use: SCRAPE {filename}"
                conn.sendall(response)
