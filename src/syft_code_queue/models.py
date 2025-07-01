"""Simple models for syft-code-queue."""

import enum
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, PrivateAttr

if TYPE_CHECKING:
    from .client import CodeQueueClient


class JobStatus(str, enum.Enum):
    """Status of a code execution job."""

    pending = "pending"  # Waiting for approval
    approved = "approved"  # Approved, waiting to run
    running = "running"  # Currently executing
    completed = "completed"  # Finished successfully
    failed = "failed"  # Execution failed
    rejected = "rejected"  # Rejected by data owner
    timedout = "timedout"  # Timed out waiting for approval


class CodeJob(BaseModel):
    """
    Represents a code execution job in the queue.

    This is a file-backed object - mutable attributes like status, updated_at, etc.
    always read from the current file state rather than cached in-memory values.
    """

    # Core identifiers
    uid: UUID = Field(default_factory=uuid4)
    name: str

    # Requester info
    requester_email: str
    target_email: str  # Data owner who needs to approve

    # Code details
    code_folder: Path  # Local path to code folder
    description: Optional[str] = None

    # Immutable metadata
    created_at: datetime = Field(default_factory=datetime.now)
    timeout_seconds: int = Field(default=86400)  # 24 hours default
    tags: list[str] = Field(default_factory=list)

    # Mutable fields (these store initial/fallback values)
    status: JobStatus = JobStatus.pending
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_folder: Optional[Path] = None
    error_message: Optional[str] = None
    exit_code: Optional[int] = None
    logs: Optional[str] = None

    # Internal references (private attributes)
    _client: Optional["CodeQueueClient"] = PrivateAttr(default=None)
    _datasite_path: Optional[Path] = PrivateAttr(
        default=None
    )  # Track where this job is actually stored
    _cached_data: Optional[dict] = PrivateAttr(default=None)  # Cache for file data
    _last_reload: Optional[datetime] = PrivateAttr(default=None)  # Track last reload time
    _file_backed_fields: set[str] = PrivateAttr(
        default={
            "status",
            "updated_at",
            "started_at",
            "completed_at",
            "output_folder",
            "error_message",
            "exit_code",
            "logs",
        }
    )

    def model_post_init(self, __context):
        """Initialize private attributes after model validation."""
        # Ensure private attributes are initialized after model validation
        if not hasattr(self, "_file_backed_fields") or self._file_backed_fields is None:
            self._file_backed_fields = {
                "status",
                "updated_at",
                "started_at",
                "completed_at",
                "output_folder",
                "error_message",
                "exit_code",
                "logs",
            }
        if not hasattr(self, "_client"):
            self._client = None
        if not hasattr(self, "_datasite_path"):
            self._datasite_path = None
        if not hasattr(self, "_cached_data"):
            self._cached_data = None
        if not hasattr(self, "_last_reload"):
            self._last_reload = None

    def __getattribute__(self, name: str):
        """Override attribute access to provide file-backed properties for mutable fields."""
        # Get the actual value first using object.__getattribute__ to avoid recursion
        if name in (
            "_file_backed_fields",
            "_client",
            "_reload_from_file",
            "_get_file_backed_value",
            "model_fields",
            "model_config",
            "client",
        ):
            return object.__getattribute__(self, name)

        # Check if this is a file-backed field
        # Use a hardcoded list to avoid private attribute access issues
        file_backed_fields = {
            "status",
            "updated_at",
            "started_at",
            "completed_at",
            "output_folder",
            "error_message",
            "exit_code",
            "logs",
        }
        if name in file_backed_fields:
            try:
                return self._get_file_backed_value(name)
            except (AttributeError, TypeError):
                # If file-backed access fails, fall back to normal access
                pass

        # For all other attributes, use normal access
        return object.__getattribute__(self, name)

    @property
    def client(self) -> Optional["CodeQueueClient"]:
        """Get the client reference."""
        return self._client

    @client.setter
    def client(self, value: Optional["CodeQueueClient"]):
        """Set the client reference."""
        self._client = value

    def _get_file_backed_value(self, field_name: str):
        """Get the current value of a field from file."""
        data = self._reload_from_file()

        if field_name == "status":
            status_str = data.get("status", "pending")
            try:
                return JobStatus(status_str)
            except ValueError:
                return JobStatus.pending
        elif field_name == "updated_at":
            updated_str = data.get("updated_at")
            if updated_str:
                try:
                    return datetime.fromisoformat(updated_str)
                except (ValueError, TypeError):
                    pass
            return object.__getattribute__(self, "updated_at")
        elif field_name in ("started_at", "completed_at"):
            time_str = data.get(field_name)
            if time_str:
                try:
                    return datetime.fromisoformat(time_str)
                except (ValueError, TypeError):
                    pass
            return None
        elif field_name == "output_folder":
            output_str = data.get("output_folder")
            if output_str:
                try:
                    return Path(output_str)
                except (ValueError, TypeError):
                    pass
            return None
        else:
            # For other fields (error_message, exit_code, logs), return direct value
            return data.get(field_name)

    def _reload_from_file(self, force: bool = False) -> dict:
        """
        Reload job data from the metadata.json file.

        Args:
            force: Force reload even if recently cached

        Returns:
            Dictionary of job data from file
        """
        # Check if we have a recent cache (within 1 second) and not forcing reload
        now = datetime.now()
        if (
            not force
            and self._cached_data is not None
            and self._last_reload is not None
            and (now - self._last_reload).total_seconds() < 1.0
        ):
            return self._cached_data

        if self._client is None:
            # Return current in-memory values if no client available
            return self._get_current_values_dict()

        try:
            # Read job data directly from metadata.json file to avoid circular dependency
            import json

            # Find the job file using cross-datasite aware search
            job_file = self._client._find_job_file_anywhere(self.uid, self._datasite_path)
            if not job_file or not job_file.exists():
                return self._get_current_values_dict()

            # Update _datasite_path if we found the job in a different location
            if job_file and job_file.exists():
                # Extract the queue directory from the job file path
                # job_file format: .../datasite/app_data/code-queue/jobs/status/uid/metadata.json
                job_file_parts = job_file.parts
                if len(job_file_parts) >= 4 and "jobs" in job_file_parts:
                    jobs_index = job_file_parts.index("jobs")
                    if jobs_index >= 3:
                        queue_dir = Path(*job_file_parts[: jobs_index + 1])
                        # Update _datasite_path if it has changed
                        if self._datasite_path != queue_dir:
                            self._datasite_path = queue_dir

            # Read raw data from file
            with open(job_file) as f:
                raw_data = json.load(f)

            # Extract the fields we care about for live updates
            data = {
                "status": raw_data.get("status", "pending"),
                "updated_at": raw_data.get("updated_at"),
                "started_at": raw_data.get("started_at"),
                "completed_at": raw_data.get("completed_at"),
                "output_folder": raw_data.get("output_folder"),
                "error_message": raw_data.get("error_message"),
                "exit_code": raw_data.get("exit_code"),
                "logs": raw_data.get("logs"),
            }

            # Cache the data
            self._cached_data = data
            self._last_reload = now

            return data

        except Exception:
            # If reload fails, return current in-memory values
            return self._get_current_values_dict()

    def _get_current_values_dict(self) -> dict:
        """Get current in-memory values as a dictionary."""
        # Use object.__getattribute__ to avoid recursion through our custom __getattribute__
        status = object.__getattribute__(self, "status")
        updated_at = object.__getattribute__(self, "updated_at")
        started_at = object.__getattribute__(self, "started_at")
        completed_at = object.__getattribute__(self, "completed_at")
        output_folder = object.__getattribute__(self, "output_folder")
        error_message = object.__getattribute__(self, "error_message")
        exit_code = object.__getattribute__(self, "exit_code")
        logs = object.__getattribute__(self, "logs")

        return {
            "status": status.value if hasattr(status, "value") else str(status),
            "updated_at": updated_at.isoformat() if updated_at else None,
            "started_at": started_at.isoformat() if started_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "output_folder": str(output_folder) if output_folder else None,
            "error_message": error_message,
            "exit_code": exit_code,
            "logs": logs,
        }

    def refresh(self) -> "CodeJob":
        """Force refresh all file-backed properties from disk."""
        self._cached_data = None
        self._last_reload = None
        # Trigger a reload
        self._reload_from_file(force=True)
        return self

    def update_status(self, new_status: JobStatus, error_message: Optional[str] = None):
        """Update job status with timestamp and save to file."""
        now = datetime.now()

        # Update the model fields directly (using object.__setattr__ to bypass our custom __getattribute__)
        object.__setattr__(self, "status", new_status)
        object.__setattr__(self, "updated_at", now)

        if new_status == JobStatus.running:
            object.__setattr__(self, "started_at", now)
        elif new_status in (JobStatus.completed, JobStatus.failed, JobStatus.rejected):
            object.__setattr__(self, "completed_at", now)

        if error_message:
            object.__setattr__(self, "error_message", error_message)

        # Save changes to file via client
        if self._client:
            try:
                self._client._save_job(self)
            except Exception:
                # If save fails, we'll still have updated the in-memory values
                pass

        # Invalidate cache so next property access reads fresh data
        self._cached_data = None
        self._last_reload = None

    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (JobStatus.completed, JobStatus.failed, JobStatus.rejected, JobStatus.timedout)

    @property
    def is_expired(self) -> bool:
        """Check if this job has exceeded its timeout."""
        if self.is_terminal:
            return False  # Terminal jobs can't expire
        
        from datetime import datetime
        now = datetime.now()
        age_seconds = (now - self.created_at).total_seconds()
        return age_seconds > self.timeout_seconds

    @property
    def time_remaining(self) -> int:
        """Get remaining time in seconds before job expires. Returns 0 if expired."""
        if self.is_terminal:
            return 0
        
        from datetime import datetime
        now = datetime.now()
        age_seconds = (now - self.created_at).total_seconds()
        remaining = max(0, self.timeout_seconds - age_seconds)
        return int(remaining)

    def get_timeout_status(self) -> JobStatus:
        """Determine what status an expired job should be moved to."""
        if self.status == JobStatus.pending:
            # Pending jobs that timeout are moved to timedout (datasite owner never responded)
            return JobStatus.timedout
        elif self.status in (JobStatus.approved, JobStatus.running):
            # Approved/running jobs that timeout are considered failed (execution timeout)
            return JobStatus.failed
        else:
            # Should not happen, but default to failed
            return JobStatus.failed

    @property
    def duration(self) -> Optional[float]:
        """Get job duration in seconds if completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def short_id(self) -> str:
        """Get short version of UUID for display."""
        return str(self.uid)[:8]

    def approve(self, reason: Optional[str] = None) -> bool:
        """
        Approve this job for execution.

        Args:
            reason: Optional reason for approval

        Returns:
            bool: True if approved successfully
        """
        if self._client is None:
            raise RuntimeError("Job not connected to DataOwner API - cannot approve")

        success = self._client.approve_job(str(self.uid), reason)
        if success:
            # Invalidate cache so next property access reads the updated status from file
            self._cached_data = None
            self._last_reload = None
        return success

    def reject(self, reason: Optional[str] = None) -> bool:
        """
        Reject this job.

        Args:
            reason: Optional reason for rejection

        Returns:
            bool: True if rejected successfully
        """
        if self._client is None:
            raise RuntimeError("Job not connected to DataOwner API - cannot reject")

        success = self._client.reject_job(str(self.uid), reason)
        if success:
            # Invalidate cache so next property access reads the updated status from file
            self._cached_data = None
            self._last_reload = None
        return success

    def deny(self, reason: Optional[str] = None) -> bool:
        """Alias for reject."""
        return self.reject(reason)

    def get_review_data(self) -> Optional[dict]:
        """Get detailed review information for this job."""
        if self._client is None:
            raise RuntimeError("Job not connected to DataOwner API - cannot review")

        # Get the full job details
        job = self._client.get_job(str(self.uid))
        if job is None:
            return None

        # Get code files if available using the correct client method
        try:
            code_files = self._client.list_job_files(str(self.uid)) or []
        except Exception:
            # If listing files fails, continue without them
            code_files = []

        return {
            "uid": str(self.uid),
            "name": self.name,
            "requester_email": self.requester_email,
            "target_email": self.target_email,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tags": self.tags,
            "code_files": code_files,
            "code_folder": str(self.code_folder),
        }

    def get_output(self) -> Optional[Path]:
        """Get the output directory for this job."""
        if self._client is None:
            raise RuntimeError("Job not connected to DataScientist API - cannot get output")
        return self._client.get_job_output(self.uid)

    def get_logs(self) -> Optional[str]:
        """Get the execution logs for this job."""
        # First try to return the current logs from file
        current_logs = self.logs
        if current_logs is not None:
            return current_logs

        # If no logs field, try to get from client
        if self._client is None:
            raise RuntimeError("Job not connected to DataScientist API - cannot get logs")
        return self._client.get_job_logs(self.uid)

    def wait_for_completion(self, timeout: int = 600) -> "CodeJob":
        """Wait for this job to complete."""
        if self._client is None:
            raise RuntimeError("Job not connected to DataScientist API - cannot wait")
        return self._client.wait_for_completion(self.uid, timeout)

    def list_files(self) -> list[str]:
        """List all files in the job's code directory."""
        if self._client is None:
            raise RuntimeError("Job not connected to API - cannot list files")
        return self._client.list_job_files(str(self.uid))

    def read_file(self, filename: str) -> Optional[str]:
        """Read the contents of a specific file in the job's code directory."""
        if self._client is None:
            raise RuntimeError("Job not connected to API - cannot read file")
        return self._client.read_job_file(str(self.uid), filename)

    def get_code_structure(self) -> dict:
        """Get comprehensive code structure with metadata."""
        if self._client is None:
            raise RuntimeError("Job not connected to API - cannot get code structure")
        return self._client.get_job_code_structure(str(self.uid))

    def list_output_files(self) -> list[str]:
        """List all files in the job's output directory."""
        if self._client is None:
            raise RuntimeError("Job not connected to API - cannot list output files")
        return self._client.list_job_output_files(str(self.uid))

    def read_output_file(self, filename: str) -> Optional[str]:
        """Read the contents of a specific file in the job's output directory."""
        if self._client is None:
            raise RuntimeError("Job not connected to API - cannot read output file")
        return self._client.read_job_output_file(str(self.uid), filename)

    def review(self):
        """Show interactive filesystem UI for code review."""
        if self._client is None:
            raise RuntimeError("Job not connected to DataOwner API - cannot review")

        # Return the interactive filesystem widget
        return FilesystemReviewWidget(self)

    @property
    def output_viewer(self):
        """Show interactive filesystem UI for viewing job output files."""
        if self._client is None:
            raise RuntimeError("Job not connected to API - cannot view output")

        # Return the interactive output viewer widget
        return OutputViewerWidget(self)

    def _repr_html_(self):
        """HTML representation for Jupyter notebooks."""
        import html

        # Determine status styling
        status_class = f"syft-badge-{self.status.value}"

        # Format creation time
        time_display = "unknown"
        try:
            diff = datetime.now() - self.created_at
            if diff.total_seconds() < 60:
                time_display = "just now"
            elif diff.total_seconds() < 3600:
                time_display = f"{int(diff.total_seconds() / 60)}m ago"
            elif diff.total_seconds() < 86400:
                time_display = f"{int(diff.total_seconds() / 3600)}h ago"
            else:
                time_display = f"{int(diff.total_seconds() / 86400)} days ago"
        except (TypeError, AttributeError):
            # Handle cases where created_at is None or invalid
            pass

        # Build tags HTML
        tags_html = ""
        if self.tags:
            tags_html = '<div class="syft-tags">\n'
            for tag in self.tags:
                tags_html += f'            <span class="syft-tag">{html.escape(tag)}</span> '
            tags_html += "\n        </div>\n        "

        # Action buttons based on status and available APIs
        actions_html = ""
        if self.status == JobStatus.pending:
            if self._client is not None:  # This is a job for me to approve
                actions_html = f"""
        <div class="syft-actions">
            <div class="syft-meta">
                Created {time_display}
            </div>
            <div>
                <button class="syft-btn syft-btn-secondary" onclick="(function(){{
                    var code = 'import syft_code_queue as q\\n' +
                               'from IPython.display import display\\n' +
                               'job = q.get_job(\\'{self.uid}\\')\\n' +
                               'if job:\\n' +
                               '    display(job.review())  # Show interactive filesystem UI\\n' +
                               'else:\\n' +
                               '    print(\\'❌ Job {self.uid} not found\\')';
                    navigator.clipboard.writeText(code).then(() => {{
                        this.innerHTML = '👁️ Copied!';
                        this.style.backgroundColor = '#6366f1';
                        setTimeout(() => {{
                            this.innerHTML = '👁️ Review Code';
                            this.style.backgroundColor = '';
                        }}, 2000);
                    }}).catch(() => alert('Code copied. Paste in new cell:\\n\\n' + code));
                }}).call(this)">
                    👁️ Review Code
                </button>
            </div>
        </div>
        """
            else:  # This is my job submitted to others
                actions_html = f"""
        <div class="syft-actions">
            <div class="syft-meta">
                Created {time_display} • Awaiting approval
            </div>
        </div>
        """
        elif self.status in (JobStatus.running, JobStatus.completed, JobStatus.failed):
            if self._client is not None:  # This is my job, can see logs/output
                actions_html = f"""
        <div class="syft-actions">
            <div class="syft-meta">
                Created {time_display}
            </div>
            <div>
                <button class="syft-btn syft-btn-secondary" onclick="(function(){{
                    var code = 'import syft_code_queue as q\\n' +
                               'job = q.get_job(\\'{self.uid}\\')\\n' +
                               'if job:\\n' +
                               '    logs = job.get_logs()\\n' +
                               '    if logs:\\n' +
                               '        print(\\'📜 Execution logs for \\' + job.name + \\':\\')\\n' +
                               '        print(\\'=\\' * 50)\\n' +
                               '        print(logs)\\n' +
                               '        print(\\'=\\' * 50)\\n' +
                               '    else:\\n' +
                               '        print(\\'📜 No logs available for \\' + job.name)\\n' +
                               'else:\\n' +
                               '    print(\\'❌ Job {self.uid} not found\\')';
                    navigator.clipboard.writeText(code).then(() => {{
                        this.innerHTML = '📜 Copied!';
                        this.style.backgroundColor = '#6366f1';
                        setTimeout(() => {{
                            this.innerHTML = '📜 View Logs';
                            this.style.backgroundColor = '';
                        }}, 2000);
                    }}).catch(() => alert('Code copied. Paste in new cell:\\n\\n' + code));
                }}).call(this)">
                    📜 View Logs
                </button>
                <button class="syft-btn syft-btn-secondary" onclick="(function(){{
                    var code = 'import syft_code_queue as q\\n' +
                               'job = q.get_job(\\'{self.uid}\\')\\n' +
                               'if job:\\n' +
                               '    output_path = job.get_output()\\n' +
                               '    if output_path:\\n' +
                               '        print(\\'📁 Output location for \\' + job.name + \\': \\' + str(output_path))\\n' +
                               '        \\n' +
                               '        # Try to show output directory contents\\n' +
                               '        from pathlib import Path\\n' +
                               '        if Path(output_path).exists():\\n' +
                               '            print(\\'\\\\n📋 Output files:\\')\\n' +
                               '            for file in Path(output_path).iterdir():\\n' +
                               '                if file.is_file():\\n' +
                               '                    print(f\\'  📄 {{file.name}} ({{file.stat().st_size}} bytes)\\')\\n' +
                               '                elif file.is_dir():\\n' +
                               '                    print(f\\'  📁 {{file.name}}/\\')\\n' +
                               '        else:\\n' +
                               '            print(\\'⚠️ Output directory does not exist yet\\')\\n' +
                               '    else:\\n' +
                               '        print(\\'📁 No output path available for \\' + job.name)\\n' +
                               'else:\\n' +
                               '    print(\\'❌ Job {self.uid} not found\\')';
                    navigator.clipboard.writeText(code).then(() => {{
                        this.innerHTML = '📁 Copied!';
                        this.style.backgroundColor = '#8b5cf6';
                        setTimeout(() => {{
                            this.innerHTML = '📁 View Output';
                            this.style.backgroundColor = '';
                        }}, 2000);
                    }}).catch(() => alert('Code copied. Paste in new cell:\\n\\n' + code));
                }}).call(this)">
                    📁 View Output
                </button>
            </div>
        </div>
        """
            else:
                actions_html = f"""
        <div class="syft-actions">
            <div class="syft-meta">
                Created {time_display}
            </div>
        </div>
        """
        else:  # rejected or other states
            actions_html = f"""
        <div class="syft-actions">
            <div class="syft-meta">
                Created {time_display}
            </div>
        </div>
        """

        # Add unique timestamp to prevent Jupyter caching
        import time

        timestamp = str(int(time.time() * 1000))

        html_content = f"""
    <div class="syft-job-container">

    <style>
    .syft-job-container {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        line-height: 1.6;
        margin: 0;
        padding: 0;
    }}

    .syft-card {{
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        background: #ffffff;
        margin-bottom: 16px;
        overflow: hidden;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
        transition: all 0.2s ease;
    }}

    .syft-card:hover {{
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }}

    .syft-card-header {{
        padding: 20px 24px 0 24px;
    }}

    .syft-card-content {{
        padding: 20px 24px 24px 24px;
    }}

    .syft-card-title {{
        font-size: 18px;
        font-weight: 600;
        color: #111827;
        margin: 0 0 4px 0;
    }}

    .syft-card-description {{
        color: #6b7280;
        font-size: 14px;
        margin: 0 0 16px 0;
    }}

    .syft-badge {{
        display: inline-flex;
        align-items: center;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 500;
        text-transform: capitalize;
    }}

    .syft-badge-pending {{
        border: 1px solid #fde047;
        background-color: #fefce8;
        color: #ca8a04;
    }}

    .syft-badge-approved {{
        border: 1px solid #6ee7b7;
        background-color: #ecfdf5;
        color: #047857;
    }}

    .syft-badge-running {{
        border: 1px solid #93c5fd;
        background-color: #eff6ff;
        color: #1d4ed8;
    }}

    .syft-badge-completed {{
        border: 1px solid #6ee7b7;
        background-color: #ecfdf5;
        color: #047857;
    }}

    .syft-badge-failed {{
        border: 1px solid #fca5a5;
        background-color: #fef2f2;
        color: #dc2626;
    }}

    .syft-badge-rejected {{
        border: 1px solid #fca5a5;
        background-color: #fef2f2;
        color: #dc2626;
    }}

    .syft-btn {{
        display: inline-flex;
        align-items: center;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        text-decoration: none;
        border: 1px solid;
        margin-right: 8px;
        margin-bottom: 4px;
    }}

    .syft-btn-approve {{
        border-color: #10b981;
        color: #047857;
        background-color: #ecfdf5;
    }}

    .syft-btn-approve:hover {{
        background-color: #d1fae5;
        color: #065f46;
    }}

    .syft-btn-reject {{
        border-color: #ef4444;
        color: #dc2626;
        background-color: #fef2f2;
    }}

    .syft-btn-reject:hover {{
        background-color: #fee2e2;
        color: #b91c1c;
    }}

    .syft-btn-secondary {{
        border-color: #d1d5db;
        color: #374151;
        background-color: #ffffff;
    }}

    .syft-btn-secondary:hover {{
        background-color: #f9fafb;
        color: #111827;
    }}

    .syft-meta {{
        color: #6b7280;
        font-size: 13px;
        margin: 4px 0;
    }}

    .syft-actions {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 16px;
        flex-wrap: wrap;
    }}

    .syft-tags {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin: 8px 0;
    }}

    .syft-tag {{
        background-color: #f3f4f6;
        color: #374151;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
    }}

    .syft-header-row {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 8px;
    }}

    @media (prefers-color-scheme: dark) {{
        .syft-job-container {{
            color: #f9fafb;
        }}

        .syft-card {{
            background: #1f2937;
            border-color: #374151;
        }}

        .syft-card-title {{
            color: #f9fafb;
        }}

        .syft-card-description {{
            color: #9ca3af;
        }}

        .syft-meta {{
            color: #9ca3af;
        }}

        .syft-badge-pending {{
            border-color: #fbbf24;
            background-color: rgba(251, 191, 36, 0.1);
            color: #fbbf24;
        }}

        .syft-badge-approved {{
            border-color: #10b981;
            background-color: rgba(16, 185, 129, 0.1);
            color: #10b981;
        }}

        .syft-badge-completed {{
            border-color: #10b981;
            background-color: rgba(16, 185, 129, 0.1);
            color: #10b981;
        }}

        .syft-badge-failed {{
            border-color: #ef4444;
            background-color: rgba(239, 68, 68, 0.1);
            color: #ef4444;
        }}

        .syft-badge-rejected {{
            border-color: #ef4444;
            background-color: rgba(239, 68, 68, 0.1);
            color: #ef4444;
        }}
    }}
    </style>

        <div class="syft-card">
            <div class="syft-card-header">
                <div class="syft-header-row">
                    <div>
                        <h3 class="syft-card-title">{html.escape(self.name)}</h3>
                        <p class="syft-card-description">{html.escape(self.description or "No description")}</p>
                        {tags_html}
                    </div>
                    <span class="syft-badge {status_class}">{self.status.value}</span>
                </div>
            </div>
            <div class="syft-card-content">
                <div class="syft-meta">
                    <strong>From:</strong> {html.escape(self.requester_email)} •
                    <strong>To:</strong> {html.escape(self.target_email)} •
                    <strong>ID:</strong> {self.short_id}
                </div>
                {actions_html}
            </div>
        </div>



    </div>
    """

        # Add unique comment to force Jupyter to treat this as new content
        return f"<!-- refresh-{timestamp}-{self.uid} -->\n{html_content}"

    def __repr__(self) -> str:
        return f"CodeJob(name='{self.name}', status='{self.status}', id='{self.short_id}')"


