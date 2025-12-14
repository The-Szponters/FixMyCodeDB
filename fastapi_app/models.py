from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from typing import Optional, Dict, Annotated, List
from datetime import datetime

PyObjectId = Annotated[str, BeforeValidator(str)]


class RepoInfo(BaseModel):
    url: str
    commit_hash: str
    commit_date: datetime


class LabelsGroup(BaseModel):
    memory_management: bool = False
    invalid_access: bool = False
    uninitialized: bool = False
    concurrency: bool = False
    logic_error: bool = False
    resource_leak: bool = False
    security_portability: bool = False
    code_quality_performance: bool = False


class Labels(BaseModel):
    cppcheck: List[str] = []
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
