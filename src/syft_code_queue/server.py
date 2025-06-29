"""Simple queue processing server for syft-code-queue."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread
from typing import Callable, List, Optional

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

from .models import CodeJob, JobStatus, QueueConfig
from .runner import CodeRunner, SafeCodeRunner


class CodeQueueServer:
    """Server that processes code execution queue."""
    
    def __init__(self, 
                 config: Optional[QueueConfig] = None,
                 runner: Optional[CodeRunner] = None,
                 approval_callback: Optional[Callable[[CodeJob], bool]] = None):
        """
        Initialize the queue server.
        
        Args:
            config: Queue configuration
            runner: Code runner instance (defaults to SafeCodeRunner)
            approval_callback: Optional callback for auto-approval logic
        """
        self.config = config or QueueConfig()
        self.runner = runner or SafeCodeRunner()  # Use safe runner by default
        self.approval_callback = approval_callback
        
        self.syftbox_client = SyftBoxClient.load()
        self.executor = ThreadPoolExecutor(max_workers=self.config.max_concurrent_jobs)
        self.running = Event()
        self.processing_thread: Optional[Thread] = None
        
    @property
    def email(self) -> str:
        """Get current user's email."""
        return self.syftbox_client.email
    
    def start(self):
        """Start the queue processing server."""
        if self.running.is_set():
            logger.warning("Server is already running")
            return
        
        logger.info(f"Starting code queue server for {self.email}")
        self.running.set()
        
        # Start the main processing thread
        self.processing_thread = Thread(target=self._process_loop, daemon=True)
        self.processing_thread.start()
        
        logger.info("Code queue server started")
    
    def stop(self):
        """Stop the queue processing server."""
        if not self.running.is_set():
            return
        
        logger.info("Stopping code queue server...")
        self.running.clear()
        
        if self.processing_thread:
            self.processing_thread.join(timeout=10)
        
        self.executor.shutdown(wait=True)
        logger.info("Code queue server stopped")
    
    def _process_loop(self):
        """Main processing loop that runs in a separate thread."""
        logger.info("Queue processing loop started")
        
        while self.running.is_set():
            try:
                # Process pending jobs
                self._process_pending_jobs()
                
                # Execute approved jobs
                self._execute_approved_jobs()
                
                # Cleanup old jobs
                self._cleanup_old_jobs()
                
                # Sleep between cycles
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                time.sleep(10)  # Wait longer on error
        
        logger.info("Queue processing loop stopped")
    
    def _process_pending_jobs(self):
        """Process jobs waiting for approval."""
        pending_jobs = self._get_jobs_by_status(JobStatus.pending)
        
        for job in pending_jobs:
            # Skip if not targeted at this datasite
            if job.target_email != self.email:
                continue
            
            logger.info(f"Processing pending job: {job.name} from {job.requester_email}")
            
            # Check for auto-approval
            if self._should_auto_approve(job):
                logger.info(f"Auto-approving job {job.uid}")
                job.update_status(JobStatus.approved)
                self._save_job(job)
            else:
                logger.info(f"Job {job.uid} requires manual approval")
                # In a real implementation, you might send notifications here
    
    def _execute_approved_jobs(self):
        """Execute jobs that have been approved."""
        approved_jobs = self._get_jobs_by_status(JobStatus.approved)
        
        # Limit concurrent executions
        running_jobs = self._get_jobs_by_status(JobStatus.running)
        if len(running_jobs) >= self.config.max_concurrent_jobs:
            return
        
        for job in approved_jobs[:self.config.max_concurrent_jobs - len(running_jobs)]:
            if job.target_email != self.email:
                continue
            
            logger.info(f"Starting execution of job: {job.name}")
            job.update_status(JobStatus.running)
            self._save_job(job)
            
            # Submit to thread pool
            future = self.executor.submit(self._execute_job, job)
            # Don't block - let it run asynchronously
    
    def _execute_job(self, job: CodeJob):
        """Execute a single job."""
        try:
            logger.info(f"Executing job {job.uid}: {job.name}")
            
            # Run the job
            exit_code, stdout, stderr = self.runner.run_job(job)
            
            # Update job status based on result
            if exit_code == 0:
                job.update_status(JobStatus.completed)
                logger.info(f"Job {job.uid} completed successfully")
            else:
                job.update_status(JobStatus.failed, f"Exit code: {exit_code}")
                logger.warning(f"Job {job.uid} failed with exit code {exit_code}")
            
        except Exception as e:
            error_msg = f"Job execution error: {e}"
            job.update_status(JobStatus.failed, error_msg)
            logger.error(f"Job {job.uid} failed: {error_msg}")
        
        finally:
            # Always save the final job state
            self._save_job(job)
    
    def _should_auto_approve(self, job: CodeJob) -> bool:
        """Determine if a job should be auto-approved."""
        # Check if auto-approval is enabled
        if not self.config.auto_approval_enabled:
            return False
        
        # Check if job is marked for auto-approval
        if not job.auto_approval:
            return False
        
        # Use custom approval callback if provided
        if self.approval_callback:
            try:
                return self.approval_callback(job)
            except Exception as e:
                logger.error(f"Approval callback failed for job {job.uid}: {e}")
                return False
        
        # Default auto-approval rules
        return self._default_auto_approval_rules(job)
    
    def _default_auto_approval_rules(self, job: CodeJob) -> bool:
        """Default auto-approval rules."""
        # Auto-approve jobs with certain tags
        safe_tags = {"data-analysis", "visualization", "statistics", "report"}
        if any(tag in safe_tags for tag in job.tags):
            return True
        
        # Auto-approve from trusted requesters (you'd customize this)
        trusted_domains = {"@openmined.org", "@company.com"}
        if any(domain in job.requester_email for domain in trusted_domains):
            return True
        
        return False
    
    def _cleanup_old_jobs(self):
        """Clean up old completed jobs."""
        cutoff_time = time.time() - self.config.cleanup_completed_after
        
        for job_file in self._get_queue_dir().glob("*.json"):
            try:
                job = self._load_job_from_file(job_file)
                if job and job.is_terminal and job.completed_at:
                    if job.completed_at.timestamp() < cutoff_time:
                        logger.info(f"Cleaning up old job: {job.uid}")
                        job_file.unlink()
                        
                        # Also remove job directory
                        job_dir = self._get_job_dir(job)
                        if job_dir.exists():
                            import shutil
                            shutil.rmtree(job_dir)
                            
            except Exception as e:
                logger.warning(f"Failed to cleanup job {job_file}: {e}")
    
    def approve_job(self, job_uid: str) -> bool:
        """Manually approve a job."""
        job = self._get_job_by_uid(job_uid)
        if not job:
            return False
        
        if job.status != JobStatus.pending:
            logger.warning(f"Cannot approve job {job_uid} with status {job.status}")
            return False
        
        logger.info(f"Manually approving job {job_uid}")
        job.update_status(JobStatus.approved)
        self._save_job(job)
        return True
    
    def reject_job(self, job_uid: str, reason: str = "Rejected by data owner") -> bool:
        """Manually reject a job."""
        job = self._get_job_by_uid(job_uid)
        if not job:
            return False
        
        if job.status not in (JobStatus.pending, JobStatus.approved):
            logger.warning(f"Cannot reject job {job_uid} with status {job.status}")
            return False
        
        logger.info(f"Manually rejecting job {job_uid}: {reason}")
        job.update_status(JobStatus.rejected, reason)
        self._save_job(job)
        return True
    
    def list_pending_jobs(self) -> List[CodeJob]:
        """List jobs waiting for approval."""
        return [job for job in self._get_jobs_by_status(JobStatus.pending) 
                if job.target_email == self.email]
    
    def _get_jobs_by_status(self, status: JobStatus) -> List[CodeJob]:
        """Get all jobs with a specific status."""
        jobs = []
        queue_dir = self._get_queue_dir()
        
        if not queue_dir.exists():
            return jobs
        
        for job_file in queue_dir.glob("*.json"):
            job = self._load_job_from_file(job_file)
            if job and job.status == status:
                jobs.append(job)
        
        return jobs
    
    def _get_job_by_uid(self, job_uid: str) -> Optional[CodeJob]:
        """Get a job by its UID."""
        job_file = self._get_queue_dir() / f"{job_uid}.json"
        return self._load_job_from_file(job_file)
    
    def _load_job_from_file(self, job_file: Path) -> Optional[CodeJob]:
        """Load a job from a JSON file."""
        try:
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
        except Exception as e:
            logger.warning(f"Failed to load job from {job_file}: {e}")
            return None
    
    def _save_job(self, job: CodeJob):
        """Save job to storage."""
        job_file = self._get_queue_dir() / f"{job.uid}.json"
        job_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(job_file, 'w') as f:
            import json
            from uuid import UUID
            from datetime import datetime
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
        """Get the queue directory."""
        return self.syftbox_client.app_data(self.config.queue_name) / "jobs"
    
    def _get_job_dir(self, job: CodeJob) -> Path:
        """Get directory for a specific job."""
        return self._get_queue_dir() / str(job.uid)


def create_server(auto_approval_callback: Optional[Callable[[CodeJob], bool]] = None,
                  **config_kwargs) -> CodeQueueServer:
    """
    Create a code queue server.
    
    Args:
        auto_approval_callback: Optional callback for custom auto-approval logic
        **config_kwargs: Additional configuration options
        
    Returns:
        CodeQueueServer instance
    """
    config = QueueConfig(**config_kwargs)
    return CodeQueueServer(config=config, approval_callback=auto_approval_callback) 