import os
import tempfile
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class RepoConfig:
    """Configuration for a single repository to scrape."""
    url: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    fix_regexes: List[str] = field(default_factory=list)


@dataclass
class ScraperConfig:
    """
    Main scraper configuration.

    Attributes:
        repositories: List of repositories to scrape
        github_tokens: List of GitHub tokens for parallel fetching (round-robin assignment)
        target_record_count: Global target for total records across ALL repositories
        num_consumer_workers: Number of consumer (labeler) processes
        temp_work_dir: Directory for temporary files (use RAM disk for performance)
        queue_max_size: Maximum size of the task queue (backpressure control)
    """
    repositories: List[RepoConfig]
    github_tokens: List[str] = field(default_factory=list)
    target_record_count: int = 1000
    num_consumer_workers: int = field(default_factory=lambda: max(1, (os.cpu_count() or 4) // 2))
    temp_work_dir: str = field(default_factory=tempfile.gettempdir)
    queue_max_size: int = 100

    # Legacy support: single token (deprecated, use github_tokens list)
    github_token: Optional[str] = None

    def get_effective_tokens(self) -> List[str]:
        """Get list of tokens, including legacy single token if present."""
        tokens = list(self.github_tokens) if self.github_tokens else []
        if self.github_token and self.github_token not in tokens:
            tokens.append(self.github_token)
        # Also check environment variable
        env_token = os.getenv("GITHUB_TOKEN")
        if env_token and env_token not in tokens:
            tokens.append(env_token)
        return tokens
