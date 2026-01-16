"""
Tests for scraper configuration modules.
"""

import json
import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

from scraper.config.config_utils import load_config, load_config_with_tokens, parse_date
from scraper.config.scraper_config import RepoConfig, ScraperConfig
from scraper.config.token_pool import TokenPool, SharedTokenPool


class TestParseDate:
    """Tests for parse_date function."""

    def test_valid_date(self):
        """Test parsing a valid date string."""
        result = parse_date("2024-06-15")
        assert result == date(2024, 6, 15)

    def test_empty_date(self):
        """Test parsing an empty string."""
        result = parse_date("")
        assert result is None

    def test_none_date(self):
        """Test parsing None."""
        result = parse_date(None)
        assert result is None

    def test_invalid_date_format(self):
        """Test parsing invalid date format."""
        result = parse_date("15/06/2024")  # Wrong format
        assert result is None

    def test_invalid_date_string(self):
        """Test parsing invalid date string."""
        result = parse_date("not-a-date")
        assert result is None


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, sample_config_file):
        """Test loading a valid config file."""
        config = load_config(sample_config_file)

        assert isinstance(config, ScraperConfig)
        assert len(config.repositories) == 2
        assert config.repositories[0].url == "https://github.com/test/repo1"
        assert config.repositories[0].target_record_count == 5

    def test_load_nonexistent_file(self):
        """Test loading a non-existent file."""
        config = load_config("/nonexistent/path/config.json")

        assert isinstance(config, ScraperConfig)
        assert len(config.repositories) == 0

    def test_load_invalid_json(self, tmp_path):
        """Test loading a file with invalid JSON."""
        config_path = tmp_path / "invalid.json"
        config_path.write_text("{ invalid json }")

        config = load_config(str(config_path))

        assert isinstance(config, ScraperConfig)
        assert len(config.repositories) == 0

    def test_load_config_with_dates(self, tmp_path):
        """Test loading config with start/end dates."""
        config_data = {
            "repositories": [
                {
                    "url": "https://github.com/test/repo",
                    "target_record_count": 10,
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31"
                }
            ]
        }
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        config = load_config(str(config_path))

        assert config.repositories[0].start_date == date(2024, 1, 1)
        assert config.repositories[0].end_date == date(2024, 12, 31)

    def test_load_config_missing_required_fields(self, tmp_path):
        """Test loading config with missing required fields."""
        config_data = {
            "repositories": [
                {"url": "https://github.com/test/repo"},  # Missing target_record_count
                {"target_record_count": 10}  # Missing url
            ]
        }
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        config = load_config(str(config_path))

        assert len(config.repositories) == 0

    def test_load_config_default_regexes(self, tmp_path):
        """Test that default fix regexes are applied."""
        config_data = {
            "repositories": [
                {
                    "url": "https://github.com/test/repo",
                    "target_record_count": 10
                }
            ]
        }
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        config = load_config(str(config_path))

        assert len(config.repositories[0].fix_regexes) > 0


class TestLoadConfigWithTokens:
    """Tests for load_config_with_tokens function."""

    def test_load_config_with_tokens_from_file(self, tmp_path):
        """Test loading config with tokens from file."""
        config_data = {
            "tokens": ["token1", "token2", "token3"],
            "max_workers": 4,
            "repositories": [
                {
                    "url": "https://github.com/test/repo",
                    "target_record_count": 10
                }
            ]
        }
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        config, tokens, max_workers = load_config_with_tokens(str(config_path))

        assert len(tokens) == 3
        assert tokens == ["token1", "token2", "token3"]
        assert max_workers == 4

    def test_load_config_with_tokens_from_env(self, tmp_path, monkeypatch):
        """Test loading tokens from environment variable."""
        config_data = {
            "repositories": [
                {
                    "url": "https://github.com/test/repo",
                    "target_record_count": 10
                }
            ]
        }
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        monkeypatch.setenv("GITHUB_TOKENS", "env_token1,env_token2")

        config, tokens, max_workers = load_config_with_tokens(str(config_path))

        assert len(tokens) == 2
        assert "env_token1" in tokens

    def test_load_config_default_max_workers(self, tmp_path):
        """Test default max_workers value."""
        config_data = {
            "repositories": [
                {
                    "url": "https://github.com/test/repo",
                    "target_record_count": 10
                }
            ]
        }
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        config, tokens, max_workers = load_config_with_tokens(str(config_path))

        assert max_workers == 4  # Default value


