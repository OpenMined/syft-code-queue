"""Simple client for syft-code-queue."""

import shutil
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from loguru import logger
try:
    from syft_core import Client as SyftBoxClient
except ImportError:
    # Fallback for tutorial/demo purposes
    class MockSyftBoxClient:
        def __init__(self):
            self.email = "demo@example.com"
        
        def app_data(self, app_name):
            from pathlib import Path
            import tempfile
            return Path(tempfile.gettempdir()) / f"syftbox_demo_{app_name}"
        
        @classmethod
        def load(cls):
            return cls()
    
    SyftBoxClient = MockSyftBoxClient

from .models import CodeJob, JobCreate, JobStatus, QueueConfig


class CodeQueueClient:
    """Simple client for submitting code to remote execution queues."""
    
    def __init__(self, syftbox_client: Optional[SyftBoxClient] = None, config: Optional[QueueConfig] = None):
        """Initialize the code queue client."""
        self.syftbox_client = syftbox_client or SyftBoxClient.load()
        self.config = config or QueueConfig()
        self.queue_name = self.config.queue_name
        
    @property
    def email(self) -> str:
        """Get current user's email."""
        return self.syftbox_client.email
    
    def submit_code(self, 
                    target_email: str,
                    code_folder: Path,
                    name: str,
                    description: Optional[str] = None,
                    tags: Optional[List[str]] = None,
                    auto_approval: bool = False) -> CodeJob:
        """
        Submit code for execution on a remote datasite.
        
        Args:
            target_email: Email of the data owner
            code_folder: Local folder containing code and run.sh
            name: Human-readable name for the job
            description: Optional description
            tags: Optional tags for categorization
            auto_approval: Whether this job can be auto-approved
            
        Returns:
            CodeJob: The created job
        """
        # Validate code folder
        if not code_folder.exists():
            raise ValueError(f"Code folder does not exist: {code_folder}")
        
        run_script = code_folder / "run.sh"
        if not run_script.exists():
            raise ValueError(f"Code folder must contain run.sh: {run_script}")
        
        # Create job
        job_create = JobCreate(
            name=name,
            target_email=target_email,
            code_folder=code_folder,
            description=description,
            tags=tags or [],
            auto_approval=auto_approval
        )
        
        job = CodeJob(
            **job_create.model_dump(),
            requester_email=self.email
        )
        
        # Copy code to queue location
        self._copy_code_to_queue(job)
        
        # Save job to local queue
        self._save_job(job)
        
        logger.info(f"Submitted job '{name}' to {target_email}")
        return job
    
    def get_job(self, job_uid: UUID) -> Optional[CodeJob]:
        """Get a job by its UID."""
        job_file = self._get_job_file(job_uid)
        if not job_file.exists():
            return None
        
        with open(job_file, 'r') as f:
            import json
            from uuid import UUID
            from datetime import datetime
            data = json.load(f)
            
            # Convert string representations back to proper types
            if 'uid' in data and isinstance(data['uid'], str):
                data['uid'] = UUID(data['uid'])
            
            for date_field in ['created_at', 'updated_at', 'started_at', 'completed_at']:
                if date_field in data and data[date_field] and isinstance(data[date_field], str):
                    data[date_field] = datetime.fromisoformat(data[date_field])
            
            return CodeJob.model_validate(data)
    
    def list_jobs(self, 
                  target_email: Optional[str] = None,
                  status: Optional[JobStatus] = None,
                  limit: int = 50) -> List[CodeJob]:
        """
        List jobs, optionally filtered.
        
        Args:
            target_email: Filter by target email
            status: Filter by job status
            limit: Maximum number of jobs to return
            
        Returns:
            List of matching jobs
        """
        jobs = []
        queue_dir = self._get_queue_dir()
        
        if not queue_dir.exists():
            return jobs
        
        for job_file in queue_dir.glob("*.json"):
            try:
                with open(job_file, 'r') as f:
                    import json
                    data = json.load(f)
                    job = CodeJob.model_validate(data)
                    
                    # Apply filters
                    if target_email and job.target_email != target_email:
                        continue
                    if status and job.status != status:
                        continue
                    
                    jobs.append(job)
                    
                    if len(jobs) >= limit:
                        break
                        
            except Exception as e:
                logger.warning(f"Failed to load job from {job_file}: {e}")
                continue
        
        # Sort by creation time, newest first
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs
    
    def get_job_output(self, job_uid: UUID) -> Optional[Path]:
        """Get the output folder for a completed job."""
        job = self.get_job(job_uid)
        if not job or not job.output_folder:
            return None
        
        return job.output_folder
    
    def get_job_logs(self, job_uid: UUID) -> Optional[str]:
        """Get execution logs for a job."""
        job = self.get_job(job_uid)
        if not job:
            return None
        
        log_file = self._get_job_dir(job) / "execution.log"
        if log_file.exists():
            return log_file.read_text()
        return None
    
    def cancel_job(self, job_uid: UUID) -> bool:
        """Cancel a pending job."""
        job = self.get_job(job_uid)
        if not job:
            return False
        
        if job.status not in (JobStatus.pending, JobStatus.approved):
            logger.warning(f"Cannot cancel job {job_uid} with status {job.status}")
            return False
        
        job.update_status(JobStatus.rejected, "Cancelled by requester")
        self._save_job(job)
        return True
    
    def _copy_code_to_queue(self, job: CodeJob):
        """Copy code folder to the queue location."""
        job_dir = self._get_job_dir(job)
        job_dir.mkdir(parents=True, exist_ok=True)
        
        code_dir = job_dir / "code"
        if code_dir.exists():
            shutil.rmtree(code_dir)
        
        shutil.copytree(job.code_folder, code_dir)
        job.code_folder = code_dir  # Update to queue location
    
    def _save_job(self, job: CodeJob):
        """Save job to local storage."""
        job_file = self._get_job_file(job.uid)
        job_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(job_file, 'w') as f:
            import json
            from uuid import UUID
            from datetime import datetime
            # Custom serializer for Path, UUID, and datetime objects
            def custom_serializer(obj):
                if isinstance(obj, Path):
                    return str(obj)
                elif isinstance(obj, UUID):
                    return str(obj)
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
            
            json.dump(job.model_dump(), f, indent=2, default=custom_serializer)
    
    def _get_queue_dir(self) -> Path:
        """Get the local queue directory."""
        return self.syftbox_client.app_data(self.queue_name) / "jobs"
    
    def _get_job_dir(self, job: CodeJob) -> Path:
        """Get directory for a specific job."""
        return self._get_queue_dir() / str(job.uid)
    
    def _get_job_file(self, job_uid: UUID) -> Path:
        """Get the JSON file path for a job."""
        return self._get_queue_dir() / f"{job_uid}.json"


def create_client(target_email: str = None, **config_kwargs) -> CodeQueueClient:
    """
    Create a code queue client.
    
    Args:
        target_email: If provided, optimizes for submitting to this target
        **config_kwargs: Additional configuration options
        
    Returns:
        CodeQueueClient instance
    """
    config = QueueConfig(**config_kwargs)
    return CodeQueueClient(config=config) 