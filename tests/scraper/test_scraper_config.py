"""
Unit tests for scraper/config/scraper_config.py
Tests ScraperConfig and RepoConfig dataclasses.
"""
import pytest
from unittest.mock import patch
import os
from datetime import date


class TestRepoConfig:
    """Tests for RepoConfig dataclass."""

    def test_init_with_url_only(self):
        """Test creating RepoConfig with just URL."""
        from scraper.config.scraper_config import RepoConfig

        config = RepoConfig(url="https://github.com/owner/repo")

        assert config.url == "https://github.com/owner/repo"
        assert config.start_date is None
        assert config.end_date is None
        assert config.fix_regexes == []

    def test_init_with_dates(self):
        """Test creating RepoConfig with date range."""
        from scraper.config.scraper_config import RepoConfig

        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        config = RepoConfig(
            url="https://github.com/owner/repo",
            start_date=start,
            end_date=end
        )

        assert config.start_date == start
        assert config.end_date == end

    def test_init_with_regexes(self):
        """Test creating RepoConfig with fix regexes."""
        from scraper.config.scraper_config import RepoConfig

        regexes = [r"fix.*bug", r"resolve.*issue"]
        config = RepoConfig(
            url="https://github.com/owner/repo",
            fix_regexes=regexes
        )

        assert config.fix_regexes == regexes
        assert len(config.fix_regexes) == 2

    def test_full_config(self):
        """Test fully specified RepoConfig."""
        from scraper.config.scraper_config import RepoConfig

        config = RepoConfig(
            url="https://github.com/test/repo",
            start_date=date(2023, 6, 1),
            end_date=date(2023, 12, 31),
            fix_regexes=[r"bug\s*fix"]
        )

        assert config.url == "https://github.com/test/repo"
        assert config.start_date.month == 6
        assert len(config.fix_regexes) == 1


class TestScraperConfig:
    """Tests for ScraperConfig dataclass."""

    def test_init_minimal(self):
        """Test ScraperConfig with minimal required fields."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(repositories=repos)

        assert len(config.repositories) == 1
        assert config.github_tokens == []
        assert config.target_record_count == 1000
        assert config.queue_max_size == 100

    def test_init_with_tokens(self):
        """Test ScraperConfig with GitHub tokens."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(
            repositories=repos,
            github_tokens=["token1", "token2"]
        )

        assert config.github_tokens == ["token1", "token2"]

    def test_init_with_custom_workers(self):
        """Test ScraperConfig with custom worker count."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(
            repositories=repos,
            num_consumer_workers=4
        )

        assert config.num_consumer_workers == 4

    def test_init_with_custom_temp_dir(self):
        """Test ScraperConfig with custom temp directory."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(
            repositories=repos,
            temp_work_dir="/custom/temp"
        )

        assert config.temp_work_dir == "/custom/temp"

    def test_init_with_legacy_token(self):
        """Test ScraperConfig with legacy single token."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(
            repositories=repos,
            github_token="legacy_token"
        )

        assert config.github_token == "legacy_token"

    def test_get_effective_tokens_from_list(self):
        """Test get_effective_tokens returns list tokens."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(
            repositories=repos,
            github_tokens=["token1", "token2"]
        )

        with patch.dict(os.environ, {}, clear=True):
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]

            tokens = config.get_effective_tokens()

            assert "token1" in tokens
            assert "token2" in tokens

    def test_get_effective_tokens_includes_legacy(self):
        """Test get_effective_tokens includes legacy token."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(
            repositories=repos,
            github_tokens=["token1"],
            github_token="legacy_token"
        )

        with patch.dict(os.environ, {}, clear=True):
            tokens = config.get_effective_tokens()

            assert "token1" in tokens
            assert "legacy_token" in tokens

    def test_get_effective_tokens_includes_env(self):
        """Test get_effective_tokens includes environment token."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(repositories=repos)

        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token"}):
            tokens = config.get_effective_tokens()

            assert "env_token" in tokens

    def test_get_effective_tokens_no_duplicates(self):
        """Test get_effective_tokens removes duplicates."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(
            repositories=repos,
            github_tokens=["same_token"],
            github_token="same_token"
        )

        with patch.dict(os.environ, {"GITHUB_TOKEN": "same_token"}):
            tokens = config.get_effective_tokens()

            # Should contain only one instance
            assert tokens.count("same_token") == 1

    def test_get_effective_tokens_empty(self):
        """Test get_effective_tokens with no tokens."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(repositories=repos)

        with patch.dict(os.environ, {}, clear=True):
            # Ensure GITHUB_TOKEN is not set
            env_backup = os.environ.get("GITHUB_TOKEN")
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]

            try:
                tokens = config.get_effective_tokens()
                assert tokens == []
            finally:
                if env_backup:
                    os.environ["GITHUB_TOKEN"] = env_backup

    def test_default_temp_dir_uses_tempfile(self):
        """Test default temp_work_dir uses tempfile.gettempdir()."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig
        import tempfile

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(repositories=repos)

        # Should use system temp directory
        assert config.temp_work_dir == tempfile.gettempdir() or callable(config.temp_work_dir)

    def test_default_workers_based_on_cpu(self):
        """Test default workers is based on CPU count."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [RepoConfig(url="https://github.com/test/repo")]
        config = ScraperConfig(repositories=repos)

        # Should be at least 1
        assert config.num_consumer_workers >= 1

    def test_multiple_repositories(self):
        """Test ScraperConfig with multiple repositories."""
        from scraper.config.scraper_config import ScraperConfig, RepoConfig

        repos = [
            RepoConfig(url="https://github.com/owner1/repo1"),
            RepoConfig(url="https://github.com/owner2/repo2"),
            RepoConfig(url="https://github.com/owner3/repo3"),
        ]
        config = ScraperConfig(
            repositories=repos,
            target_record_count=5000
        )

        assert len(config.repositories) == 3
        assert config.target_record_count == 5000
