from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class RepoConfig:
    url: str
    target_record_count: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    fix_regexes: List[str] = field(default_factory=list)


@dataclass
class ScraperConfig:
    repositories: List[RepoConfig]
    github_token: Optional[str] = None
