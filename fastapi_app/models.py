from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

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
    unused_code: bool = False
    const_correctness: bool = False
    redundant_code: bool = False
    stl_misuse: bool = False
    class_design: bool = False
    code_style: bool = False


class Labels(BaseModel):
    cppcheck: List[str] = []
    clang: Dict[str, Any] = Field(default_factory=dict)
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


class LabelUpdateRequest(BaseModel):
    """Request body for adding/removing labels from an entry."""
    add: List[str] = Field(default_factory=list, description="Labels to add to the entry")
    remove: List[str] = Field(default_factory=list, description="Labels to remove from the entry")
