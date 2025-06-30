#!/usr/bin/env python3
"""
Data Scientist API for syft-code-queue.

This module provides a clean Python API for data scientists to submit
code for execution and monitor job progress.
"""

from pathlib import Path
from typing import List, Optional, Union
from uuid import UUID

from loguru import logger

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

from .models import JobStatus, QueueConfig, CodeJob
from .client import CodeQueueClient


class DataScientistAPI:
    """
    Python API for data scientists to submit and monitor code execution jobs.
    
    This provides a clean interface for:
    - Submitting code packages for execution
    - Monitoring job status and progress
    - Retrieving results and logs
    - Managing submitted jobs
    """
    
    def __init__(self, config: Optional[QueueConfig] = None):
        """Initialize the data scientist API."""
        self.syftbox_client = SyftBoxClient.load()
        self.config = config or QueueConfig(queue_name="code-queue")
        self.client = CodeQueueClient(syftbox_client=self.syftbox_client, config=self.config)
        
        logger.info(f"Initialized Data Scientist API for {self.email}")
    
    @property
    def email(self) -> str:
        """Get the data scientist's email."""
        return self.syftbox_client.email
    
    # Job Submission
    
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
            CodeJob: The submitted job object
            
        Raises:
            ValueError: If code folder is invalid or missing run.sh
        """
        code_path = Path(code_folder)
        
        # Validate code folder
        if not code_path.exists():
            raise ValueError(f"Code folder does not exist: {code_path}")
        
        run_script = code_path / "run.sh"
        if not run_script.exists():
            raise ValueError(f"Code folder must contain run.sh script: {run_script}")
        
        # Submit the job
        job = self.client.submit_code(
            target_email=target_email,
            code_folder=code_path,
            name=name,
            description=description,
            tags=tags or []
        )
        
        logger.info(f"Submitted job '{name}' to {target_email} (ID: {job.uid})")
        return job
    
    def create_python_job(self,
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
            CodeJob: The submitted job object
        """
        import tempfile
        
        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Create Python script file
            script_file = temp_dir / "script.py"
            script_file.write_text(script_content)
            
            # Create run.sh for Python execution
            run_content = "#!/bin/bash\nset -e\n"
            if requirements:
                req_file = temp_dir / "requirements.txt"
                req_file.write_text("\n".join(requirements))
                run_content += "pip install -r requirements.txt\n"
            run_content += "python script.py\n"
            
            run_script = temp_dir / "run.sh"
            run_script.write_text(run_content)
            run_script.chmod(0o755)
            
            # Submit the job
            job = self.submit_job(
                target_email=target_email,
                code_folder=temp_dir,
                name=name,
                description=description,
                tags=tags
            )
            
            return job
            
        finally:
            # Note: We don't delete temp_dir here because the client copies it
            # The temp directory will be cleaned up by the system later
            pass
    
    def create_bash_job(self,
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
            CodeJob: The submitted job object
        """
        import tempfile
        
        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Create bash script file
            script_file = temp_dir / "script.sh"
            script_file.write_text(script_content)
            script_file.chmod(0o755)
            
            # Create run.sh for bash execution
            run_content = "#!/bin/bash\nset -e\n./script.sh\n"
            run_script = temp_dir / "run.sh"
            run_script.write_text(run_content)
            run_script.chmod(0o755)
            
            # Submit the job
            job = self.submit_job(
                target_email=target_email,
                code_folder=temp_dir,
                name=name,
                description=description,
                tags=tags
            )
            
            return job
            
        finally:
            # Note: We don't delete temp_dir here because the client copies it
            # The temp directory will be cleaned up by the system later
            pass
    
    # Job Monitoring and Retrieval
    
    def get_job(self, job_uid: Union[str, UUID]) -> Optional[CodeJob]:
        """
        Get a specific job by its UID.
        
        Args:
            job_uid: Job UID (full UUID or partial string)
            
        Returns:
            CodeJob object if found, None otherwise
        """
        if isinstance(job_uid, UUID):
            job_uid = str(job_uid)
        
        return self.client.get_job(UUID(job_uid) if len(job_uid) == 36 else job_uid)
    
    def list_my_jobs(self, 
                     status: Optional[JobStatus] = None,
                     target_email: Optional[str] = None,
                     limit: int = 50) -> List[CodeJob]:
        """
        List jobs submitted by this data scientist.
        
        Args:
            status: Optional filter by job status
            target_email: Optional filter by target datasite
            limit: Maximum number of jobs to return
            
        Returns:
            List of CodeJob objects matching the criteria
        """
        all_jobs = self.client.list_jobs(target_email=target_email, status=status, limit=limit * 2)
        
        # Filter to only jobs from this user
        my_jobs = [job for job in all_jobs if job.requester_email == self.email]
        
        return my_jobs[:limit]
    
    def list_pending_jobs(self, target_email: Optional[str] = None) -> List[CodeJob]:
        """List jobs pending approval."""
        return self.list_my_jobs(status=JobStatus.pending, target_email=target_email)
    
    def list_running_jobs(self, target_email: Optional[str] = None) -> List[CodeJob]:
        """List currently running jobs."""
        return self.list_my_jobs(status=JobStatus.running, target_email=target_email)
    
    def list_completed_jobs(self, target_email: Optional[str] = None, limit: int = 20) -> List[CodeJob]:
        """List completed jobs."""
        return self.list_my_jobs(status=JobStatus.completed, target_email=target_email, limit=limit)
    
    def list_failed_jobs(self, target_email: Optional[str] = None, limit: int = 20) -> List[CodeJob]:
        """List failed jobs."""
        return self.list_my_jobs(status=JobStatus.failed, target_email=target_email, limit=limit)
    
    # Job Results and Logs
    
    def get_job_output(self, job_uid: Union[str, UUID]) -> Optional[Path]:
        """
        Get the output directory path for a completed job.
        
        Args:
            job_uid: Job UID
            
        Returns:
            Path to output directory if job completed successfully, None otherwise
        """
        if isinstance(job_uid, str) and len(job_uid) < 36:
            # Handle partial ID
            job = self.get_job(job_uid)
            if job:
                job_uid = job.uid
            else:
                return None
        
        if isinstance(job_uid, str):
            job_uid = UUID(job_uid)
        
        return self.client.get_job_output(job_uid)
    
    def get_job_logs(self, job_uid: Union[str, UUID]) -> Optional[str]:
        """
        Get execution logs for a job.
        
        Args:
            job_uid: Job UID
            
        Returns:
            Execution logs as string, None if not available
        """
        if isinstance(job_uid, str) and len(job_uid) < 36:
            # Handle partial ID
            job = self.get_job(job_uid)
            if job:
                job_uid = job.uid
            else:
                return None
        
        if isinstance(job_uid, str):
            job_uid = UUID(job_uid)
        
        return self.client.get_job_logs(job_uid)
    
    def get_job_results(self, job_uid: Union[str, UUID]) -> dict:
        """
        Get comprehensive results for a job including output files and logs.
        
        Args:
            job_uid: Job UID
            
        Returns:
            Dictionary with job results, output files, and logs
        """
        job = self.get_job(job_uid)
        if not job:
            return {"error": "Job not found"}
        
        results = {
            "job": {
                "uid": str(job.uid),
                "name": job.name,
                "status": job.status.value,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "duration": job.duration if job.completed_at else None
            },
            "output_files": {},
            "logs": None,
            "error": job.error_message
        }
        
        # Get output files
        output_path = self.get_job_output(job.uid)
        if output_path and output_path.exists():
            results["output_path"] = str(output_path)
            
            # List output files and read small ones
            for file_path in output_path.iterdir():
                if file_path.is_file():
                    try:
                        # Only read files smaller than 1MB
                        if file_path.stat().st_size < 1024 * 1024:
                            results["output_files"][file_path.name] = file_path.read_text()
                        else:
                            results["output_files"][file_path.name] = f"<large file: {file_path.stat().st_size} bytes>"
                    except Exception as e:
                        results["output_files"][file_path.name] = f"<error reading file: {e}>"
        
        # Get logs
        logs = self.get_job_logs(job.uid)
        if logs:
            results["logs"] = logs
        
        return results
    
    # Job Management
    
    def cancel_job(self, job_uid: Union[str, UUID]) -> bool:
        """
        Cancel a pending job.
        
        Args:
            job_uid: Job UID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        if isinstance(job_uid, str) and len(job_uid) < 36:
            # Handle partial ID
            job = self.get_job(job_uid)
            if job:
                job_uid = job.uid
            else:
                return False
        
        if isinstance(job_uid, str):
            job_uid = UUID(job_uid)
        
        success = self.client.cancel_job(job_uid)
        if success:
            logger.info(f"Cancelled job {job_uid}")
        
        return success
    
    def wait_for_completion(self, 
                           job_uid: Union[str, UUID], 
                           timeout: int = 600,
                           poll_interval: int = 5) -> CodeJob:
        """
        Wait for a job to complete.
        
        Args:
            job_uid: Job UID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: How often to check status in seconds
            
        Returns:
            Final CodeJob object
            
        Raises:
            TimeoutError: If job doesn't complete within timeout
        """
        import time
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            job = self.get_job(job_uid)
            if not job:
                raise ValueError(f"Job {job_uid} not found")
            
            if job.is_terminal:
                logger.info(f"Job {job.name} completed with status: {job.status.value}")
                return job
            
            logger.debug(f"Job {job.name} status: {job.status.value}")
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Job {job_uid} did not complete within {timeout} seconds")
    
    # Convenience Methods
    
    def get_my_job_summary(self) -> dict:
        """
        Get a summary of this data scientist's job activity.
        
        Returns:
            Dictionary with job statistics and recent activity
        """
        from datetime import datetime, timedelta
        
        recent_jobs = self.list_my_jobs(limit=100)
        
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        
        summary = {
            "data_scientist": self.email,
            "total_jobs": len(recent_jobs),
            "jobs_last_24h": len([j for j in recent_jobs if j.created_at >= day_ago]),
            "jobs_last_week": len([j for j in recent_jobs if j.created_at >= week_ago]),
            "status_counts": {},
            "target_datasites": {}
        }
        
        # Count by status
        for status in JobStatus:
            count = len([j for j in recent_jobs if j.status == status])
            if count > 0:
                summary["status_counts"][status.value] = count
        
        # Count by target datasite
        target_counts = {}
        for job in recent_jobs:
            target_counts[job.target_email] = target_counts.get(job.target_email, 0) + 1
        
        summary["target_datasites"] = target_counts
        
        return summary
    
    def has_pending_jobs(self) -> bool:
        """Check if this data scientist has any pending jobs."""
        return len(self.list_pending_jobs()) > 0
    
    def has_running_jobs(self) -> bool:
        """Check if this data scientist has any running jobs."""
        return len(self.list_running_jobs()) > 0 