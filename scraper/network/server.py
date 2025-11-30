import socket
import threading
from typing import Any, Callable


def start_server(callback: Callable[[str], Any]) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', 60000))

    print("UDP Server listening...")

    while True:
        data, addr = sock.recvfrom(512)
        decoded_data = data.decode()
        response = b""

        if decoded_data.startswith("SCRAPE "):
            filename = decoded_data[7:]
            thread = threading.Thread(target=callback, args=(filename,))
            thread.start()
            response = f"ACK: Scraping {filename}".encode()
        else:
            response = b"ERROR: Invalid format. Use: SCRAPE {filename}"

        sock.sendto(response, addr)
