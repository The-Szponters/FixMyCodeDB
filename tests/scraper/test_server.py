"""
Unit tests for scraper/network/server.py
Tests socket server with mocked connections.
"""
import pytest
from unittest.mock import MagicMock, patch
import socket


class TestSendProgress:
    """Tests for send_progress function."""

    def test_send_progress_with_connection(self):
        """Test sending progress when connected."""
        import scraper.network.server as server

        mock_conn = MagicMock()
        server._current_conn = mock_conn

        server.send_progress(5, 10, "abc1234")

        mock_conn.sendall.assert_called_once()
        call_args = mock_conn.sendall.call_args[0][0]
        assert b"PROGRESS: 5/10" in call_args
        assert b"abc1234" in call_args

    def test_send_progress_without_connection(self):
        """Test sending progress when not connected."""
        import scraper.network.server as server

        server._current_conn = None

        # Should not raise
        server.send_progress(5, 10, "abc1234")

    def test_send_progress_with_error(self):
        """Test sending progress when socket errors."""
        import scraper.network.server as server

        mock_conn = MagicMock()
        mock_conn.sendall.side_effect = OSError("connection reset")
        server._current_conn = mock_conn

        # Should not raise, just log
        server.send_progress(5, 10, "abc1234")


class TestStartServer:
    """Tests for start_server function."""

    def test_server_handles_scrape_command(self):
        """Test server processes SCRAPE command."""
        from scraper.network.server import start_server

        mock_callback = MagicMock()

        with patch('scraper.network.server.socket.socket') as mock_socket_class:
            mock_server_socket = MagicMock()
            mock_conn = MagicMock()

            mock_socket_class.return_value = mock_server_socket

            # First accept returns connection, second raises to exit loop
            call_count = [0]

            def accept_side_effect():
                call_count[0] += 1
                if call_count[0] == 1:
                    return (mock_conn, ("127.0.0.1", 12345))
                raise KeyboardInterrupt()

            mock_server_socket.accept.side_effect = accept_side_effect
            mock_conn.recv.return_value = b"SCRAPE config.json"
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            try:
                start_server(mock_callback)
            except KeyboardInterrupt:
                pass

            mock_callback.assert_called_once()
            # Verify ACK was sent
            mock_conn.sendall.assert_called()

    def test_server_handles_invalid_command(self):
        """Test server handles invalid command."""
        from scraper.network.server import start_server

        mock_callback = MagicMock()

        with patch('scraper.network.server.socket.socket') as mock_socket_class:
            mock_server_socket = MagicMock()
            mock_conn = MagicMock()

            mock_socket_class.return_value = mock_server_socket

            call_count = [0]

            def accept_side_effect():
                call_count[0] += 1
                if call_count[0] == 1:
                    return (mock_conn, ("127.0.0.1", 12345))
                raise KeyboardInterrupt()

            mock_server_socket.accept.side_effect = accept_side_effect
            mock_conn.recv.return_value = b"INVALID command"
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            try:
                start_server(mock_callback)
            except KeyboardInterrupt:
                pass

            # Callback should NOT be called for invalid command
            mock_callback.assert_not_called()
            # Error response should be sent
            assert mock_conn.sendall.called
            call_args = mock_conn.sendall.call_args[0][0]
            assert b"ERROR" in call_args

    def test_server_handles_empty_data(self):
        """Test server handles empty data."""
        from scraper.network.server import start_server

        mock_callback = MagicMock()

        with patch('scraper.network.server.socket.socket') as mock_socket_class:
            mock_server_socket = MagicMock()
            mock_conn = MagicMock()

            mock_socket_class.return_value = mock_server_socket

            call_count = [0]

            def accept_side_effect():
                call_count[0] += 1
                if call_count[0] <= 2:
                    return (mock_conn, ("127.0.0.1", 12345))
                raise KeyboardInterrupt()

            mock_server_socket.accept.side_effect = accept_side_effect
            # First connection sends empty, second sends valid then exits
            recv_count = [0]

            def recv_side_effect(size):
                recv_count[0] += 1
                if recv_count[0] == 1:
                    return b""  # Empty
                return b"SCRAPE config.json"

            mock_conn.recv.side_effect = recv_side_effect
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            try:
                start_server(mock_callback)
            except KeyboardInterrupt:
                pass

    def test_server_binds_correctly(self):
        """Test server binds to correct address."""
        from scraper.network.server import start_server

        mock_callback = MagicMock()

        with patch('scraper.network.server.socket.socket') as mock_socket_class:
            mock_server_socket = MagicMock()
            mock_socket_class.return_value = mock_server_socket
            mock_server_socket.accept.side_effect = KeyboardInterrupt()

            try:
                start_server(mock_callback)
            except KeyboardInterrupt:
                pass

            mock_server_socket.bind.assert_called_once_with(("0.0.0.0", 8080))
            mock_server_socket.listen.assert_called_once()
