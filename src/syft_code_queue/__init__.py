"""
syft-code-queue: Simple code execution queue for SyftBox.

This package provides a lightweight way to submit code for execution on remote datasites.
Code is submitted as folders containing a run.sh script, and executed by SyftBox apps.

Architecture:
- Code is submitted using the unified API
- Jobs are stored in SyftBox app data directories  
- SyftBox periodically calls run.sh which processes the queue
- No long-running server processes required

Usage:
    import syft_code_queue as q
    
    # Submit jobs to others
    job = q.submit_job("data-owner@university.edu", "./my_analysis", "Statistical Analysis")
    
    # Object-oriented job management
    q.jobs_for_me[0].approve("Looks safe")
    q.jobs_for_others[0].get_logs()
    q.jobs_for_me.pending().approve_all("Batch approval")
    
    # Functional API still available
    q.pending_for_me()
    q.approve("job-id", "reason")
"""

from pathlib import Path
from typing import List, Optional, Union
from uuid import UUID

from loguru import logger

from .client import CodeQueueClient, create_client
from .models import CodeJob, JobStatus, QueueConfig, JobCollection
# Runner components moved to syft-simple-runner package  
# App execution moved to syft-simple-runner package
from .data_owner_api import DataOwnerAPI
from .data_scientist_api import DataScientistAPI

try:
    from syft_core import Client as SyftBoxClient
except ImportError:
    logger.warning("syft_core not available - using mock client")
    class MockSyftBoxClient:
        def __init__(self):
            self.email = "demo@example.com"
        
        def app_data(self, app_name):
            import tempfile
            return Path(tempfile.gettempdir()) / f"syftbox_demo_{app_name}"
        
        @classmethod
        def load(cls):
            return cls()
    
    SyftBoxClient = MockSyftBoxClient


class UnifiedAPI:
    """
    Unified API for syft-code-queue that handles both job submission and management.
    
    This provides both object-oriented and functional interfaces:
    - Object-oriented: q.jobs_for_me[0].approve("reason")
    - Functional: q.approve("job-id", "reason")
    """
    
    def __init__(self, config: Optional[QueueConfig] = None):
        """Initialize the unified API."""
        try:
            self.syftbox_client = SyftBoxClient.load()
            self.config = config or QueueConfig(queue_name="code-queue")
            self.client = CodeQueueClient(syftbox_client=self.syftbox_client, config=self.config)
            self._ds_api = DataScientistAPI(config=self.config)
            self._do_api = DataOwnerAPI(config=self.config)
            
            logger.info(f"Initialized syft-code-queue API for {self.email}")
        except Exception as e:
            logger.warning(f"Could not initialize syft-code-queue: {e}")
            # Set up in demo mode
            self.syftbox_client = SyftBoxClient()
            self.config = config or QueueConfig(queue_name="code-queue")
            self.client = None
            self._ds_api = None
            self._do_api = None
    
    @property
    def email(self) -> str:
        """Get the current user's email."""
        return self.syftbox_client.email
    
    def _connect_job_apis(self, job: CodeJob) -> CodeJob:
        """Connect a job to the appropriate APIs for method calls."""
        job._ds_api = self._ds_api
        job._do_api = self._do_api
        return job
    
    def _connect_jobs_apis(self, jobs: List[CodeJob]) -> JobCollection:
        """Connect a list of jobs to the appropriate APIs."""
        connected_jobs = [self._connect_job_apis(job) for job in jobs]
        return JobCollection(connected_jobs)
    
    # Object-Oriented Properties
    
    @property
    def jobs_for_others(self) -> JobCollection:
        """Jobs I've submitted to other people."""
        if self._ds_api is None:
            return JobCollection([])
        jobs = self._ds_api.list_my_jobs(limit=100)
        return self._connect_jobs_apis(jobs)
    
    @property
    def jobs_for_me(self) -> JobCollection:
        """Jobs submitted to me for approval/management."""
        if self._do_api is None:
            return JobCollection([])
        jobs = self._do_api.list_all_jobs(limit=100)
        return self._connect_jobs_apis(jobs)
    
    @property
    def my_pending(self) -> JobCollection:
        """Jobs I've submitted that are still pending."""
        return self.jobs_for_others.by_status(JobStatus.pending)
    
    @property
    def my_running(self) -> JobCollection:
        """Jobs I've submitted that are currently running."""
        return self.jobs_for_others.by_status(JobStatus.running)
    
    @property
    def my_completed(self) -> JobCollection:
        """Jobs I've submitted that have completed."""
        return self.jobs_for_others.by_status(JobStatus.completed)
    
    @property
    def pending_for_me(self) -> JobCollection:
        """Jobs submitted to me that need approval."""
        # Filter out jobs that have been locally updated to non-pending status
        all_jobs_for_me = self.jobs_for_me
        pending_jobs = [job for job in all_jobs_for_me if job.status == JobStatus.pending]
        return JobCollection(pending_jobs)
    
    @property
    def approved_by_me(self) -> JobCollection:
        """Jobs I've approved that are running/completed."""
        approved = self.jobs_for_me.by_status(JobStatus.approved)
        running = self.jobs_for_me.by_status(JobStatus.running)
        completed = self.jobs_for_me.by_status(JobStatus.completed)
        all_approved = JobCollection(list(approved) + list(running) + list(completed))
        return all_approved
    
    # Job Submission (Data Scientist functionality)
    
    def submit_job(self, 
                   target_email: str,
                   code_folder: Union[str, Path],
                   name: str,
                   description: Optional[str] = None,
                   tags: Optional[List[str]] = None) -> CodeJob:
        """
        Submit a code package for execution on a remote datasite.
        
        Args:
            target_email: Email of the data owner/datasite
            code_folder: Path to folder containing code and run.sh script
            name: Human-readable name for the job
            description: Optional description of what the job does
            tags: Optional tags for categorization (e.g. ["privacy-safe", "aggregate"])
            
        Returns:
            CodeJob: The submitted job object with API methods attached
        """
        if self._ds_api is None:
            raise RuntimeError("API not properly initialized")
        job = self._ds_api.submit_job(target_email, code_folder, name, description, tags)
        return self._connect_job_apis(job)
    
    def submit_python(self,
                     target_email: str,
                     script_content: str,
                     name: str,
                     description: Optional[str] = None,
                     requirements: Optional[List[str]] = None,
                     tags: Optional[List[str]] = None) -> CodeJob:
        """
        Create and submit a Python job from script content.
        
        Args:
            target_email: Email of the data owner/datasite
            script_content: Python script content
            name: Human-readable name for the job
            description: Optional description
            requirements: Optional list of Python packages to install
            tags: Optional tags for categorization
            
        Returns:
            CodeJob: The submitted job object with API methods attached
        """
        if self._ds_api is None:
            raise RuntimeError("API not properly initialized")
        job = self._ds_api.create_python_job(target_email, script_content, name, description, requirements, tags)
        return self._connect_job_apis(job)
    
    def submit_bash(self,
                   target_email: str,
                   script_content: str,
                   name: str,
                   description: Optional[str] = None,
                   tags: Optional[List[str]] = None) -> CodeJob:
        """
        Create and submit a bash job from script content.
        
        Args:
            target_email: Email of the data owner/datasite
            script_content: Bash script content
            name: Human-readable name for the job
            description: Optional description
            tags: Optional tags for categorization
            
        Returns:
            CodeJob: The submitted job object with API methods attached
        """
        if self._ds_api is None:
            raise RuntimeError("API not properly initialized")
        job = self._ds_api.create_bash_job(target_email, script_content, name, description, tags)
        return self._connect_job_apis(job)
    
    # Legacy Functional API (for backward compatibility)
    
    def my_jobs(self, status: Optional[JobStatus] = None, limit: int = 50) -> List[CodeJob]:
        """List jobs I've submitted to others (functional API)."""
        if status is None:
            return list(self.jobs_for_others[:limit])
        else:
            return list(self.jobs_for_others.by_status(status)[:limit])
    
    def get_job(self, job_uid: Union[str, UUID]) -> Optional[CodeJob]:
        """Get a specific job by its UID (functional API)."""
        if self._ds_api is None:
            return None
        job = self._ds_api.get_job(job_uid)
        return self._connect_job_apis(job) if job else None
    
    def get_job_output(self, job_uid: Union[str, UUID]) -> Optional[Path]:
        """Get the output directory for a completed job (functional API)."""
        if self._ds_api is None:
            return None
        return self._ds_api.get_job_output(job_uid)
    
    def get_job_logs(self, job_uid: Union[str, UUID]) -> Optional[str]:
        """Get the execution logs for a job (functional API)."""
        if self._ds_api is None:
            return None
        return self._ds_api.get_job_logs(job_uid)
    
    def wait_for_completion(self, job_uid: Union[str, UUID], timeout: int = 600) -> CodeJob:
        """Wait for a job to complete (functional API)."""
        if self._ds_api is None:
            raise RuntimeError("API not properly initialized")
        job = self._ds_api.wait_for_completion(job_uid, timeout)
        return self._connect_job_apis(job)
    
    # Legacy Job Management (Data Owner functionality)
    
    def all_jobs_for_me(self, status: Optional[JobStatus] = None, limit: int = 50) -> List[CodeJob]:
        """List all jobs submitted to me (functional API)."""
        if status is None:
            return list(self.jobs_for_me[:limit])
        else:
            return list(self.jobs_for_me.by_status(status)[:limit])
    
    def approve(self, job_uid: Union[str, UUID], reason: Optional[str] = None) -> bool:
        """Approve a job for execution (functional API)."""
        if self._do_api is None:
            return False
        return self._do_api.approve_job(job_uid, reason)
    
    def reject(self, job_uid: Union[str, UUID], reason: Optional[str] = None) -> bool:
        """Reject a job (functional API)."""
        if self._do_api is None:
            return False
        return self._do_api.reject_job(job_uid, reason)
    
    def review_job(self, job_uid: Union[str, UUID]) -> Optional[dict]:
        """Get detailed information about a job for review (functional API)."""
        if self._do_api is None:
            return None
        
        # Get the job and use its review method
        job = self._do_api.get_job(str(job_uid))
        if job is None:
            return None
        
        # Connect APIs and call review
        connected_job = self._connect_job_apis(job)
        return connected_job.review()
    
    # Status and Summary
    
    def status(self) -> dict:
        """Get overall status summary."""
        summary = {
            "email": self.email,
            "jobs_submitted_by_me": len(self.jobs_for_others),
            "jobs_submitted_to_me": len(self.jobs_for_me),
            "pending_for_approval": len(self.pending_for_me),
            "my_running_jobs": len(self.my_running)
        }
        return summary
    
    def refresh(self):
        """Refresh all job data to get latest statuses."""
        # Force refresh by invalidating any cached data
        # The properties will fetch fresh data on next access
        pass
    
    def help(self):
        """Show help and examples for using syft-code-queue."""
        help_text = """
🚀 Syft Code Queue Help

Import Convention:
  import syft_code_queue as q

Object-Oriented API (Recommended):
  # Submit jobs
  job = q.submit_job("data-owner@university.edu", "./my_analysis", "Statistical Analysis")
  job = q.submit_script("owner@email.com", "print('hello')", "Hello Test")
  
  # Access job collections
  q.jobs_for_others              # Jobs I've submitted to others
  q.jobs_for_me                  # Jobs submitted to me
  q.pending_for_me               # Jobs waiting for my approval
  q.my_pending                   # My jobs still pending approval
  q.my_running                   # My jobs currently running
  q.my_completed                 # My completed jobs
  
  # Work with individual jobs
  q.jobs_for_me[0].approve("Looks safe")
  q.jobs_for_me[0].reject("Too broad")
  q.jobs_for_others[0].get_logs()
  q.jobs_for_others[0].wait_for_completion()
  
  # Work with collections
  q.pending_for_me.approve_all("Batch approval")
  q.jobs_for_me.pending().approve_all("All look good")
  q.jobs_for_others.by_tags("statistics").summary()
  
  # Filter collections
  q.jobs_for_me.by_status(q.JobStatus.completed)
  q.jobs_for_others.by_name("analysis")
  q.jobs_for_me.pending()
  q.jobs_for_others.completed()

Functional API (Legacy):
  # Submit jobs
  job = q.submit_job("data-owner@university.edu", "./my_analysis", "Statistical Analysis")
  
  # Monitor your submitted jobs
  q.my_jobs()                    # All your jobs
  q.get_job("job-id")           # Specific job
  q.get_job_logs("job-id")      # Job logs
  q.wait_for_completion("job-id") # Wait for completion

  # Manage jobs submitted to you
  q.all_jobs_for_me()           # All jobs submitted to you
  q.approve("job-id", "Looks safe")  # Approve job
  q.reject("job-id", "Too broad")    # Reject job

General:
  q.status()                    # Overall status summary
  q.help()                      # This help message

Job Lifecycle:
  📤 submit → ⏳ pending → ✅ approved → 🏃 running → 🎉 completed
                       ↘ 🚫 rejected            ↘ ❌ failed
        """
        print(help_text)


# Create global instance
jobs = UnifiedAPI()

# Expose key functions at module level for convenience
submit_job = jobs.submit_job
submit_python = jobs.submit_python
submit_bash = jobs.submit_bash
my_jobs = jobs.my_jobs
get_job = jobs.get_job
get_job_output = jobs.get_job_output
get_job_logs = jobs.get_job_logs
wait_for_completion = jobs.wait_for_completion
all_jobs_for_me = jobs.all_jobs_for_me
approve = jobs.approve
reject = jobs.reject
review_job = jobs.review_job
status = jobs.status
help = jobs.help

# Override module attribute access to provide fresh data from backend
def __getattr__(name):
    """Module-level attribute access that always fetches fresh data."""
    if name == 'jobs_for_others':
        return jobs.jobs_for_others
    elif name == 'jobs_for_me':
        return jobs.jobs_for_me  
    elif name == 'pending_for_me':
        return jobs.pending_for_me
    elif name == 'my_pending':
        return jobs.my_pending
    elif name == 'my_running':
        return jobs.my_running
    elif name == 'my_completed':
        return jobs.my_completed
    elif name == 'approved_by_me':
        return jobs.approved_by_me
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__version__ = "0.1.0"
__all__ = [
    # Global unified API
    "jobs",
    
    # Object-oriented properties
    "jobs_for_others",
    "jobs_for_me", 
    "pending_for_me",
    "my_pending",
    "my_running",
    "my_completed",
    "approved_by_me",
    
    # Convenience functions
    "submit_job",
    "submit_python",
    "submit_bash", 
    "my_jobs",
    "get_job",
    "get_job_output",
    "get_job_logs",
    "wait_for_completion",
    "all_jobs_for_me",
    "approve",
    "reject",
    "review_job",
    "status",
    "help",
    
    # Legacy support (for existing code)
    "DataOwnerAPI",
    "DataScientistAPI",
    "submit_code",
    
    # Lower-level APIs
    "CodeQueueClient",
    "create_client", 
    
    # Models
    "CodeJob",
    "JobStatus", 
    "QueueConfig",
    "JobCollection",
]

# Legacy convenience function for backward compatibility
def submit_code(target_email: str, code_folder, name: str, **kwargs) -> CodeJob:
    """
    Legacy function for backward compatibility.
    Use submit_job() instead.
    """
    return submit_job(target_email, code_folder, name, **kwargs) 