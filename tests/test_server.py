"""
Tests for scraper/network/server.py module.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestSendProgress:
    """Tests for send_progress function."""

    def test_send_progress_no_connection(self):
        """Test send_progress with no connection."""
        from scraper.network.server import send_progress
        import scraper.network.server as server_module

        # Ensure no connection
        server_module._current_conn = None

        # Should not raise
        send_progress(1, 10, "abc123")

    def test_send_progress_with_connection(self):
        """Test send_progress with active connection."""
        from scraper.network.server import send_progress
        import scraper.network.server as server_module

        mock_conn = MagicMock()
        server_module._current_conn = mock_conn

        send_progress(5, 10, "abc123")

        mock_conn.sendall.assert_called_once()
        call_args = mock_conn.sendall.call_args[0][0].decode()
        assert "PROGRESS: 5/10" in call_args
        assert "abc123" in call_args

        # Cleanup
        server_module._current_conn = None

    def test_send_progress_os_error(self):
        """Test send_progress handles OSError."""
        from scraper.network.server import send_progress
        import scraper.network.server as server_module

        mock_conn = MagicMock()
        mock_conn.sendall.side_effect = OSError("Connection closed")
        server_module._current_conn = mock_conn

        # Should not raise
        send_progress(1, 10, "abc123")

        # Cleanup
        server_module._current_conn = None


class TestSendParallelProgress:
    """Tests for send_parallel_progress function."""

    def test_send_parallel_progress_no_connection(self):
        """Test send_parallel_progress with no connection."""
        from scraper.network.server import send_parallel_progress
        import scraper.network.server as server_module

        server_module._current_conn = None

        # Should not raise
        send_parallel_progress({
            "worker_id": 1,
            "current": 5,
            "total": 10,
            "commit_sha": "abc123",
            "repo_url": "https://github.com/test/repo"
        })

    def test_send_parallel_progress_with_connection(self):
        """Test send_parallel_progress with active connection."""
        from scraper.network.server import send_parallel_progress
        import scraper.network.server as server_module

        mock_conn = MagicMock()
        server_module._current_conn = mock_conn

        send_parallel_progress({
            "worker_id": 2,
            "current": 3,
            "total": 20,
            "commit_sha": "def456",
            "repo_url": "https://github.com/test/repo"
        })

        mock_conn.sendall.assert_called_once()
        call_args = mock_conn.sendall.call_args[0][0].decode()
        assert "Worker-2" in call_args
        assert "3/20" in call_args
        assert "def456" in call_args

        # Cleanup
        server_module._current_conn = None

    def test_send_parallel_progress_os_error(self):
        """Test send_parallel_progress handles OSError."""
        from scraper.network.server import send_parallel_progress
        import scraper.network.server as server_module

        mock_conn = MagicMock()
        mock_conn.sendall.side_effect = OSError("Connection closed")
        server_module._current_conn = mock_conn

        # Should not raise
        send_parallel_progress({"worker_id": 1})

        # Cleanup
        server_module._current_conn = None


class TestStartServer:
    """Tests for start_server function - basic protocol tests."""

    @patch("scraper.network.server.socket.socket")
    def test_server_handles_scrape_command(self, mock_socket_class):
        """Test server handles SCRAPE command."""
        from scraper.network.server import start_server

        # Setup mock socket
        mock_socket = MagicMock()
        mock_conn = MagicMock()
        mock_socket_class.return_value = mock_socket

        # First accept returns connection, second raises to exit loop
        mock_socket.accept.side_effect = [
            (mock_conn, ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        # Connection receives SCRAPE command
        mock_conn.recv.return_value = b"SCRAPE config.json"
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_callback = MagicMock()

        try:
            start_server(mock_callback)
        except KeyboardInterrupt:
            pass

        # Verify callback was called
        mock_callback.assert_called_once()

    @patch("scraper.network.server.socket.socket")
    def test_server_handles_parallel_scrape_command(self, mock_socket_class):
        """Test server handles SCRAPE_PARALLEL command."""
        from scraper.network.server import start_server

        # Setup mock socket
        mock_socket = MagicMock()
        mock_conn = MagicMock()
        mock_socket_class.return_value = mock_socket

        # First accept returns connection, second raises to exit loop
        mock_socket.accept.side_effect = [
            (mock_conn, ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        # Connection receives SCRAPE_PARALLEL command
        mock_conn.recv.return_value = b"SCRAPE_PARALLEL config.json"
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_callback = MagicMock()
        mock_parallel_callback = MagicMock()
        mock_parallel_callback.return_value = MagicMock(
            successful_workers=4,
            total_workers=4,
            total_records=100,
            total_duration_seconds=60.0
        )

        try:
            start_server(mock_callback, parallel_callback=mock_parallel_callback)
        except KeyboardInterrupt:
            pass

        # Verify parallel callback was called
        mock_parallel_callback.assert_called_once()

    @patch("scraper.network.server.socket.socket")
    def test_server_handles_invalid_command(self, mock_socket_class):
        """Test server handles invalid command."""
        from scraper.network.server import start_server

        # Setup mock socket
        mock_socket = MagicMock()
        mock_conn = MagicMock()
        mock_socket_class.return_value = mock_socket

        mock_socket.accept.side_effect = [
            (mock_conn, ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        # Connection receives invalid command
        mock_conn.recv.return_value = b"INVALID command"
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_callback = MagicMock()

        try:
            start_server(mock_callback)
        except KeyboardInterrupt:
            pass

        # Verify error response was sent
        mock_conn.sendall.assert_called()
        call_args = mock_conn.sendall.call_args[0][0]
        assert b"ERROR" in call_args

    @patch("scraper.network.server.socket.socket")
    def test_server_handles_empty_data(self, mock_socket_class):
        """Test server handles empty data."""
        from scraper.network.server import start_server

        mock_socket = MagicMock()
        mock_conn = MagicMock()
        mock_socket_class.return_value = mock_socket

        mock_socket.accept.side_effect = [
            (mock_conn, ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        # Connection receives empty data
        mock_conn.recv.return_value = b""
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_callback = MagicMock()

        try:
            start_server(mock_callback)
        except KeyboardInterrupt:
            pass

        # Callback should not be called for empty data
        mock_callback.assert_not_called()
