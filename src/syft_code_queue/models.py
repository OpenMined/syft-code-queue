"""Simple models for syft-code-queue."""

import enum
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class JobStatus(str, enum.Enum):
    """Status of a code execution job."""
    pending = "pending"          # Waiting for approval
    approved = "approved"        # Approved, waiting to run
    running = "running"          # Currently executing
    completed = "completed"      # Finished successfully
    failed = "failed"           # Execution failed
    rejected = "rejected"       # Rejected by data owner


class CodeJob(BaseModel):
    """Represents a code execution job in the queue."""
    
    # Core identifiers
    uid: UUID = Field(default_factory=uuid4)
    name: str
    
    # Requester info
    requester_email: str
    target_email: str  # Data owner who needs to approve
    
    # Code details
    code_folder: Path  # Local path to code folder
    description: Optional[str] = None
    
    # Status and timing
    status: JobStatus = JobStatus.pending
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results
    output_folder: Optional[Path] = None
    error_message: Optional[str] = None
    exit_code: Optional[int] = None
    
    # Metadata
    tags: list[str] = Field(default_factory=list)
    
    def update_status(self, new_status: JobStatus, error_message: Optional[str] = None):
        """Update job status with timestamp."""
        self.status = new_status
        self.updated_at = datetime.now()
        
        if new_status == JobStatus.running:
            self.started_at = datetime.now()
        elif new_status in (JobStatus.completed, JobStatus.failed, JobStatus.rejected):
            self.completed_at = datetime.now()
            
        if error_message:
            self.error_message = error_message
    
    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (JobStatus.completed, JobStatus.failed, JobStatus.rejected)
    
    @property
    def duration(self) -> Optional[float]:
        """Get job duration in seconds if completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class JobCreate(BaseModel):
    """Request to create a new code job."""
    name: str
    target_email: str
    code_folder: Path
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class JobUpdate(BaseModel):
    """Request to update a job."""
    uid: UUID
    status: Optional[JobStatus] = None
    error_message: Optional[str] = None
    exit_code: Optional[int] = None


class QueueConfig(BaseModel):
    """Configuration for the code queue."""
    queue_name: str = "code-queue"
    max_concurrent_jobs: int = 3
    job_timeout: int = 300  # 5 minutes default
    cleanup_completed_after: int = 86400  # 24 hours 