"""Tests for syft-code-queue models."""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from syft_code_queue.models import CodeJob, JobStatus, QueueConfig


def test_job_status_enum():
    """Test JobStatus enum values."""
    assert JobStatus.pending == "pending"
    assert JobStatus.approved == "approved"
    assert JobStatus.running == "running"
    assert JobStatus.completed == "completed"
    assert JobStatus.failed == "failed"
    assert JobStatus.rejected == "rejected"


def test_code_job_creation():
    """Test CodeJob creation and validation."""
    job = CodeJob(
        name="Test Job",
        requester_email="requester@example.com",
        target_email="target@example.com",
        code_folder=Path("/tmp/test"),
        description="Test description",
        tags=["test", "demo"]
    )
    
    assert job.name == "Test Job"
    assert job.requester_email == "requester@example.com"
    assert job.target_email == "target@example.com"
    assert job.code_folder == Path("/tmp/test")
    assert job.description == "Test description"
    assert job.tags == ["test", "demo"]
    assert job.status == JobStatus.pending


def test_job_status_updates():
    """Test job status update functionality."""
    job = CodeJob(
        name="Test Job",
        requester_email="requester@example.com",
        target_email="target@example.com",
        code_folder=Path("/tmp/test")
    )
    
    original_updated_at = job.updated_at
    
    # Update to running
    job.update_status(JobStatus.running)
    assert job.status == JobStatus.running
    assert job.started_at is not None
    assert job.updated_at > original_updated_at
    
    # Update to completed
    job.update_status(JobStatus.completed)
    assert job.status == JobStatus.completed
    assert job.completed_at is not None
    
    # Update with error
    job.update_status(JobStatus.failed, "Test error")
    assert job.status == JobStatus.failed
    assert job.error_message == "Test error"


def test_job_terminal_status():
    """Test is_terminal property."""
    job = CodeJob(
        name="Test Job",
        requester_email="requester@example.com",
        target_email="target@example.com",
        code_folder=Path("/tmp/test")
    )
    
    # Non-terminal states
    job.status = JobStatus.pending
    assert not job.is_terminal
    
    job.status = JobStatus.approved
    assert not job.is_terminal
    
    job.status = JobStatus.running
    assert not job.is_terminal
    
    # Terminal states
    job.status = JobStatus.completed
    assert job.is_terminal
    
    job.status = JobStatus.failed
    assert job.is_terminal
    
    job.status = JobStatus.rejected
    assert job.is_terminal


def test_job_duration():
    """Test job duration calculation."""
    job = CodeJob(
        name="Test Job",
        requester_email="requester@example.com",
        target_email="target@example.com",
        code_folder=Path("/tmp/test")
    )
    
    # No duration without timestamps
    assert job.duration is None
    
    # Set timestamps
    job.started_at = datetime(2024, 1, 1, 12, 0, 0)
    job.completed_at = datetime(2024, 1, 1, 12, 0, 5)  # 5 seconds later
    
    assert job.duration == 5.0


def test_queue_config():
    """Test QueueConfig model."""
    config = QueueConfig()
    
    # Test defaults
    assert config.queue_name == "code-queue"
    assert config.max_concurrent_jobs == 3
    assert config.job_timeout == 300
    assert config.cleanup_completed_after == 86400


def test_job_serialization():
    """Test job serialization/deserialization."""
    job = CodeJob(
        name="Test Job",
        requester_email="requester@example.com",
        target_email="target@example.com",
        code_folder=Path("/tmp/test"),
        description="Test description",
        tags=["test", "demo"]
    )
    
    # Serialize
    data = job.model_dump()
    assert data["name"] == "Test Job"
    assert data["requester_email"] == "requester@example.com"
    
    # Deserialize
    restored_job = CodeJob.model_validate(data)
    assert restored_job.name == job.name
    assert restored_job.uid == job.uid
    assert restored_job.requester_email == job.requester_email 