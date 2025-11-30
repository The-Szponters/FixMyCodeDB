from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from typing import Optional, Dict, Annotated
from datetime import datetime

PyObjectId = Annotated[str, BeforeValidator(str)]


class RepoInfo(BaseModel):
    url: str
    commit_hash: str
    commit_date: datetime


class LabelsGroup(BaseModel):
    memory_errors: bool = False
    undefined_behavior: bool = False
    correctness: bool = False
    performance: bool = False
    style: bool = False


class Labels(BaseModel):
    cppcheck: Dict[str, int] = {}
    clang: Dict[str, int] = {}
    groups: LabelsGroup


class CodeEntry(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    code_original: str
    code_fixed: Optional[str] = None
    code_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    repo: RepoInfo
    ingest_timestamp: datetime
    labels: Labels

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )
