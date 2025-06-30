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
    logs: Optional[str] = None  # Execution logs (stdout/stderr)

    # Metadata
    tags: list[str] = Field(default_factory=list)

    # Internal references (private attributes)
    _client: Optional["CodeQueueClient"] = PrivateAttr(default=None)
    _datasite_path: Optional[Path] = PrivateAttr(default=None)  # Track where this job is actually stored

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
            # Update local status immediately for better UX
            self.status = JobStatus.approved
            self.updated_at = datetime.now()
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
            # Update local status immediately for better UX
            self.status = JobStatus.rejected
            self.updated_at = datetime.now()
        return success

    def deny(self, reason: Optional[str] = None) -> bool:
        """Alias for reject."""
        return self.reject(reason)

    def review(self) -> Optional[dict]:
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
        # First try to return the logs field if it exists
        if self.logs is not None:
            return self.logs
            
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

    def review(self):
        """Show interactive filesystem UI for code review."""
        if self._client is None:
            raise RuntimeError("Job not connected to DataOwner API - cannot review")
        
        # Return the interactive filesystem widget
        return FilesystemReviewWidget(self)

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

        return f"""
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
                collection_type = "Jobs Awaiting Your Approval"
                collection_description = "Review and approve/reject these jobs"
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
        if self and hasattr(self[0], '_client') and self[0]._client:
            current_user_email = self[0]._client.syftbox_client.email
        
        can_approve_any = any(
            job.status == JobStatus.pending and 
            job._client is not None and
            job.target_email == current_user_email
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
                job.status == JobStatus.pending and 
                job._client is not None and
                job.target_email == current_user_email
            )
            
            collection_name = (
                "pending_for_me" if can_approve_job else "jobs_for_others"
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

        """

        return html_content

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
        self._html_content = None
    
    def _repr_html_(self):
        """Return HTML for Jupyter display."""
        if self._html_content is None:
            self._html_content = self._create_filesystem_ui()
        return self._html_content
    
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
            return f"""
            <div style="padding: 20px; color: #6c757d; border: 1px solid #dee2e6; border-radius: 8px; background: #f8f9fa;">
                <h3>📁 No files found</h3>
                <p>This job appears to have no files to review.</p>
            </div>
            """
        
        # Sort files - executables first, then alphabetically
        def sort_key(filename):
            is_executable = filename in ['run.sh', 'run.py', 'run.bash']
            return (not is_executable, filename.lower())
        
        sorted_files = sorted(files, key=sort_key)
        
        # Build file list HTML
        files_html = ""
        for i, filename in enumerate(sorted_files):
            icon = self._get_file_type(filename)
            is_executable = filename in ['run.sh', 'run.py', 'run.bash']
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
                    • 🏷️ {', '.join(self.job.tags) if self.job.tags else 'No tags'}
                </div>
            </div>
            
            <div class="review-content">
                <div class="file-list">
                    <div class="file-list-header">📁 Files ({len(files)})</div>
                    {files_html}
                </div>
                
                <div class="content-viewer">
                    <div class="content-header">
                        <div class="content-title" id="current-file">{html.escape(first_file) if first_file else 'No file selected'}</div>
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
            self.job.status == JobStatus.pending and
            self.job._client is not None and
            self.job.target_email == current_user_email
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
        if filename.endswith('.py'):
            return '🐍'
        elif filename.endswith(('.sh', '.bash')):
            return '💻'
        elif filename.endswith(('.txt', '.md')):
            return '📝'
        elif filename.endswith(('.yml', '.yaml')):
            return '⚙️'
        elif filename.endswith('.json'):
            return '📋'
        elif filename.endswith(('.csv', '.tsv')):
            return '📊'
        elif filename in ['requirements.txt', 'pyproject.toml', 'setup.py']:
            return '📦'
        elif filename in ['Dockerfile', 'docker-compose.yml']:
            return '🐳'
        elif filename.startswith('run.'):
            return '🚀'
        else:
            return '📄'