class TestTokenPool:
    """Tests for TokenPool class."""

    def test_init_with_tokens(self):
        """Test initialization with provided tokens."""
        pool = TokenPool(tokens=["token1", "token2", "token3"])

        assert pool.token_count == 3

    def test_init_empty(self):
        """Test initialization with no tokens."""
        pool = TokenPool(tokens=[])

        assert pool.token_count == 0

    def test_get_token_round_robin(self):
        """Test token distribution with round-robin."""
        pool = TokenPool(tokens=["a", "b", "c"])

        assert pool.get_token(0) == "a"
        assert pool.get_token(1) == "b"
        assert pool.get_token(2) == "c"
        assert pool.get_token(3) == "a"  # Wraps around

    def test_get_token_no_tokens(self):
        """Test getting token when pool is empty."""
        pool = TokenPool(tokens=[])

        assert pool.get_token(0) is None

    def test_distribute_tokens(self):
        """Test distributing tokens to workers."""
        pool = TokenPool(tokens=["a", "b"])

        distributed = pool.distribute_tokens(4)

        assert len(distributed) == 4
        assert distributed[0] == "a"
        assert distributed[1] == "b"
        assert distributed[2] == "a"
        assert distributed[3] == "b"

    def test_distribute_tokens_no_tokens(self):
        """Test distribution with no tokens."""
        pool = TokenPool(tokens=[])

        distributed = pool.distribute_tokens(3)

        assert len(distributed) == 3
        assert all(t is None for t in distributed)

    def test_get_all_tokens(self):
        """Test getting all tokens."""
        original = ["token1", "token2"]
        pool = TokenPool(tokens=original)

        all_tokens = pool.get_all_tokens()

        assert all_tokens == original
        assert all_tokens is not pool._tokens  # Should be a copy

    def test_token_cleanup(self):
        """Test that whitespace is cleaned from tokens."""
        pool = TokenPool(tokens=["  token1  ", "token2\n", "\ttoken3"])

        assert pool.get_token(0) == "token1"
        assert pool.get_token(1) == "token2"
        assert pool.get_token(2) == "token3"

    def test_empty_tokens_filtered(self):
        """Test that empty tokens are filtered out."""
        pool = TokenPool(tokens=["token1", "", "  ", "token2"])

        assert pool.token_count == 2


class TestRepoConfig:
    """Tests for RepoConfig dataclass."""

    def test_default_values(self):
        """Test default values for optional fields."""
        config = RepoConfig(url="https://github.com/test/repo", target_record_count=10)

        assert config.start_date is None
        assert config.end_date is None
        assert config.fix_regexes == []

    def test_with_all_fields(self):
        """Test creation with all fields."""
        config = RepoConfig(
            url="https://github.com/test/repo",
            target_record_count=10,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            fix_regexes=["(?i)\\bfix\\b"]
        )

        assert config.url == "https://github.com/test/repo"
        assert config.target_record_count == 10
        assert config.start_date == date(2024, 1, 1)


class TestScraperConfig:
    """Tests for ScraperConfig dataclass."""

    def test_empty_repositories(self):
        """Test creation with empty repositories list."""
        config = ScraperConfig(repositories=[])

        assert len(config.repositories) == 0

    def test_with_repositories(self):
        """Test creation with repositories."""
        repos = [
            RepoConfig(url="https://github.com/test/repo1", target_record_count=5),
            RepoConfig(url="https://github.com/test/repo2", target_record_count=10)
        ]
        config = ScraperConfig(repositories=repos)

        assert len(config.repositories) == 2
