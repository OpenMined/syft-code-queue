"""
Pydantic models for syft-code-queue UI API
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Standard message response."""
    message: str
    code: Optional[str] = None


class JobFileInfo(BaseModel):
    """Information about a file in a job."""
    path: str
    type: str
    size: int
    content: Optional[str] = None
    modified_at: Optional[datetime] = None


class JobResponse(BaseModel):
    """Basic job information."""
    uid: str
    sender: str
    status: str
    created_at: datetime
    time_ago: str
    datasite: str
    files: List[Dict[str, Any]] = Field(default_factory=list)
    description: Optional[str] = None
    is_recent: bool = False


class JobListResponse(BaseModel):
    """Response for job list endpoint."""
    jobs: List[JobResponse]
    total: int
    filtered: bool = False


class JobDetailsResponse(BaseModel):
    """Detailed job information."""
    uid: str
    sender: str
    status: str
    created_at: datetime
    time_ago: str
    datasite: str
    description: Optional[str] = None
    files: List[JobFileInfo] = Field(default_factory=list)
    logs: Optional[str] = None
    output: Optional[str] = None
    is_recent: bool = False


class JobStatsResponse(BaseModel):
    """Job statistics."""
    total: int
    pending: int
    running: int
    completed: int
    failed: int
    recent: int


class JobActionRequest(BaseModel):
    """Request to perform an action on a job."""
    action: str = Field(..., description="Action to perform: review, logs, or output") 