from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime


class RepoInfo(BaseModel):
    url: str
    commit_hash: str
    commit_date: datetime


class LabelsGroup(BaseModel):
    memory_errors: int = Field(0, ge=0, le=1)
    undefined_behavior: int = Field(0, ge=0, le=1)
    correctness: int = Field(0, ge=0, le=1)
    performance: int = Field(0, ge=0, le=1)
    style: int = Field(0, ge=0, le=1)


class Labels(BaseModel):
    cppcheck: Dict[str, int] = {}
    clang: Dict[str, int] = {}
    groups: LabelsGroup


class CodeEntry(BaseModel):
    code_original: str
    code_fixed: Optional[str] = None
    code_hash: str
    repo: RepoInfo
    ingest_timestamp: datetime
    labels: Labels