class JobCollection(list[CodeJob]):
    """A collection of CodeJob objects that behaves like a list but with additional methods."""

    def __init__(self, jobs: list[CodeJob] = None):
        if jobs is None:
            jobs = []
        super().__init__(jobs)

    def by_status(self, status: JobStatus) -> "JobCollection":
        """Filter jobs by status."""
        filtered = [job for job in self if job.status == status]
        return JobCollection(filtered)

    def by_name(self, name: str) -> "JobCollection":
        """Filter jobs by name (case insensitive)."""
        name_lower = name.lower()
        filtered = [job for job in self if name_lower in job.name.lower()]
        return JobCollection(filtered)

    def by_tags(self, *tags: str) -> "JobCollection":
        """Filter jobs that have any of the specified tags."""
        filtered = []
        for job in self:
            if any(tag in job.tags for tag in tags):
                filtered.append(job)
        return JobCollection(filtered)

    def pending(self) -> "JobCollection":
        """Get only pending jobs."""
        return self.by_status(JobStatus.pending)

    def completed(self) -> "JobCollection":
        """Get only completed jobs."""
        return self.by_status(JobStatus.completed)

    def running(self) -> "JobCollection":
        """Get only running jobs."""
        return self.by_status(JobStatus.running)

    def approve_all(self, reason: Optional[str] = None) -> dict:
        """Approve all jobs in this collection."""
        results = {"approved": 0, "failed": 0, "skipped": 0, "errors": []}
        for job in self:
            try:
                # Check if job is still pending before attempting to approve
                if job.status != JobStatus.pending:
                    results["skipped"] += 1
                    results["errors"].append(
                        f"Job {job.short_id} ({job.name}): Already {job.status.value}, skipping"
                    )
                    continue

                if job.approve(reason):
                    results["approved"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Job {job.short_id} ({job.name}): Approval failed")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Job {job.short_id} ({job.name}): {str(e)}")
        return results

    def reject_all(self, reason: Optional[str] = None) -> dict:
        """Reject all jobs in this collection."""
        results = {"rejected": 0, "failed": 0, "skipped": 0, "errors": []}
        for job in self:
            try:
                # Check if job is still pending before attempting to reject
                if job.status != JobStatus.pending:
                    results["skipped"] += 1
                    results["errors"].append(
                        f"Job {job.short_id} ({job.name}): Already {job.status.value}, skipping"
                    )
                    continue

                if job.reject(reason):
                    results["rejected"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Job {job.short_id} ({job.name}): Rejection failed")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Job {job.short_id} ({job.name}): {str(e)}")
        return results

    def summary(self) -> dict:
        """Get summary statistics for this collection."""
        status_counts = {}
        for status in JobStatus:
            status_counts[status.value] = len(self.by_status(status))

        return {
            "total": len(self),
            "by_status": status_counts,
            "latest": self[-1] if self else None,
        }

    def refresh(self) -> "JobCollection":
        """
        Refresh job statuses from the server.
        Note: This requires jobs to have API connections.
        """
        refreshed_jobs = []
        for job in self:
            if job._client is not None:
                # Try to get updated job from DataOwner API
                updated_job = job._client.get_job(str(job.uid))
                if updated_job:
                    refreshed_jobs.append(updated_job)
                else:
                    refreshed_jobs.append(job)

        return JobCollection(refreshed_jobs)

    def _repr_html_(self):
        """HTML representation for Jupyter notebooks."""
        import html

        if not self:
            return """
            <div style="text-align: center; padding: 40px; color: #6b7280; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                <div style="font-size: 48px; margin-bottom: 16px;">📭</div>
                <div style="font-size: 16px; font-weight: 500;">No jobs found</div>
                <div style="font-size: 14px; margin-top: 8px;">Submit a job to get started</div>
            </div>
            """

        # Determine collection type for header
        summary = self.summary()
        collection_type = "Code Jobs"
        collection_description = "Manage your code execution jobs"

        # Check if this is a filtered collection
        if all(job.status == JobStatus.pending for job in self):
            if all(job._client is not None for job in self):
                # Determine if this is pending_for_me or pending_for_others
                if len(self) > 0:
                    first_job = self[0]
                    user_email = first_job._client.email if first_job._client else None

                    if user_email:
                        # Check if user is the target (pending_for_me) or requester (pending_for_others)
                        if all(job.target_email == user_email for job in self):
                            collection_type = "Jobs Awaiting Your Approval"
                            collection_description = "Review and approve/reject these jobs"
                        elif all(job.requester_email == user_email for job in self):
                            collection_type = "Jobs Awaiting Others' Approval"
                            collection_description = "Jobs you submitted waiting for approval"
                        else:
                            # Mixed collection
                            collection_type = "Pending Jobs"
                            collection_description = "Jobs awaiting approval"
                    else:
                        collection_type = "Pending Jobs"
                        collection_description = "Jobs awaiting approval"
                else:
                    collection_type = "Pending Jobs"
                    collection_description = "Jobs awaiting approval"
            else:
                collection_type = "Pending Jobs"
                collection_description = "Jobs awaiting approval"
        elif all(job.status == JobStatus.completed for job in self):
            collection_type = "Completed Jobs"
            collection_description = "Successfully completed jobs"
        elif all(job.status == JobStatus.running for job in self):
            collection_type = "Running Jobs"
            collection_description = "Currently executing jobs"

        container_id = f"syft-jobs-{hash(str([job.uid for job in self])) % 10000}"

        html_content = f"""
        <style>
        .syft-jobs-container {{
            max-height: 600px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin: 16px 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #ffffff;
        }}
        .syft-jobs-header {{
            background-color: #f8fafc;
            padding: 16px 20px;
            border-bottom: 1px solid #e5e7eb;
            border-radius: 8px 8px 0 0;
        }}
        .syft-jobs-title {{
            font-size: 20px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 4px 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .syft-jobs-count {{
            background-color: #e5e7eb;
            color: #374151;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
        }}
        .syft-jobs-description {{
            color: #6b7280;
            font-size: 14px;
            margin: 0;
        }}
        .syft-jobs-controls {{
            padding: 12px 20px;
            background-color: #ffffff;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .syft-search-box {{
            flex: 1;
            min-width: 200px;
            padding: 8px 12px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 14px;
        }}
        .syft-filter-btn {{
            padding: 8px 12px;
            background-color: #f3f4f6;
            color: #374151;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.2s;
        }}
        .syft-filter-btn:hover, .syft-filter-btn.active {{
            background-color: #3b82f6;
            color: white;
            border-color: #3b82f6;
        }}
        .syft-batch-btn {{
            padding: 8px 12px;
            background-color: #10b981;
            color: white;
            border: 1px solid #10b981;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            margin-left: auto;
        }}
        .syft-batch-btn:hover {{
            background-color: #059669;
        }}
        .syft-batch-btn.reject {{
            background-color: #ef4444;
            border-color: #ef4444;
        }}
        .syft-batch-btn.reject:hover {{
            background-color: #dc2626;
        }}
        .syft-jobs-table-container {{
            max-height: 400px;
            overflow-y: auto;
        }}
        .syft-jobs-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            table-layout: fixed;
        }}
        .syft-jobs-table th {{
            background-color: #f8fafc;
            border-bottom: 2px solid #e5e7eb;
            padding: 8px 12px;
            text-align: left;
            font-weight: 600;
            color: #374151;
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        .syft-jobs-table td {{
            border-bottom: 1px solid #f1f3f4;
            padding: 8px 12px;
            vertical-align: top;
            overflow: hidden;
        }}
        .syft-jobs-table tr:hover {{
            background-color: #f8fafc;
        }}
        .syft-jobs-table tr.syft-selected {{
            background-color: #eff6ff;
        }}

        /* Column width allocation */
        .syft-jobs-table th:nth-child(1), .syft-jobs-table td:nth-child(1) {{ width: 40px; }} /* Checkbox */
        .syft-jobs-table th:nth-child(2), .syft-jobs-table td:nth-child(2) {{ width: 30%; }} /* Job Name */
        .syft-jobs-table th:nth-child(3), .syft-jobs-table td:nth-child(3) {{ width: 80px; }} /* Status */
        .syft-jobs-table th:nth-child(4), .syft-jobs-table td:nth-child(4) {{ width: 15%; }} /* From */
        .syft-jobs-table th:nth-child(5), .syft-jobs-table td:nth-child(5) {{ width: 15%; }} /* To */
        .syft-jobs-table th:nth-child(6), .syft-jobs-table td:nth-child(6) {{ width: 15%; }} /* Tags */
        .syft-jobs-table th:nth-child(7), .syft-jobs-table td:nth-child(7) {{ width: 70px; }} /* ID */
        .syft-jobs-table th:nth-child(8), .syft-jobs-table td:nth-child(8) {{ width: 100px; }} /* Actions */

        .syft-job-name {{
            font-weight: 600;
            color: #111827;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            display: block;
        }}
        .syft-job-desc {{
            color: #6b7280;
            font-size: 12px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            display: block;
            margin-top: 2px;
        }}
        .syft-job-email {{
            color: #3b82f6;
            font-size: 12px;
            font-weight: 500;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            display: block;
        }}
        .syft-job-id {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 11px;
            color: #6b7280;
        }}
        .syft-job-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 2px;
            overflow: hidden;
        }}
        .syft-job-tag {{
            background-color: #f3f4f6;
            color: #374151;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 500;
            white-space: nowrap;
        }}

        /* Responsive design for narrow screens */
        @media (max-width: 1200px) {{
            .syft-jobs-table th:nth-child(6), .syft-jobs-table td:nth-child(6) {{ display: none; }} /* Hide Tags */
        }}
        @media (max-width: 1000px) {{
            .syft-jobs-table th:nth-child(7), .syft-jobs-table td:nth-child(7) {{ display: none; }} /* Hide ID */
            .syft-job-desc {{ display: none; }} /* Hide description */
        }}
        @media (max-width: 800px) {{
            .syft-jobs-table th:nth-child(5), .syft-jobs-table td:nth-child(5) {{ display: none; }} /* Hide To */
            .syft-jobs-table th:nth-child(4), .syft-jobs-table td:nth-child(4) {{ width: 25%; }} /* Expand From */
            .syft-jobs-table th:nth-child(2), .syft-jobs-table td:nth-child(2) {{ width: 40%; }} /* Expand Job Name */
        }}
        .syft-badge {{
            display: inline-flex;
            align-items: center;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 500;
            text-transform: capitalize;
        }}
        .syft-badge-pending {{
            border: 1px solid #fde047;
            background-color: #fefce8;
            color: #ca8a04;
        }}
        .syft-badge-approved {{
            border: 1px solid #6ee7b7;
            background-color: #ecfdf5;
            color: #047857;
        }}
        .syft-badge-running {{
            border: 1px solid #93c5fd;
            background-color: #eff6ff;
            color: #1d4ed8;
        }}
        .syft-badge-completed {{
            border: 1px solid #6ee7b7;
            background-color: #ecfdf5;
            color: #047857;
        }}
        .syft-badge-failed {{
            border: 1px solid #fca5a5;
            background-color: #fef2f2;
            color: #dc2626;
        }}
        .syft-badge-rejected {{
            border: 1px solid #fca5a5;
            background-color: #fef2f2;
            color: #dc2626;
        }}
        .syft-job-actions {{
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
        }}
        .syft-action-btn {{
            padding: 4px 8px;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            background: white;
            cursor: pointer;
            font-size: 11px;
            font-weight: 500;
            color: #374151;
            text-decoration: none;
        }}
        .syft-action-btn:hover {{
            background-color: #f3f4f6;
        }}
        .syft-action-btn.approve {{
            border-color: #10b981;
            color: #047857;
            background-color: #ecfdf5;
        }}
        .syft-action-btn.approve:hover {{
            background-color: #d1fae5;
        }}
        .syft-action-btn.reject {{
            border-color: #ef4444;
            color: #dc2626;
            background-color: #fef2f2;
        }}
        .syft-action-btn.reject:hover {{
            background-color: #fee2e2;
        }}
        .syft-status {{
            padding: 12px 20px;
            background-color: #f8fafc;
            font-size: 12px;
            color: #6b7280;
            border-top: 1px solid #e5e7eb;
        }}
        .syft-checkbox {{
            width: 16px;
            height: 16px;
        }}
        </style>

        <div class="syft-jobs-container" id="{container_id}">
            <div class="syft-jobs-header">
                <div class="syft-jobs-title">
                    🔧 {collection_type}
                    <span class="syft-jobs-count">{len(self)}</span>
                </div>
                <p class="syft-jobs-description">{collection_description}</p>
            </div>
            <div class="syft-jobs-controls">
                <input type="text" class="syft-search-box" placeholder="🔍 Search jobs..."
                       onkeyup="filterJobs('{container_id}')">
                <button class="syft-filter-btn active" onclick="filterByStatus('{container_id}', 'all')">All</button>
                <button class="syft-filter-btn" onclick="filterByStatus('{container_id}', 'pending')">Pending ({summary["by_status"].get("pending", 0)})</button>
                <button class="syft-filter-btn" onclick="filterByStatus('{container_id}', 'running')">Running ({summary["by_status"].get("running", 0)})</button>
                <button class="syft-filter-btn" onclick="filterByStatus('{container_id}', 'completed')">Completed ({summary["by_status"].get("completed", 0)})</button>
        """

        # Add batch approval buttons only if any jobs can be approved by the current user
        # (i.e., jobs submitted TO me that are pending, not jobs I submitted to others)
        current_user_email = None
        if self and hasattr(self[0], "_client") and self[0]._client:
            current_user_email = self[0]._client.syftbox_client.email

        can_approve_any = any(
            job.status == JobStatus.pending
            and job._client is not None
            and job.target_email == current_user_email
            for job in self
        )

        if can_approve_any:
            html_content += f"""
                <button class="syft-batch-btn" onclick="batchApprove('{container_id}')">Approve Selected</button>
                <button class="syft-batch-btn reject" onclick="batchReject('{container_id}')">Reject Selected</button>
            """

        html_content += """
            </div>
            <div class="syft-jobs-table-container">
                <table class="syft-jobs-table">
                    <thead>
                        <tr>
                            <th>☑</th>
                            <th>Job Name</th>
                            <th>Status</th>
                            <th>From</th>
                            <th>To</th>
                            <th>Tags</th>
                            <th>ID</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for i, job in enumerate(self):
            # Format creation time
            time_display = "unknown"
            try:
                diff = datetime.now() - job.created_at
                if diff.total_seconds() < 60:
                    time_display = "just now"
                elif diff.total_seconds() < 3600:
                    time_display = f"{int(diff.total_seconds() / 60)}m ago"
                elif diff.total_seconds() < 86400:
                    time_display = f"{int(diff.total_seconds() / 3600)}h ago"
                else:
                    time_display = f"{int(diff.total_seconds() / 86400)} days ago"
            except (TypeError, AttributeError):
                # Handle cases where created_at is None or invalid
                pass

            # Build tags with tooltip showing all tags
            tags_html = ""
            tags_title = ""
            if job.tags:
                tags_title = html.escape(", ".join(job.tags))
                for tag in job.tags[:2]:  # Show max 2 tags
                    tags_html += f'<span class="syft-job-tag">{html.escape(tag)}</span>'
                if len(job.tags) > 2:
                    tags_html += f'<span class="syft-job-tag">+{len(job.tags) - 2}</span>'

            # Build action buttons - pass index and collection type
            # Determine if this job can be approved by current user
            can_approve_job = (
                job.status == JobStatus.pending
                and job._client is not None
                and job.target_email == current_user_email
            )

            actions_html = ""
            if can_approve_job:
                # Jobs I can approve (submitted TO me)
                actions_html = f"""
                    <button class="syft-action-btn approve" onclick="approveJobByUid('{job.uid}')">✓</button>
                    <button class="syft-action-btn reject" onclick="rejectJobByUid('{job.uid}')">✗</button>
                    <button class="syft-action-btn" onclick="reviewJobByUid('{job.uid}')">👁️</button>
                """
            elif job.status == JobStatus.pending and job._client is not None:
                # Jobs I submitted to others (pending their approval) - only review
                actions_html = f"""
                    <button class="syft-action-btn" onclick="reviewJobByUid('{job.uid}')">👁️</button>
                """
            elif (
                job.status in (JobStatus.running, JobStatus.completed, JobStatus.failed)
                and job._client is not None
            ):
                # Completed/running jobs - logs and output
                actions_html = f"""
                    <button class="syft-action-btn" onclick="viewLogsByUid('{job.uid}')">📜</button>
                    <button class="syft-action-btn" onclick="viewOutputByUid('{job.uid}')">📁</button>
                """

            html_content += f"""
                        <tr data-status="{job.status.value}" data-name="{html.escape(job.name.lower())}"
                            data-email="{html.escape(job.requester_email.lower())}" data-index="{i}" data-job-uid="{job.uid}">
                            <td>
                                <input type="checkbox" class="syft-checkbox" onchange="updateSelection('{container_id}')">
                            </td>
                            <td>
                                <div class="syft-job-name" title="{html.escape(job.name)}">{html.escape(job.name)}</div>
                                <div class="syft-job-desc" title="{html.escape(job.description or "")}">{html.escape(job.description or "No description")}</div>
                                <div style="font-size: 11px; color: #9ca3af; margin-top: 2px;">{time_display}</div>
                            </td>
                            <td>
                                <span class="syft-badge syft-badge-{job.status.value}">{job.status.value}</span>
                            </td>
                            <td>
                                <div class="syft-job-email" title="{html.escape(job.requester_email)}">{html.escape(job.requester_email)}</div>
                            </td>
                            <td>
                                <div class="syft-job-email" title="{html.escape(job.target_email)}">{html.escape(job.target_email)}</div>
                            </td>
                            <td>
                                <div class="syft-job-tags" title="{tags_title}">{tags_html}</div>
                            </td>
                            <td>
                                <div class="syft-job-id">{job.short_id}</div>
                            </td>
                            <td>
                                <div class="syft-job-actions">{actions_html}</div>
                            </td>
                        </tr>
            """

        html_content += f"""
                    </tbody>
                </table>
            </div>
            <div class="syft-status" id="{container_id}-status">
                0 jobs selected • {len(self)} total
            </div>
        </div>

        <script>
        function filterJobs(containerId) {{
            const searchBox = document.querySelector(`#${{containerId}} .syft-search-box`);
            const table = document.querySelector(`#${{containerId}} .syft-jobs-table tbody`);
            const rows = table.querySelectorAll('tr');
            const searchTerm = searchBox.value.toLowerCase();

            let visibleCount = 0;
            rows.forEach(row => {{
                const name = row.dataset.name || '';
                const email = row.dataset.email || '';
                const isVisible = name.includes(searchTerm) || email.includes(searchTerm);
                row.style.display = isVisible ? '' : 'none';
                if (isVisible) visibleCount++;
            }});

            updateSelection(containerId);
        }}

        function filterByStatus(containerId, status) {{
            const buttons = document.querySelectorAll(`#${{containerId}} .syft-filter-btn`);
            const table = document.querySelector(`#${{containerId}} .syft-jobs-table tbody`);
            const rows = table.querySelectorAll('tr');

            // Update active button
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            let visibleCount = 0;
            rows.forEach(row => {{
                const jobStatus = row.dataset.status;
                const isVisible = status === 'all' || jobStatus === status;
                row.style.display = isVisible ? '' : 'none';
                if (isVisible) visibleCount++;
            }});

            updateSelection(containerId);
        }}

        function updateSelection(containerId) {{
            const table = document.querySelector(`#${{containerId}} .syft-jobs-table tbody`);
            const rows = table.querySelectorAll('tr');
            const status = document.querySelector(`#${{containerId}}-status`);

            let selectedCount = 0;
            let visibleCount = 0;
            rows.forEach(row => {{
                const checkbox = row.querySelector('input[type="checkbox"]');
                if (row.style.display !== 'none') {{
                    visibleCount++;
                    if (checkbox && checkbox.checked) {{
                        row.classList.add('syft-selected');
                        selectedCount++;
                    }} else {{
                        row.classList.remove('syft-selected');
                    }}
                }}
            }});

            status.textContent = `${{selectedCount}} job(s) selected • ${{visibleCount}} visible`;
        }}

                 function batchApprove(containerId) {{
             // Get selected job UIDs
             const table = document.querySelector(`#${{containerId}} .syft-jobs-table tbody`);
             const rows = table.querySelectorAll('tr');
             const selectedUids = [];

             rows.forEach((row, index) => {{
                 const checkbox = row.querySelector('input[type="checkbox"]');
                 if (checkbox && checkbox.checked && row.style.display !== 'none') {{
                     const jobUid = row.getAttribute('data-job-uid'); if (jobUid) {{ selectedUids.push(jobUid); }}
                 }}
             }});

             if (selectedUids.length === 0) {{
                 alert('Please select jobs to approve first.');
                 return;
             }}

             const reason = prompt(`Approval reason for ${{selectedUids.length}} selected job(s):`, "Batch approved via Jupyter interface");
             if (reason !== null) {{
                 let code = 'import syft_code_queue as q\\n';
                 code += 'approved_count = 0\\n';
                 selectedUids.forEach(uid => {{
                     code += `job = q.get_job("${{uid}}")\n`;
                     code += `if job and job.approve("${{reason.replace(/"/g, '\"')}}"):  \n`;
                     code += `        approved_count += 1\\n`;
                 }});
                 code += 'print(f"✅ Approved {{approved_count}} job(s)")';

                 navigator.clipboard.writeText(code).then(() => {{
                     const button = document.querySelector(`#${{containerId}} button[onclick="batchApprove('${{containerId}}')"]`);
                     if (button) {{
                         const originalText = button.textContent;
                         button.textContent = '✅ Copied!';
                         button.style.backgroundColor = '#059669';
                         setTimeout(() => {{
                             button.textContent = originalText;
                             button.style.backgroundColor = '#10b981';
                         }}, 2000);
                     }}
                 }}).catch(err => {{
                     console.error('Could not copy code to clipboard:', err);
                     alert('Failed to copy to clipboard. Please copy manually:\\n\\n' + code);
                 }});
             }}
         }}

                 function batchReject(containerId) {{
             // Get selected job UIDs
             const table = document.querySelector(`#${{containerId}} .syft-jobs-table tbody`);
             const rows = table.querySelectorAll('tr');
             const selectedUids = [];

             rows.forEach((row, index) => {{
                 const checkbox = row.querySelector('input[type="checkbox"]');
                 if (checkbox && checkbox.checked && row.style.display !== 'none') {{
                     const jobUid = row.getAttribute('data-job-uid'); if (jobUid) {{ selectedUids.push(jobUid); }}
                 }}
             }});

             if (selectedUids.length === 0) {{
                 alert('Please select jobs to reject first.');
                 return;
             }}

             const reason = prompt(`Rejection reason for ${{selectedUids.length}} selected job(s):`, "Batch rejected via Jupyter interface");
             if (reason !== null && reason.trim() !== "") {{
                 let code = 'import syft_code_queue as q\\n';
                 code += 'rejected_count = 0\\n';
                 selectedUids.forEach(uid => {{
                     code += `job = q.get_job("${{uid}}")\n`;
                     code += `if job and job.reject("${{reason.replace(/"/g, '\"')}}"):  \n`;
                     code += `        rejected_count += 1\\n`;
                 }});
                 code += 'print(f"🚫 Rejected {{rejected_count}} job(s)")';

                 navigator.clipboard.writeText(code).then(() => {{
                     const button = document.querySelector(`#${{containerId}} button[onclick="batchReject('${{containerId}}')"]`);
                     if (button) {{
                         const originalText = button.textContent;
                         button.textContent = '🚫 Copied!';
                         button.style.backgroundColor = '#b91c1c';
                         setTimeout(() => {{
                             button.textContent = originalText;
                             button.style.backgroundColor = '#ef4444';
                         }}, 2000);
                     }}
                 }}).catch(err => {{
                     console.error('Could not copy code to clipboard:', err);
                     alert('Failed to copy to clipboard. Please copy manually:\\n\\n' + code);
                 }});
             }}
         }}

                 // Simple index-based job actions
         window.reviewJob = function(index, collection) {{
             var code = 'from IPython.display import display\\n' +
                        'import syft_code_queue as q\\n' +
                        'display(q.' + collection + '[' + index + '].review())';

             navigator.clipboard.writeText(code).then(() => {{
                 var buttons = document.querySelectorAll(`button[onclick="reviewJob(${{index}}, '${{collection}}')"]`);
                 buttons.forEach(button => {{
                     var originalText = button.innerHTML;
                     button.innerHTML = '📋 Copied!';
                     button.style.backgroundColor = '#059669';
                     setTimeout(() => {{
                         button.innerHTML = originalText;
                         button.style.backgroundColor = '';
                     }}, 2000);
                 }});
             }}).catch(err => {{
                 console.error('Could not copy code to clipboard:', err);
                 alert('Failed to copy to clipboard. Please copy manually:\\n\\n' + code);
             }});
         }};

                 window.approveJob = function(index, collection) {{
             var reason = prompt("Approval reason (optional):", "Approved via Jupyter interface");
             if (reason !== null) {{
                 var code = `q.${{collection}}[${{index}}].approve("${{reason.replace(/"/g, '\\"')}}")`;

                 navigator.clipboard.writeText(code).then(() => {{
                     var buttons = document.querySelectorAll(`button[onclick="approveJob(${{index}}, '${{collection}}')"]`);
                     buttons.forEach(button => {{
                         var originalText = button.innerHTML;
                         button.innerHTML = '✅ Copied!';
                         button.style.backgroundColor = '#059669';
                         setTimeout(() => {{
                             button.innerHTML = originalText;
                             button.style.backgroundColor = '';
                         }}, 2000);
                     }});
                 }}).catch(err => {{
                     console.error('Could not copy code to clipboard:', err);
                     alert('Failed to copy to clipboard. Please copy manually:\\n\\n' + code);
                 }});
             }}
         }};

                 window.rejectJob = function(index, collection) {{
             var reason = prompt("Rejection reason:", "");
             if (reason !== null && reason.trim() !== "") {{
                 var code = `q.${{collection}}[${{index}}].reject("${{reason.replace(/"/g, '\\"')}}")`;

                 navigator.clipboard.writeText(code).then(() => {{
                     var buttons = document.querySelectorAll(`button[onclick="rejectJob(${{index}}, '${{collection}}')"]`);
                     buttons.forEach(button => {{
                         var originalText = button.innerHTML;
                         button.innerHTML = '🚫 Copied!';
                         button.style.backgroundColor = '#dc2626';
                         setTimeout(() => {{
                             button.innerHTML = originalText;
                             button.style.backgroundColor = '';
                         }}, 2000);
                     }});
                 }}).catch(err => {{
                     console.error('Could not copy code to clipboard:', err);
                     alert('Failed to copy to clipboard. Please copy manually:\\n\\n' + code);
                 }});
             }}
         }};

                 window.viewLogs = function(index, collection) {{
             var code = `q.${{collection}}[${{index}}].get_logs()`;

             navigator.clipboard.writeText(code).then(() => {{
                 var buttons = document.querySelectorAll(`button[onclick="viewLogs(${{index}}, '${{collection}}')"]`);
                 buttons.forEach(button => {{
                     var originalText = button.innerHTML;
                     button.innerHTML = '📜 Copied!';
                     button.style.backgroundColor = '#6366f1';
                     setTimeout(() => {{
                         button.innerHTML = originalText;
                         button.style.backgroundColor = '';
                     }}, 2000);
                 }});
             }}).catch(err => {{
                 console.error('Could not copy code to clipboard:', err);
                 alert('Failed to copy to clipboard. Please copy manually:\\n\\n' + code);
             }});
         }};

        window.viewOutput = function(index, collection) {{
            var code = `q.${{collection}}[${{index}}].get_output()`;

            navigator.clipboard.writeText(code).then(() => {{
                var buttons = document.querySelectorAll(`button[onclick="viewOutput(${{index}}, '${{collection}}')"]`);
                buttons.forEach(button => {{
                    var originalText = button.innerHTML;
                    button.innerHTML = '📁 Copied!';
                    button.style.backgroundColor = '#8b5cf6';
                    setTimeout(() => {{
                        button.innerHTML = originalText;
                        button.style.backgroundColor = '';
                    }}, 2000);
                }});
            }}).catch(err => {{
                console.error('Could not copy code to clipboard:', err);
                alert('Failed to copy to clipboard. Please copy manually:\\n\\n' + code);
            }});
        }};


        // UID-based functions for individual row buttons
        window.approveJobByUid = function(jobUid) {{
            var reason = prompt("Approval reason (optional):", "Approved via Jupyter interface");
            if (reason !== null) {{
                var code = `q.get_job("${{jobUid}}").approve("${{reason.replace(/"/g, '\\\\"')}}")`;

                navigator.clipboard.writeText(code).then(() => {{
                    var buttons = document.querySelectorAll(`button[onclick="approveJobByUid('${{jobUid}}')"]`);
                    buttons.forEach(button => {{
                        var originalText = button.innerHTML;
                        button.innerHTML = '✅ Copied!';
                        button.style.backgroundColor = '#059669';
                        setTimeout(() => {{
                            button.innerHTML = originalText;
                            button.style.backgroundColor = '';
                        }}, 2000);
                    }});
                }}).catch(err => {{
                    console.error('Could not copy code to clipboard:', err);
                    alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
                }});
            }}
        }};

        window.rejectJobByUid = function(jobUid) {{
            var reason = prompt("Rejection reason:", "");
            if (reason !== null && reason.trim() !== "") {{
                var code = `q.get_job("${{jobUid}}").reject("${{reason.replace(/"/g, '\\\\"')}}")`;

                navigator.clipboard.writeText(code).then(() => {{
                    var buttons = document.querySelectorAll(`button[onclick="rejectJobByUid('${{jobUid}}')"]`);
                    buttons.forEach(button => {{
                        var originalText = button.innerHTML;
                        button.innerHTML = '🚫 Copied!';
                        button.style.backgroundColor = '#dc2626';
                        setTimeout(() => {{
                            button.innerHTML = originalText;
                            button.style.backgroundColor = '';
                        }}, 2000);
                    }});
                }}).catch(err => {{
                    console.error('Could not copy code to clipboard:', err);
                    alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
                }});
            }}
        }};

        window.reviewJobByUid = function(jobUid) {{
            var code = `q.get_job("${{jobUid}}").review()`;

            navigator.clipboard.writeText(code).then(() => {{
                var buttons = document.querySelectorAll(`button[onclick="reviewJobByUid('${{jobUid}}')"]`);
                buttons.forEach(button => {{
                    var originalText = button.innerHTML;
                    button.innerHTML = '📋 Copied!';
                    button.style.backgroundColor = '#059669';
                    setTimeout(() => {{
                        button.innerHTML = originalText;
                        button.style.backgroundColor = '';
                    }}, 2000);
                }});
            }}).catch(err => {{
                console.error('Could not copy code to clipboard:', err);
                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
            }});
        }};

        window.viewLogsByUid = function(jobUid) {{
            var code = `q.get_job("${{jobUid}}").get_logs()`;

            navigator.clipboard.writeText(code).then(() => {{
                var buttons = document.querySelectorAll(`button[onclick="viewLogsByUid('${{jobUid}}')"]`);
                buttons.forEach(button => {{
                    var originalText = button.innerHTML;
                    button.innerHTML = '📜 Copied!';
                    button.style.backgroundColor = '#6366f1';
                    setTimeout(() => {{
                        button.innerHTML = originalText;
                        button.style.backgroundColor = '';
                    }}, 2000);
                }});
            }}).catch(err => {{
                console.error('Could not copy code to clipboard:', err);
                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
            }});
        }};

        window.viewOutputByUid = function(jobUid) {{
            var code = `q.get_job("${{jobUid}}").get_output()`;

            navigator.clipboard.writeText(code).then(() => {{
                var buttons = document.querySelectorAll(`button[onclick="viewOutputByUid('${{jobUid}}')"]`);
                buttons.forEach(button => {{
                    var originalText = button.innerHTML;
                    button.innerHTML = '📁 Copied!';
                    button.style.backgroundColor = '#8b5cf6';
                    setTimeout(() => {{
                        button.innerHTML = originalText;
                        button.style.backgroundColor = '';
                    }}, 2000);
                }});
            }}).catch(err => {{
                console.error('Could not copy code to clipboard:', err);
                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
            }});
        }};
        """

        # Add unique timestamp to prevent Jupyter caching
        import time

        timestamp = str(int(time.time() * 1000))
        collection_id = hash(str([job.uid for job in self])) % 10000

        # Add unique comment to force Jupyter to treat this as new content
        return f"<!-- refresh-{timestamp}-collection-{collection_id} -->\n{html_content}"

    def __repr__(self) -> str:
        if not self:
            return "JobCollection([])"

        summary = self.summary()
        status_str = ", ".join([f"{k}: {v}" for k, v in summary["by_status"].items() if v > 0])
        return f"JobCollection({len(self)} jobs - {status_str})"


class JobCreate(BaseModel):
    """Request to create a new code job."""

    name: str
    target_email: str
    code_folder: Path
    description: Optional[str] = None
    timeout_seconds: int = Field(default=86400)  # 24 hours default
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


class FilesystemReviewWidget:
    """Interactive filesystem widget for code review in Jupyter."""

    def __init__(self, job: "CodeJob"):
        self.job = job

    def _repr_html_(self):
        """Return HTML for Jupyter display."""
        # Always regenerate HTML to ensure fresh content for each job
        # Add unique timestamp to prevent Jupyter caching
        import time

        timestamp = str(int(time.time() * 1000))
        html = self._create_filesystem_ui()
        # Add unique comment to force Jupyter to treat this as new content
        return f"<!-- refresh-{timestamp}-{self.job.uid} -->\n{html}"

    def _create_filesystem_ui(self):
        """Create the interactive filesystem UI."""
        import html

        # Get file list
        try:
            files = self.job.list_files()
        except Exception as e:
            return f"""
            <div style="padding: 20px; color: #dc3545; border: 1px solid #dc3545; border-radius: 8px; background: #f8d7da;">
                <h3>❌ Unable to load files</h3>
                <p>Error: {html.escape(str(e))}</p>
            </div>
            """

        if not files:
            return """
            <div style="padding: 20px; color: #6c757d; border: 1px solid #dee2e6; border-radius: 8px; background: #f8f9fa;">
                <h3>📁 No files found</h3>
                <p>This job appears to have no files to review.</p>
            </div>
            """

        # Sort files - executables first, then alphabetically
        def sort_key(filename):
            is_executable = filename in ["run.sh", "run.py", "run.bash"]
            return (not is_executable, filename.lower())

        sorted_files = sorted(files, key=sort_key)

        # Build file list HTML
        files_html = ""
        for i, filename in enumerate(sorted_files):
            icon = self._get_file_type(filename)
            is_executable = filename in ["run.sh", "run.py", "run.bash"]
            file_class = "file-executable" if is_executable else "file-regular"

            files_html += f"""
                <div class="file-item {file_class}" onclick="loadFileReview('{filename}')" data-filename="{filename}">
                    <span class="file-icon">{icon}</span>
                    <span class="file-name">{html.escape(filename)}</span>
                </div>
            """

        # Pre-load all file contents for the JavaScript
        file_contents = {}
        for filename in sorted_files:
            try:
                content = self.job.read_file(filename)
                if content:
                    file_contents[filename] = content
                else:
                    file_contents[filename] = "❌ Could not read file content"
            except Exception as e:
                file_contents[filename] = f"❌ Error reading file: {str(e)}"

        # Get first file content for initial display
        first_file = sorted_files[0] if sorted_files else None
        initial_content = ""
        if first_file and first_file in file_contents:
            initial_content = html.escape(file_contents[first_file])

        # Convert file contents to JavaScript object
        import json

        file_contents_js = json.dumps(file_contents)

        return f"""
        <div class="filesystem-review-container">
            <style>
            .filesystem-review-container {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                border: 1px solid #e1e5e9;
                border-radius: 12px;
                overflow: hidden;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 16px 0;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }}

            .review-header {{
                padding: 20px 24px;
                color: white;
                background: rgba(255,255,255,0.2);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(255,255,255,0.2);
            }}

            .review-title {{
                font-size: 20px;
                font-weight: 700;
                margin: 0 0 8px 0;
                display: flex;
                align-items: center;
                gap: 12px;
            }}

            .review-meta {{
                font-size: 14px;
                opacity: 0.9;
                display: flex;
                align-items: center;
                gap: 16px;
                margin: 8px 0 0 0;
            }}

            .review-content {{
                display: flex;
                height: 500px;
                background: white;
            }}

            .file-list {{
                width: 280px;
                border-right: 1px solid #e1e5e9;
                background: #f8fafc;
                overflow-y: auto;
            }}

            .file-list-header {{
                padding: 16px;
                background: #f1f5f9;
                border-bottom: 1px solid #e1e5e9;
                font-weight: 600;
                color: #475569;
                font-size: 14px;
            }}

            .file-item {{
                padding: 12px 16px;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 12px;
                border-bottom: 1px solid #f1f5f9;
                transition: all 0.2s ease;
            }}

            .file-item:hover {{
                background: #e2e8f0;
            }}

            .file-item.active {{
                background: #3b82f6;
                color: white;
            }}

            .file-item.file-executable {{
                background: linear-gradient(90deg, #fef3c7, #fef3c7);
                border-left: 4px solid #f59e0b;
            }}

            .file-item.file-executable:hover {{
                background: linear-gradient(90deg, #fde68a, #fde68a);
            }}

            .file-item.file-executable.active {{
                background: #f59e0b;
                color: white;
            }}

            .file-icon {{
                font-size: 16px;
                min-width: 20px;
            }}

            .file-name {{
                font-size: 14px;
                font-weight: 500;
            }}

            .content-viewer {{
                flex: 1;
                display: flex;
                flex-direction: column;
            }}

            .content-header {{
                padding: 16px 20px;
                background: #f8fafc;
                border-bottom: 1px solid #e1e5e9;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}

            .content-title {{
                font-weight: 600;
                color: #1e293b;
                font-size: 14px;
            }}

            .content-meta {{
                font-size: 12px;
                color: #64748b;
            }}

            .content-body {{
                flex: 1;
                overflow: auto;
                padding: 0;
            }}

            .content-code {{
                padding: 20px;
                font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.6;
                white-space: pre-wrap;
                margin: 0;
                background: #ffffff;
                color: #1e293b;
                border: none;
                min-height: 100%;
            }}

            .action-buttons {{
                padding: 16px 20px;
                background: #f8fafc;
                border-top: 1px solid #e1e5e9;
                display: flex;
                gap: 12px;
                justify-content: center;
            }}

            .action-btn {{
                padding: 10px 20px;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                font-size: 14px;
                display: flex;
                align-items: center;
                gap: 8px;
            }}

            .action-btn.approve {{
                background: linear-gradient(135deg, #10b981, #059669);
                color: white;
            }}

            .action-btn.approve:hover {{
                background: linear-gradient(135deg, #059669, #047857);
                transform: translateY(-1px);
            }}

            .action-btn.reject {{
                background: linear-gradient(135deg, #ef4444, #dc2626);
                color: white;
            }}

            .action-btn.reject:hover {{
                background: linear-gradient(135deg, #dc2626, #b91c1c);
                transform: translateY(-1px);
            }}

            .loading {{
                padding: 40px;
                text-align: center;
                color: #64748b;
            }}
            </style>

            <div class="review-header">
                <div class="review-title">
                    🔍 Code Review: {html.escape(self.job.name)}
                    <span style="background: rgba(255,255,255,0.2); padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 500;">{len(files)} files</span>
                </div>
                <div class="review-meta">
                    📧 {html.escape(self.job.requester_email)} → {html.escape(self.job.target_email)}
                    • 🏷️ {", ".join(self.job.tags) if self.job.tags else "No tags"}
                </div>
            </div>

            <div class="review-content">
                <div class="file-list">
                    <div class="file-list-header">📁 Files ({len(files)})</div>
                    {files_html}
                </div>

                <div class="content-viewer">
                    <div class="content-header">
                        <div class="content-title" id="current-file">{html.escape(first_file) if first_file else "No file selected"}</div>
                        <div class="content-meta" id="file-meta"></div>
                    </div>
                    <div class="content-body">
                        <pre class="content-code" id="file-content">{initial_content}</pre>
                    </div>
                </div>
            </div>

            <div class="action-buttons">
                {self._get_action_buttons_html()}
            </div>
        </div>

        <script>
        let currentJobUid = '{self.job.uid}';
        let jobFiles = {sorted_files};
        let fileContents = {file_contents_js};

        function loadFileReview(filename) {{
            console.log('loadFileReview called with filename:', filename);
            console.log('fileContents object:', fileContents);
            console.log('Available keys:', Object.keys(fileContents));

            // Update active file styling
            document.querySelectorAll('.file-item').forEach(item => {{
                item.classList.remove('active');
            }});
            document.querySelector(`[data-filename="${{filename}}"]`).classList.add('active');

            // Update header
            document.getElementById('current-file').textContent = filename;

            // Get file content from pre-loaded data
            let content = fileContents[filename];
            console.log('Content for', filename, ':', content);
            console.log('Content exists:', !!content);
            console.log('Content type:', typeof content);

            if (content) {{
                // Display the actual file content
                document.getElementById('file-content').textContent = content;

                // Update metadata
                let lines = content.split('\\n').length;
                let chars = content.length;
                document.getElementById('file-meta').textContent = `${{lines}} lines • ${{chars}} characters`;
                console.log('Successfully loaded content for', filename);
            }} else {{
                document.getElementById('file-content').textContent = 'File content not available.';
                document.getElementById('file-meta').textContent = 'Content not loaded';
                console.log('ERROR: No content found for', filename);
            }}
        }}

        function approveJobReview(jobUid) {{
            let reason = prompt('Approval reason (optional):', 'Code review completed - approved');
            if (reason !== null) {{
                let code = `
# Approve job after review
job = q.get_job('${{jobUid}}')
if job:
    success = job.approve('` + reason.replace(/'/g, "\\'") + `')
    if success:
        print('✅ Job approved successfully!')
        print('Job: ' + job.name)
        print('Reason: ` + reason + `')
    else:
        print('❌ Failed to approve job')
else:
    print('❌ Job not found')`;

                navigator.clipboard.writeText(code.trim()).then(() => {{
                    alert('✅ Approval code copied to clipboard!\\n\\nPaste and run in a new cell to approve the job.');
                }}).catch(() => {{
                    alert('Approval code:\\n\\n' + code.trim());
                }});
            }}
        }}

        function rejectJobReview(jobUid) {{
            let reason = prompt('Rejection reason:', '');
            if (reason !== null && reason.trim() !== '') {{
                let code = `
# Reject job after review
job = q.get_job('${{jobUid}}')
if job:
    success = job.reject('` + reason.replace(/'/g, "\\'") + `')
    if success:
        print('🚫 Job rejected')
        print('Job: ' + job.name)
        print('Reason: ` + reason + `')
    else:
        print('❌ Failed to reject job')
else:
    print('❌ Job not found')`;

                navigator.clipboard.writeText(code.trim()).then(() => {{
                    alert('🚫 Rejection code copied to clipboard!\\n\\nPaste and run in a new cell to reject the job.');
                }}).catch(() => {{
                    alert('Rejection code:\\n\\n' + code.trim());
                }});
            }}
        }}

        // Initialize first file as active
        console.log('Initializing filesystem review widget');
        console.log('jobFiles:', jobFiles);
        console.log('fileContents keys:', Object.keys(fileContents));
        console.log('fileContents values lengths:', Object.keys(fileContents).map(k => k + ': ' + fileContents[k].length + ' chars'));

        if (jobFiles.length > 0) {{
            let firstFile = jobFiles[0];
            console.log('Setting first file as active:', firstFile);
            document.querySelector(`[data-filename="${{firstFile}}"]`).classList.add('active');

            // Show metadata for the first file
            let firstContent = fileContents[firstFile];
            if (firstContent) {{
                let lines = firstContent.split('\\n').length;
                let chars = firstContent.length;
                document.getElementById('file-meta').textContent = `${{lines}} lines • ${{chars}} characters`;
                console.log('First file metadata set:', lines, 'lines,', chars, 'chars');
            }} else {{
                console.log('ERROR: No content for first file:', firstFile);
            }}
        }} else {{
            console.log('ERROR: No files to initialize');
        }}
        </script>
        """

    def _get_action_buttons_html(self) -> str:
        """Get HTML for action buttons based on user permissions."""
        # Check if current user can approve this job
        current_user_email = None
        if self.job._client:
            current_user_email = self.job._client.syftbox_client.email

        can_approve = (
            self.job.status == JobStatus.pending
            and self.job._client is not None
            and self.job.target_email == current_user_email
        )

        if can_approve:
            # User can approve - show approve/reject buttons
            return f"""
                <button class="action-btn approve" onclick="approveJobReview('{self.job.uid}')">
                    ✅ Approve Job
                </button>
                <button class="action-btn reject" onclick="rejectJobReview('{self.job.uid}')">
                    🚫 Reject Job
                </button>
            """
        else:
            # User cannot approve - show info message
            if self.job.status != JobStatus.pending:
                status_msg = f"Job status: {self.job.status.value}"
            else:
                status_msg = "Awaiting approval from job recipient"

            return f"""
                <div style="text-align: center; padding: 16px; color: #64748b; font-style: italic;">
                    📋 Review only • {status_msg}
                </div>
            """

    def _get_file_type(self, filename: str) -> str:
        """Get emoji icon for file type."""
        if filename.endswith(".py"):
            return "🐍"
        elif filename.endswith((".sh", ".bash")):
            return "💻"
        elif filename.endswith((".txt", ".md")):
            return "📝"
        elif filename.endswith((".yml", ".yaml")):
            return "⚙️"
        elif filename.endswith(".json"):
            return "📋"
        elif filename.endswith((".csv", ".tsv")):
            return "📊"
        elif filename in ["requirements.txt", "pyproject.toml", "setup.py"]:
            return "📦"
        elif filename in ["Dockerfile", "docker-compose.yml"]:
            return "🐳"
        elif filename.startswith("run."):
            return "🚀"
        else:
            return "📄"


class OutputViewerWidget:
    """Interactive output filesystem widget for viewing job results in Jupyter."""

    def __init__(self, job: "CodeJob"):
        self.job = job

    def _repr_html_(self):
        """Return HTML for Jupyter display."""
        # Always regenerate HTML to ensure fresh content for each job
        # Add unique timestamp to prevent Jupyter caching
        import time

        timestamp = str(int(time.time() * 1000))
        html = self._create_output_ui()
        # Add unique comment to force Jupyter to treat this as new content
        return f"<!-- refresh-{timestamp}-{self.job.uid} -->\n{html}"

    def _create_output_ui(self):
        """Create the interactive output filesystem UI."""
        import html

        # Check if job has output folder
        if not self.job.output_folder:
            return f"""
            <div style="padding: 20px; color: #6c757d; border: 1px solid #dee2e6; border-radius: 8px; background: #f8f9fa;">
                <h3>📁 No Output Available</h3>
                <p>This job doesn't have an output folder configured yet.</p>
                <p><strong>Job Status:</strong> {self.job.status.value}</p>
            </div>
            """

        # Get file list
        try:
            files = self.job.list_output_files()
        except Exception as e:
            return f"""
            <div style="padding: 20px; color: #dc3545; border: 1px solid #dc3545; border-radius: 8px; background: #f8d7da;">
                <h3>❌ Unable to load output files</h3>
                <p>Error: {html.escape(str(e))}</p>
                <p><strong>Output Path:</strong> {html.escape(str(self.job.output_folder))}</p>
            </div>
            """

        if not files:
            return f"""
            <div style="padding: 20px; color: #6c757d; border: 1px solid #dee2e6; border-radius: 8px; background: #f8f9fa;">
                <h3>📁 No Output Files Found</h3>
                <p>The job output directory exists but contains no files.</p>
                <p><strong>Output Path:</strong> {html.escape(str(self.job.output_folder))}</p>
                <p><strong>Job Status:</strong> {self.job.status.value}</p>
            </div>
            """

        # Sort files alphabetically
        sorted_files = sorted(files)

        # Build file list HTML
        files_html = ""
        for filename in sorted_files:
            icon = self._get_file_type(filename)
            files_html += f"""
                <div class="file-item" onclick="loadOutputFile('{filename}')" data-filename="{filename}">
                    <span class="file-icon">{icon}</span>
                    <span class="file-name">{html.escape(filename)}</span>
                </div>
            """

        # Pre-load all file contents for the JavaScript
        file_contents = {}
        for filename in sorted_files:
            try:
                content = self.job.read_output_file(filename)
                if content:
                    file_contents[filename] = content
                else:
                    file_contents[filename] = "❌ Could not read file content"
            except Exception as e:
                file_contents[filename] = f"❌ Error reading file: {str(e)}"

        # Get first file content for initial display
        first_file = sorted_files[0] if sorted_files else None
        initial_content = ""
        if first_file and first_file in file_contents:
            initial_content = html.escape(file_contents[first_file])

        # Convert file contents to JavaScript object
        import json

        file_contents_js = json.dumps(file_contents)

        return f"""
        <div class="output-viewer-container">
            <style>
            .output-viewer-container {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                border: 1px solid #e1e5e9;
                border-radius: 12px;
                overflow: hidden;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 16px 0;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }}

            .output-header {{
                padding: 20px 24px;
                color: white;
                background: rgba(255,255,255,0.2);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(255,255,255,0.2);
            }}

            .output-title {{
                font-size: 20px;
                font-weight: 700;
                margin: 0 0 8px 0;
                display: flex;
                align-items: center;
                gap: 12px;
            }}

            .output-meta {{
                font-size: 14px;
                opacity: 0.9;
                display: flex;
                align-items: center;
                gap: 16px;
                margin: 8px 0 0 0;
            }}

            .output-content {{
                display: flex;
                height: 500px;
                background: white;
            }}

            .file-list {{
                width: 280px;
                border-right: 1px solid #e1e5e9;
                background: #f8fafc;
                overflow-y: auto;
            }}

            .file-list-header {{
                padding: 16px;
                background: #f1f5f9;
                border-bottom: 1px solid #e1e5e9;
                font-weight: 600;
                color: #475569;
                font-size: 14px;
            }}

            .file-item {{
                padding: 12px 16px;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 12px;
                border-bottom: 1px solid #f1f5f9;
                transition: all 0.2s ease;
            }}

            .file-item:hover {{
                background: #e2e8f0;
            }}

            .file-item.active {{
                background: #3b82f6;
                color: white;
            }}

            .file-icon {{
                font-size: 16px;
                min-width: 20px;
            }}

            .file-name {{
                font-size: 14px;
                font-weight: 500;
            }}

            .content-viewer {{
                flex: 1;
                display: flex;
                flex-direction: column;
            }}

            .content-header {{
                padding: 16px 20px;
                background: #f8fafc;
                border-bottom: 1px solid #e1e5e9;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}

            .content-title {{
                font-weight: 600;
                color: #1e293b;
                font-size: 14px;
            }}

            .content-meta {{
                font-size: 12px;
                color: #64748b;
            }}

            .content-body {{
                flex: 1;
                overflow: auto;
                padding: 0;
            }}

            .content-code {{
                padding: 20px;
                font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.6;
                white-space: pre-wrap;
                margin: 0;
                background: #ffffff;
                color: #1e293b;
                border: none;
                min-height: 100%;
            }}
            </style>

            <div class="output-header">
                <div class="output-title">
                    📁 Job Output: {html.escape(self.job.name)}
                    <span style="background: rgba(255,255,255,0.2); padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 500;">{len(files)} files</span>
                </div>
                <div class="output-meta">
                    📂 {html.escape(str(self.job.output_folder))}
                    • Status: {self.job.status.value}
                </div>
            </div>

            <div class="output-content">
                <div class="file-list">
                    <div class="file-list-header">📄 Output Files ({len(files)})</div>
                    {files_html}
                </div>

                <div class="content-viewer">
                    <div class="content-header">
                        <div class="content-title" id="current-output-file">{html.escape(first_file) if first_file else "No file selected"}</div>
                        <div class="content-meta" id="output-file-meta"></div>
                    </div>
                    <div class="content-body">
                        <pre class="content-code" id="output-file-content">{initial_content}</pre>
                    </div>
                </div>
            </div>
        </div>

        <script>
        let outputJobUid = '{self.job.uid}';
        let outputFiles = {json.dumps(sorted_files)};
        let outputFileContents = {file_contents_js};

        function loadOutputFile(filename) {{
            console.log('loadOutputFile called with filename:', filename);

            // Update active file styling
            document.querySelectorAll('.file-item').forEach(item => {{
                item.classList.remove('active');
            }});
            document.querySelector(`[data-filename="${{filename}}"]`).classList.add('active');

            // Update header
            document.getElementById('current-output-file').textContent = filename;

            // Get file content from pre-loaded data
            let content = outputFileContents[filename];

            if (content) {{
                // Display the actual file content
                document.getElementById('output-file-content').textContent = content;

                // Update metadata
                let lines = content.split('\\n').length;
                let chars = content.length;
                document.getElementById('output-file-meta').textContent = `${{lines}} lines • ${{chars}} characters`;
            }} else {{
                document.getElementById('output-file-content').textContent = 'File content not available.';
                document.getElementById('output-file-meta').textContent = 'Content not loaded';
            }}
        }}

        // Initialize first file as active
        if (outputFiles.length > 0) {{
            let firstFile = outputFiles[0];
            document.querySelector(`[data-filename="${{firstFile}}"]`).classList.add('active');

            // Show metadata for the first file
            let firstContent = outputFileContents[firstFile];
            if (firstContent) {{
                let lines = firstContent.split('\\n').length;
                let chars = firstContent.length;
                document.getElementById('output-file-meta').textContent = `${{lines}} lines • ${{chars}} characters`;
            }}
        }}
        </script>
        """

    def _get_file_type(self, filename: str) -> str:
        """Get emoji icon for file type."""
        if filename.endswith(".py"):
            return "🐍"
        elif filename.endswith((".sh", ".bash")):
            return "💻"
        elif filename.endswith((".txt", ".md")):
            return "📝"
        elif filename.endswith((".yml", ".yaml")):
            return "⚙️"
        elif filename.endswith(".json"):
            return "📋"
        elif filename.endswith((".csv", ".tsv")):
            return "📊"
        elif filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
            return "🖼️"
        elif filename.endswith(".pdf"):
            return "📄"
        elif filename.endswith(".log"):
            return "📜"
        elif filename.endswith((".html", ".htm")):
            return "🌐"
        elif filename.endswith(".xml"):
            return "📋"
        elif filename.startswith("output"):
            return "📤"
        elif filename.startswith("result"):
            return "🎯"
        else:
            return "📄"


class DataSitesCollection:
    """Collection of datasites that have open syft-code-queues."""

    def __init__(self, syftbox_client=None):
        """Initialize the datasites collection."""
        self.syftbox_client = syftbox_client
        self._override_data = None  # Used for filtered collections

    def _get_current_data(self):
        """Get current datasites data - either overridden (for filtered) or fresh from filesystem."""
        if self._override_data is not None:
            return self._override_data
        return self._load_datasites()

    def _load_datasites(self):
        """Load all datasites with open code queues. Returns fresh data every time."""
        from loguru import logger
        
        datasites = []
        
        if not self.syftbox_client:
            logger.warning("No SyftBox client available - cannot scan for datasites")
            return datasites

        try:
            datasites_dir = self.syftbox_client.datasites
            if not datasites_dir.exists():
                logger.warning(f"Datasites directory does not exist: {datasites_dir}")
                return datasites

            logger.debug(f"Scanning for datasites with code queues in: {datasites_dir}")

            # Iterate through all datasites
            for datasite_dir in datasites_dir.iterdir():
                if not datasite_dir.is_dir():
                    continue
                
                # Check if it's a valid email-like datasite
                if "@" not in datasite_dir.name:
                    continue

                try:
                    # Check if this datasite has a code-queue app
                    queue_dir = datasite_dir / "app_data" / "code-queue" / "jobs"
                    if not queue_dir.exists():
                        continue

                    # Count jobs in different statuses, deduplicating by UID
                    # Pipeline order: pending -> approved/rejected/timedout -> running -> completed/failed
                    pipeline_order = ["pending", "approved", "rejected", "timedout", "running", "completed", "failed"]
                    
                    # Collect all job UIDs and their statuses
                    job_uids_by_status = {}
                    all_job_uids = {}  # uid -> latest_status_in_pipeline
                    
                    for status in JobStatus:
                        status_dir = queue_dir / status.value
                        if status_dir.exists():
                            job_dirs = [d for d in status_dir.iterdir() if d.is_dir()]
                            job_uids_by_status[status.value] = set(d.name for d in job_dirs)
                            
                            # Track the latest status for each UID
                            for job_dir in job_dirs:
                                uid = job_dir.name
                                current_status_index = pipeline_order.index(status.value)
                                
                                if uid not in all_job_uids:
                                    all_job_uids[uid] = status.value
                                else:
                                    # Keep the status that's furthest in the pipeline
                                    existing_status_index = pipeline_order.index(all_job_uids[uid])
                                    if current_status_index > existing_status_index:
                                        all_job_uids[uid] = status.value
                        else:
                            job_uids_by_status[status.value] = set()
                    
                    # Count deduplicated jobs by their actual (latest) status
                    status_counts = {}
                    for status in JobStatus:
                        status_counts[status.value] = 0
                    
                    for uid, actual_status in all_job_uids.items():
                        status_counts[actual_status] += 1
                    
                    total_jobs = len(all_job_uids)

                    # Check if pending directory has proper permissions for code queue
                    pending_dir = queue_dir / "pending"
                    has_permissions = pending_dir.exists() and (pending_dir / "syft.pub.yaml").exists()

                    # Analyze responsiveness history
                    responsiveness_info = self._analyze_responsiveness(queue_dir)

                    datasite_info = {
                        "email": datasite_dir.name,
                        "queue_path": queue_dir,
                        "total_jobs": total_jobs,
                        "status_counts": status_counts,
                        "has_permissions": has_permissions,
                        "responsiveness": responsiveness_info["category"],
                        "responded_to_me": responsiveness_info["responded_to_me"],
                        "responded_to_others": responsiveness_info["responded_to_others"],
                        "total_responses": responsiveness_info["total_responses"],
                        "last_response_to_me": responsiveness_info["last_response_to_me"],
                        "last_activity": self._get_last_activity(queue_dir)
                    }
                    
                    datasites.append(datasite_info)
                    logger.debug(f"Found datasite with code queue: {datasite_dir.name}")

                except Exception as e:
                    logger.debug(f"Error scanning datasite {datasite_dir.name}: {e}")
                    continue

            # Sort by default: last response to me (most recent first), then by email
            datasites.sort(key=lambda x: (
                # Put datasites that responded to me first, then others
                0 if x["last_response_to_me"] else 1,
                # Within each group, sort by last response time (most recent first)
                -(x["last_response_to_me"].timestamp() if x["last_response_to_me"] else 0),
                # Then by email as tiebreaker
                x["email"]
            ))
            return datasites

        except Exception as e:
            logger.error(f"Error scanning for datasites: {e}")
            return datasites

    def _get_last_activity(self, queue_dir):
        """Get the last activity timestamp for a queue directory.
        
        Only considers jobs that have been processed (approved, running, completed, failed, rejected).
        Pending and timedout jobs don't count as activity since they represent lack of action.
        """
        try:
            latest_time = None
            # Only look at statuses that represent actual activity/processing
            # Note: "timedout" is excluded as it represents lack of activity, not activity
            active_statuses = ["approved", "running", "completed", "failed", "rejected"]
            
            for status_name in active_statuses:
                status_dir = queue_dir / status_name
                if status_dir.exists() and status_dir.is_dir():
                    for job_dir in status_dir.iterdir():
                        if job_dir.is_dir():
                            try:
                                metadata_file = job_dir / "metadata.json"
                                if metadata_file.exists():
                                    mtime = metadata_file.stat().st_mtime
                                    if latest_time is None or mtime > latest_time:
                                        latest_time = mtime
                            except:
                                continue
            
            if latest_time:
                from datetime import datetime
                return datetime.fromtimestamp(latest_time)
            return None
        except:
            return None

    def _analyze_responsiveness(self, queue_dir):
        """Analyze if this datasite has responded to job requests and to whom."""
        try:
            # Get current user's email
            current_user_email = None
            if self.syftbox_client:
                current_user_email = self.syftbox_client.email
            
            # Statuses that indicate the datasite owner responded/took action
            # Note: "timedout" is excluded as it represents lack of response, not a response
            response_statuses = ["approved", "rejected", "running", "completed", "failed"]
            
            responded_to_me = False
            responded_to_others = False
            total_responses = 0
            last_response_to_me = None
            
            for status_name in response_statuses:
                status_dir = queue_dir / status_name
                if not status_dir.exists():
                    continue
                    
                for job_dir in status_dir.iterdir():
                    if not job_dir.is_dir():
                        continue
                        
                    try:
                        metadata_file = job_dir / "metadata.json"
                        if not metadata_file.exists():
                            continue
                            
                        import json
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            
                        requester_email = metadata.get("requester_email")
                        if not requester_email:
                            continue
                            
                        total_responses += 1
                        
                        # Get the timestamp of this response
                        response_time = metadata_file.stat().st_mtime
                        
                        if current_user_email and requester_email == current_user_email:
                            responded_to_me = True
                            # Track the most recent response to me
                            if last_response_to_me is None or response_time > last_response_to_me:
                                last_response_to_me = response_time
                        else:
                            responded_to_others = True
                            
                    except Exception as e:
                        # Skip problematic job metadata
                        continue
            
            # Determine category
            if responded_to_me:
                category = "responsive_to_me"
            elif responded_to_others:
                category = "responsive_to_others"
            else:
                category = "unresponsive"
            
            # Convert timestamp to datetime
            last_response_to_me_dt = None
            if last_response_to_me:
                from datetime import datetime
                last_response_to_me_dt = datetime.fromtimestamp(last_response_to_me)
                
            return {
                "category": category,
                "responded_to_me": responded_to_me,
                "responded_to_others": responded_to_others,
                "total_responses": total_responses,
                "last_response_to_me": last_response_to_me_dt
            }
            
        except Exception as e:
            # Default to unresponsive if we can't determine
            return {
                "category": "unresponsive",
                "responded_to_me": False,
                "responded_to_others": False,
                "total_responses": 0,
                "last_response_to_me": None
            }

    def refresh(self):
        """Refresh is not needed since datasites collection is always fresh from filesystem."""
        return self

    @property
    def responsive_to_me(self):
        """Filter to datasites that have responded to my job requests before."""
        datasites = self._load_datasites()
        responsive_datasites = [ds for ds in datasites if ds["responsiveness"] == "responsive_to_me"]
        collection = DataSitesCollection(self.syftbox_client)
        collection._override_data = responsive_datasites
        return collection
    
    @property
    def responsive(self):
        """Filter to datasites that have responded to anyone's job requests."""
        datasites = self._load_datasites()
        responsive_datasites = [ds for ds in datasites if ds["responsiveness"] in ["responsive_to_me", "responsive_to_others"]]
        collection = DataSitesCollection(self.syftbox_client)
        collection._override_data = responsive_datasites
        return collection

    @property
    def with_pending_jobs(self):
        """Filter to datasites with pending jobs."""
        datasites = self._load_datasites()
        pending_datasites = [ds for ds in datasites if ds["status_counts"]["pending"] > 0]
        collection = DataSitesCollection(self.syftbox_client)
        collection._override_data = pending_datasites
        return collection

    def sort_by(self, column: str, reverse: bool = False):
        """
        Sort datasites by any column.
        
        Args:
            column: Column name to sort by. Available columns:
                   'email', 'total_jobs', 'pending', 'running', 'completed', 'failed',
                   'timedout', 'responsiveness', 'last_response_to_me', 'last_activity'
            reverse: True for descending order, False for ascending
            
        Returns:
            New sorted DataSitesCollection
        """
        datasites = self._get_current_data()
        
        def get_sort_key(ds):
            if column == 'email':
                return ds['email']
            elif column == 'total_jobs':
                return ds['total_jobs']
            elif column == 'pending':
                return ds['status_counts']['pending']
            elif column == 'running':
                return ds['status_counts']['running']
            elif column == 'completed':
                return ds['status_counts']['completed']
            elif column == 'failed':
                return ds['status_counts']['failed']
            elif column == 'timedout':
                return ds['status_counts']['timedout']
            elif column == 'responsiveness':
                # Sort order: responsive_to_me, responsive_to_others, unresponsive
                order = {'responsive_to_me': 1, 'responsive_to_others': 2, 'unresponsive': 3}
                return order.get(ds['responsiveness'], 4)
            elif column == 'last_response_to_me':
                # Handle None values - put them at the end
                if ds['last_response_to_me'] is None:
                    return 0 if reverse else float('inf')
                return ds['last_response_to_me'].timestamp()
            elif column == 'last_activity':
                # Handle None values - put them at the end
                if ds['last_activity'] is None:
                    return 0 if reverse else float('inf')
                return ds['last_activity'].timestamp()
            else:
                raise ValueError(f"Unknown column: {column}. Available columns: email, total_jobs, pending, running, completed, failed, timedout, responsiveness, last_response_to_me, last_activity")
        
        try:
            sorted_datasites = sorted(datasites, key=get_sort_key, reverse=reverse)
            collection = DataSitesCollection(self.syftbox_client)
            collection._override_data = sorted_datasites
            return collection
        except Exception as e:
            from loguru import logger
            logger.warning(f"Error sorting by column '{column}': {e}")
            return self

    def ping(self, timeout_minutes: float = 0.5, include_self: bool = False, block: bool = False) -> dict:
        """
        Send ping jobs to all datasites in this collection.
        
        Args:
            timeout_minutes: How long the ping jobs should remain valid (default 0.5 minutes = 30 seconds)
            include_self: Whether to send a ping job to yourself (default False)
            block: If True, wait for responses and show a live status bar (default False)
                - Shows a carriage-return based (and pretty) status bar for how long it takes datasites to reply
                - At the end, prints a summary of which datasites responded and which did not
        Returns:
            dict: Summary of ping results with 'sent_to', 'failed_to_send', 'jobs', and (if block=True) 'responses'
        """
        if not self.syftbox_client:
            return {
                "sent_to": [],
                "failed_to_send": [],
                "jobs": [],
                "error": "No SyftBox client available"
            }
        
        from .client import CodeQueueClient
        from . import QueueConfig
        import time
        import sys
        config = QueueConfig()
        client = CodeQueueClient(self.syftbox_client, config)
        ping_script = '''import os
with open(os.getenv("OUTPUT_DIR")+"/ping.txt", "w") as file:
    file.write("This is a ping to see if you're alive and receiving jobs from me.")
'''
        timeout_seconds = int(timeout_minutes * 60)
        sent_to = []
        failed_to_send = []
        ping_jobs = []
        datasites_info = self._get_current_data()
        current_user_email = self.syftbox_client.email
        from loguru import logger
        logger.info(f"Pinging {len(datasites_info)} datasites from collection")
        for datasite_info in datasites_info:
            target_email = datasite_info["email"]
            if target_email == current_user_email and not include_self:
                logger.debug(f"Skipping ping to self: {target_email} (set include_self=True to ping yourself)")
                continue
            try:
                job = client.create_python_job(
                    target_email=target_email,
                    script_content=ping_script,
                    name=f'Ping from {current_user_email}',
                    description='Network connectivity test - checking if you can receive jobs from me.',
                    timeout_seconds=timeout_seconds,
                    tags=['ping', 'network-test']
                )
                sent_to.append(target_email)
                ping_jobs.append(job)
                logger.info(f"Sent ping to {target_email} (job {job.short_id})")
            except Exception as e:
                failed_to_send.append({"email": target_email, "error": str(e)})
                logger.warning(f"Failed to send ping to {target_email}: {e}")
        summary = {
            "sent_to": sent_to,
            "failed_to_send": failed_to_send,
            "jobs": ping_jobs,
            "timeout_minutes": timeout_minutes,
            "collection_size": len(datasites_info)
        }
        if not block:
            logger.info(f"Ping summary: sent to {len(sent_to)} datasites, failed to send to {len(failed_to_send)}")
            return summary
        # --- Blocking mode: poll for responses and show status bar ---
        job_map = {job.target_email: job for job in ping_jobs}
        responded = set()
        pending = set(sent_to)
        failed = set(x["email"] for x in failed_to_send)
        start_time = time.time()
        poll_interval = 1.0
        def get_status():
            nonlocal responded, pending
            for email, job in job_map.items():
                job.refresh()
                if job.status in (job.status.completed, job.status.failed):
                    responded.add(email)
            pending = set(sent_to) - responded
        def print_status_bar(elapsed, responded, pending, total, responded_list, pending_list):
            bar_len = 30
            done = int(bar_len * len(responded) / total) if total else 0
            bar = "█" * done + "-" * (bar_len - done)
            resp_str = ','.join(responded_list)
            pend_str = ','.join(pending_list)
            sys.stdout.write(f"\r[Ping] [{bar}] {len(responded)}/{total} responded, {len(pending)} pending | {int(elapsed)}s | responded: [{resp_str}] | pending: [{pend_str}]   ")
            sys.stdout.flush()
        while time.time() - start_time < timeout_seconds and pending:
            get_status()
            print_status_bar(
                time.time() - start_time,
                responded,
                pending,
                len(sent_to),
                sorted(responded),
                sorted(pending),
            )
            time.sleep(poll_interval)
        get_status()
        print_status_bar(
            time.time() - start_time,
            responded,
            pending,
            len(sent_to),
            sorted(responded),
            sorted(pending),
        )
        print()
        # Final summary
        print("\nPing Results:")
        for email in sent_to:
            if email in responded:
                print(f"  ✅ {email} responded")
            else:
                print(f"  ❌ {email} did NOT respond in time")
        if failed:
            print("\nFailed to send ping to:")
            for email in failed:
                print(f"  ⚠️  {email}")
        summary["responded"] = list(responded)
        summary["pending"] = list(pending)
        summary["failed"] = list(failed)
        summary["elapsed_seconds"] = int(time.time() - start_time)
        return summary

    def __len__(self):
        return len(self._get_current_data())

    def __iter__(self):
        return iter(self._get_current_data())

    def __getitem__(self, index):
        current_data = self._get_current_data()
        if isinstance(index, slice):
            collection = DataSitesCollection(self.syftbox_client)
            collection._override_data = current_data[index]
            return collection
        return current_data[index]

    def to_list(self):
        """Convert to a simple list of datasite info."""
        return list(self._get_current_data())

    def __str__(self):
        """Display datasites as a nice table."""
        datasites = self._get_current_data()
        
        if not datasites:
            return "No datasites with code queues found"

        try:
            from tabulate import tabulate
            table_data = []
            
            for i, datasite in enumerate(datasites):
                email = datasite["email"]
                total = datasite["total_jobs"]
                pending = datasite["status_counts"]["pending"]
                running = datasite["status_counts"]["running"]
                completed = datasite["status_counts"]["completed"]
                # Determine status display based on responsiveness
                if datasite["responsiveness"] == "responsive_to_me":
                    status = "🟢 Responsive to Me"
                elif datasite["responsiveness"] == "responsive_to_others":
                    status = "🟡 Responsive to Others" 
                else:
                    status = "🔴 Unresponsive"
                
                # Format last activity
                last_activity = datasite["last_activity"]
                if last_activity:
                    from datetime import datetime, timedelta
                    diff = datetime.now() - last_activity
                    if diff.days > 0:
                        activity_str = f"{diff.days}d ago"
                    elif diff.seconds > 3600:
                        activity_str = f"{diff.seconds // 3600}h ago"
                    else:
                        activity_str = f"{diff.seconds // 60}m ago"
                else:
                    activity_str = "Never"

                # Format last response to me
                last_response_to_me = datasite["last_response_to_me"]
                if last_response_to_me:
                    from datetime import datetime, timedelta
                    diff = datetime.now() - last_response_to_me
                    if diff.days > 0:
                        response_to_me_str = f"{diff.days}d ago"
                    elif diff.seconds > 3600:
                        response_to_me_str = f"{diff.seconds // 3600}h ago"
                    else:
                        response_to_me_str = f"{diff.seconds // 60}m ago"
                else:
                    response_to_me_str = "Never"

                table_data.append([
                    i, email, status, total, pending, running, completed, activity_str, response_to_me_str
                ])

            headers = ["#", "Email", "Responsiveness", "Total", "Pending", "Running", "Completed", "Last Activity", "Last Response to Me"]
            return tabulate(table_data, headers=headers, tablefmt="grid")
            
        except ImportError:
            lines = ["Available DataSites with Code Queues:"]
            for i, datasite in enumerate(datasites):
                email = datasite["email"]
                total = datasite["total_jobs"]
                pending = datasite["status_counts"]["pending"]
                # Determine status for text display
                if datasite["responsiveness"] == "responsive_to_me":
                    status = "Responsive to Me"
                elif datasite["responsiveness"] == "responsive_to_others":
                    status = "Responsive to Others"
                else:
                    status = "Unresponsive"
                lines.append(f"{i}: {email} ({status}) - {total} total jobs, {pending} pending")
            return "\n".join(lines)

    def __repr__(self):
        return self.__str__()

    def _repr_html_(self):
        """Return HTML representation for Jupyter notebooks."""
        datasites = self._get_current_data()
        
        if not datasites:
            return """
            <div style="padding: 20px; border: 2px solid #ddd; border-radius: 8px; background-color: #f9f9f9;">
                <h3 style="color: #666; margin-top: 0;">📡 DataSites with Code Queues</h3>
                <p style="color: #888;">No datasites with code queues found</p>
            </div>
            """

        # List of all job statuses
        status_names = [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("rejected", "Rejected"),
            ("timedout", "Timed Out"),
        ]

        # Determine current sort column (if any)
        # For now, just default to 'last_response_to_me' (could be improved with JS in the future)
        current_sort = getattr(self, '_last_sort_column', 'last_response_to_me')
        current_sort_reverse = getattr(self, '_last_sort_reverse', True)
        sort_indicator = lambda col: (" &#9650;" if current_sort == col and not current_sort_reverse else (" &#9660;" if current_sort == col and current_sort_reverse else ""))

        # Create HTML table
        html = """
        <div style="padding: 20px; border: 2px solid #ddd; border-radius: 8px; background-color: #f9f9f9;">
            <h3 style="color: #333; margin-top: 0;">📡 DataSites with Code Queues</h3>
            <div style="overflow-x: auto; margin-top: 10px;">
                <table id="datasites-table" style="min-width: 1200px; border-collapse: collapse; width: 100%;">
                    <thead>
                        <tr style="background-color: #e9e9e9;">
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: left; min-width: 30px;">#</th>
                            <th class="sortable" data-sort="email" style="padding: 8px; border: 1px solid #ddd; text-align: left; min-width: 200px; cursor: pointer;">Email{email_sort}</th>
                            <th class="sortable" data-sort="responsiveness" style="padding: 8px; border: 1px solid #ddd; text-align: left; min-width: 140px; cursor: pointer;">Responsiveness{resp_sort}</th>
                            <th class="sortable" data-sort="total_jobs" style="padding: 8px; border: 1px solid #ddd; text-align: center; min-width: 50px; cursor: pointer;">Total{total_sort}</th>
        """.format(
            email_sort=sort_indicator('email'),
            resp_sort=sort_indicator('responsiveness'),
            total_sort=sort_indicator('total_jobs'),
        )
        for status_key, status_label in status_names:
            html += f'<th class="sortable" data-sort="{status_key}" style="padding: 8px; border: 1px solid #ddd; text-align: center; min-width: 60px; cursor: pointer;">{status_label}{sort_indicator(status_key)}</th>'
        html += """
                            <th class="sortable" data-sort="last_activity" style="padding: 8px; border: 1px solid #ddd; text-align: center; min-width: 100px; cursor: pointer;">Last Activity{activity_sort}</th>
                            <th class="sortable" data-sort="last_response_to_me" style="padding: 8px; border: 1px solid #ddd; text-align: center; min-width: 120px; cursor: pointer;">Last Response to Me{lastresp_sort}</th>
                        </tr>
                    </thead>
                    <tbody>
        """.format(
            activity_sort=sort_indicator('last_activity'),
            lastresp_sort=sort_indicator('last_response_to_me'),
        )

        for i, datasite in enumerate(datasites):
            email = datasite["email"]
            total = datasite["total_jobs"]
            status_counts = datasite["status_counts"]
            # Status with color coding based on responsiveness
            if datasite["responsiveness"] == "responsive_to_me":
                status_badge = '<span style="color: #28a745; font-weight: bold;">🟢 Responsive to Me</span>'
            elif datasite["responsiveness"] == "responsive_to_others":
                status_badge = '<span style="color: #ffc107; font-weight: bold;">🟡 Responsive to Others</span>'
            else:
                status_badge = '<span style="color: #dc3545; font-weight: bold;">🔴 Unresponsive</span>'
            # Format last activity
            last_activity = datasite["last_activity"]
            if last_activity:
                from datetime import datetime, timedelta
                diff = datetime.now() - last_activity
                if diff.days > 0:
                    activity_str = f"{diff.days}d ago"
                elif diff.seconds > 3600:
                    activity_str = f"{diff.seconds // 3600}h ago"
                else:
                    activity_str = f"{diff.seconds // 60}m ago"
            else:
                activity_str = "Never"
            # Format last response to me
            last_response_to_me = datasite["last_response_to_me"]
            if last_response_to_me:
                from datetime import datetime, timedelta
                diff = datetime.now() - last_response_to_me
                if diff.days > 0:
                    response_to_me_str = f"{diff.days}d ago"
                elif diff.seconds > 3600:
                    response_to_me_str = f"{diff.seconds // 3600}h ago"
                else:
                    response_to_me_str = f"{diff.seconds // 60}m ago"
            else:
                response_to_me_str = "Never"
            row_color = "#fff" if i % 2 == 0 else "#f8f9fa"
            html += f"""
                <tr style="background-color: {row_color};">
                    <td style="padding: 8px; border: 1px solid #ddd;">{i}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; font-family: monospace; word-break: break-all;">{email}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{status_badge}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{total}</td>
            """
            for status_key, _ in status_names:
                count = status_counts.get(status_key, 0)
                color = ''
                if status_key == 'pending' and count > 0:
                    color = 'color: #dc3545; font-weight: bold;'
                elif status_key == 'running' and count > 0:
                    color = 'color: #007bff; font-weight: bold;'
                elif status_key == 'completed' and count > 0:
                    color = 'color: #28a745; font-weight: bold;'
                elif status_key == 'failed' and count > 0:
                    color = 'color: #b71c1c; font-weight: bold;'
                elif status_key == 'rejected' and count > 0:
                    color = 'color: #ff9800; font-weight: bold;'
                elif status_key == 'timedout' and count > 0:
                    color = 'color: #888; font-weight: bold;'
                html += f'<td style="padding: 8px; border: 1px solid #ddd; text-align: center; {color}">{count}</td>'
            html += f"""
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: center; font-size: 0.9em; color: #666;">{activity_str}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: center; font-size: 0.9em; color: #666;">{response_to_me_str}</td>
                </tr>
            """
        html += """
                </tbody>
            </table>
            </div>
            <div style="margin-top: 15px; padding: 10px; background-color: #e3f2fd; border-radius: 4px;">
                <small style="color: #1976d2;">
                                         <strong>💡 Usage:</strong> 
                    <code>q.datasites.responsive_to_me()</code> • 
                    <code>q.datasites.responsive()</code> • 
                    <code>q.datasites.with_pending_jobs()</code> • 
                    <b>Click any column header to sort (coming soon)</b>
                </small>
            </div>
        </div>
        """
        return html

    def help(self):
        """Show help for using the datasites collection."""
        help_text = """
📡 DataSites Collection Help

Available Methods:
        - q.datasites                        # Show all datasites with code queues (sorted by last response to me)
        - q.datasites.responsive_to_me()     # Show datasites that have responded to MY jobs
        - q.datasites.responsive()           # Show datasites that have responded to ANYONE's jobs
        - q.datasites.with_pending_jobs()    # Show datasites with pending jobs
        - q.datasites.sort_by('total_jobs')  # Sort by any column (email, total_jobs, pending, etc.)
        - q.datasites.sort_by('email', reverse=True)  # Sort in reverse order
        - q.datasites.ping()                 # Ping all datasites in this collection
        - q.datasites.responsive_to_me().ping()  # Ping only responsive datasites
        - q.datasites[0]                     # Get first datasite info
        - len(q.datasites)                   # Count of datasites

DataSite Info Structure:
- email: Email address of the datasite
- total_jobs: Total number of jobs in all statuses
- status_counts: Dict with counts for each job status
- has_permissions: Whether the datasite has proper queue permissions
- responsiveness: "responsive_to_me", "responsive_to_others", or "unresponsive"
- responded_to_me: Whether they've responded to my jobs before
- responded_to_others: Whether they've responded to someone else's jobs
- total_responses: Total number of jobs they've responded to
- last_response_to_me: Timestamp of last time they responded to MY jobs
- last_activity: Timestamp of last job activity

Responsiveness Categories:
🟢 Responsive to Me    - Has approved/rejected MY job requests before
🟡 Responsive to Others - Has responded to someone's jobs (but not mine)
🔴 Unresponsive        - Has never responded to anyone's job requests

Examples:
    # View all datasites
    q.datasites
    
    # Get datasites that have responded to me before (highest chance of response)
    trusted_sites = q.datasites.responsive_to_me()
    
    # Get any responsive datasites
    responsive_sites = q.datasites.responsive()
    
    # Check a specific datasite's responsiveness
    site_info = q.datasites[0]
    print(f"Email: {site_info['email']}")
    print(f"Responsiveness: {site_info['responsiveness']}")
    print(f"Has responded to me: {site_info['responded_to_me']}")
    print(f"Total responses: {site_info['total_responses']}")
"""
        print(help_text)
        return help_text
