"""
Unit tests for scraper/config/config_utils.py
Tests configuration loading and validation.
"""
import pytest
from unittest.mock import patch, mock_open
import json


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self):
        """Test loading valid configuration."""
        config_data = {
            "repositories": [
                "https://github.com/test/repo1",
                {"url": "https://github.com/test/repo2"}
            ],
            "github_tokens": ["token1", "token2"],
            "target_record_count": 500
        }
        mock_file = mock_open(read_data=json.dumps(config_data))

        with patch('builtins.open', mock_file):
            from scraper.config.config_utils import load_config

            result = load_config("test.json")

            assert len(result.repositories) == 2
            assert result.repositories[0].url == "https://github.com/test/repo1"
            assert result.github_tokens == ["token1", "token2"]
            assert result.target_record_count == 500

    def test_load_config_with_dates(self):
        """Test loading config with date fields."""
        config_data = {
            "repositories": [
                {
                    "url": "https://github.com/test/repo",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31"
                }
            ]
        }
        mock_file = mock_open(read_data=json.dumps(config_data))

        with patch('builtins.open', mock_file):
            from scraper.config.config_utils import load_config

            result = load_config("config.json")

            assert len(result.repositories) == 1
            assert result.repositories[0].start_date is not None

    def test_load_file_not_found(self):
        """Test handling file not found returns empty config."""
        with patch('builtins.open', side_effect=FileNotFoundError()):
            from scraper.config.config_utils import load_config

            result = load_config("nonexistent.json")

            # Returns empty ScraperConfig
            assert len(result.repositories) == 0

    def test_load_invalid_json(self):
        """Test handling invalid JSON returns empty config."""
        mock_file = mock_open(read_data="not valid json {")

        with patch('builtins.open', mock_file):
            from scraper.config.config_utils import load_config

            result = load_config("invalid.json")

            # Returns empty ScraperConfig
            assert len(result.repositories) == 0

    def test_load_empty_repositories(self):
        """Test loading config with empty repositories."""
        config_data = {"repositories": []}
        mock_file = mock_open(read_data=json.dumps(config_data))

        with patch('builtins.open', mock_file):
            from scraper.config.config_utils import load_config

            result = load_config("empty.json")

            assert len(result.repositories) == 0

    def test_load_config_with_fix_regexes(self):
        """Test loading config with custom fix regexes."""
        config_data = {
            "repositories": [
                {"url": "https://github.com/test/repo", "fix_regexes": [r"custom.*fix"]}
            ],
            "fix_regexes": [r"global.*fix"]
        }
        mock_file = mock_open(read_data=json.dumps(config_data))

        with patch('builtins.open', mock_file):
            from scraper.config.config_utils import load_config

            result = load_config("config.json")

            assert len(result.repositories) == 1
            # Repo has its own fix_regexes
            assert result.repositories[0].fix_regexes == [r"custom.*fix"]

    def test_load_config_with_legacy_token(self):
        """Test loading config with legacy single token."""
        config_data = {
            "repositories": ["https://github.com/test/repo"],
            "github_token": "legacy_token"
        }
        mock_file = mock_open(read_data=json.dumps(config_data))

        with patch('builtins.open', mock_file):
            from scraper.config.config_utils import load_config

            result = load_config("config.json")

            assert result.github_token == "legacy_token"

    def test_load_config_with_workers(self):
        """Test loading config with worker count."""
        config_data = {
            "repositories": ["https://github.com/test/repo"],
            "num_consumer_workers": 8
        }
        mock_file = mock_open(read_data=json.dumps(config_data))

        with patch('builtins.open', mock_file):
            from scraper.config.config_utils import load_config

            result = load_config("config.json")

            assert result.num_consumer_workers == 8


class TestParseDate:
    """Tests for parse_date function."""

    def test_parse_valid_date_string(self):
        """Test parsing valid date string."""
        from scraper.config.config_utils import parse_date

        result = parse_date("2024-06-15")

        assert result is not None
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15

    def test_parse_none(self):
        """Test parsing None returns None."""
        from scraper.config.config_utils import parse_date

        result = parse_date(None)

        assert result is None

    def test_parse_invalid_date_string(self):
        """Test parsing invalid date returns None."""
        from scraper.config.config_utils import parse_date

        result = parse_date("not-a-date")

        assert result is None

    def test_parse_empty_string(self):
        """Test parsing empty string returns None."""
        from scraper.config.config_utils import parse_date

        result = parse_date("")

        assert result is None
