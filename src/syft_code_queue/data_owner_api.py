#!/usr/bin/env python3
"""
Data Owner API for syft-code-queue.

This module provides a Python API for data owners to manage job approvals
and monitor their queue without using the CLI.
"""

from pathlib import Path
from typing import List, Optional
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
# App execution moved to syft-simple-runner package


class DataOwnerAPI:
    """
    Python API for data owners to manage job approvals and queue monitoring.
    
    This provides programmatic access to all data owner functionality:
    - List pending jobs
    - Review job details  
    - Approve/reject jobs
    - Monitor job execution
    - View queue statistics
    """
    
    def __init__(self, config: Optional[QueueConfig] = None):
        """Initialize the data owner API."""
        self.syftbox_client = SyftBoxClient.load()
        self.config = config or QueueConfig(queue_name="code-queue")
        # App execution is now handled by syft-simple-runner
        
        logger.info(f"Initialized Data Owner API for {self.email}")
    
    def _get_queue_dir(self) -> Path:
        """Get the queue directory."""
        return self.syftbox_client.app_data(self.config.queue_name) / "jobs"
    
    def _get_job_dir(self, job) -> Path:
        """Get directory for a specific job."""
        return self._get_queue_dir() / str(job.uid)
    
    def _get_jobs_by_status(self, status: JobStatus):
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
    
    def _load_job_from_file(self, job_file: Path):
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
    
    def _save_job(self, job):
        """Save job to storage."""
        job_file = self._get_queue_dir() / f"{job.uid}.json"
        job_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(job_file, 'w') as f:
            import json
            from uuid import UUID
            from datetime import datetime
            from pathlib import Path
            
            def custom_serializer(obj):
                if isinstance(obj, Path):
                    return str(obj)
                elif isinstance(obj, UUID):
                    return str(obj)
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
            
            json.dump(job.model_dump(), f, indent=2, default=custom_serializer)
    
    @property
    def email(self) -> str:
        """Get the data owner's email."""
        return self.syftbox_client.email
    
    # Job Listing and Filtering
    
    def list_pending_jobs(self) -> List[CodeJob]:
        """
        List all jobs pending approval for this datasite.
        
        Returns:
            List of pending CodeJob objects
        """
        pending_jobs = self.app._get_jobs_by_status(JobStatus.pending)
        return [job for job in pending_jobs if job.target_email == self.email]
    
    def list_approved_jobs(self) -> List[CodeJob]:
        """
        List all approved jobs waiting for execution.
        
        Returns:
            List of approved CodeJob objects
        """
        approved_jobs = self.app._get_jobs_by_status(JobStatus.approved)
        return [job for job in approved_jobs if job.target_email == self.email]
    
    def list_running_jobs(self) -> List[CodeJob]:
        """
        List all currently running jobs.
        
        Returns:
            List of running CodeJob objects
        """
        running_jobs = self.app._get_jobs_by_status(JobStatus.running)
        return [job for job in running_jobs if job.target_email == self.email]
    
    def list_completed_jobs(self, limit: int = 50) -> List[CodeJob]:
        """
        List recently completed jobs.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of completed CodeJob objects
        """
        completed_jobs = self.app._get_jobs_by_status(JobStatus.completed)
        my_jobs = [job for job in completed_jobs if job.target_email == self.email]
        
        # Sort by completion time, newest first
        my_jobs.sort(key=lambda j: j.completed_at or j.updated_at, reverse=True)
        return my_jobs[:limit]
    
    def list_all_jobs(self, limit: int = 100) -> List[CodeJob]:
        """
        List all jobs for this datasite across all statuses.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of CodeJob objects sorted by creation time (newest first)
        """
        all_jobs = []
        for status in JobStatus:
            jobs = self._get_jobs_by_status(status)
            my_jobs = [job for job in jobs if job.target_email == self.email]
            all_jobs.extend(my_jobs)
        
        # Sort by creation time, newest first
        all_jobs.sort(key=lambda j: j.created_at, reverse=True)
        return all_jobs[:limit]
    
    # Job Retrieval and Inspection
    
    def get_job(self, job_uid: str) -> Optional[CodeJob]:
        """
        Get a specific job by its UID.
        
        Args:
            job_uid: Full or partial job UID
            
        Returns:
            CodeJob object if found, None otherwise
        """
        # Handle both full UUID and partial ID
        if len(job_uid) == 36:  # Full UUID
            try:
                uuid_obj = UUID(job_uid)
                return self._load_job_from_file(
                    self._get_queue_dir() / f"{uuid_obj}.json"
                )
            except ValueError:
                return None
        
        # Search by partial ID
        queue_dir = self._get_queue_dir()
        if not queue_dir.exists():
            return None
        
        matches = []
        for job_file in queue_dir.glob("*.json"):
            if job_file.stem.startswith(job_uid):
                job = self._load_job_from_file(job_file)
                if job and job.target_email == self.email:
                    matches.append(job)
        
        return matches[0] if len(matches) == 1 else None
    
    def get_job_code_files(self, job_uid: str) -> Optional[List[Path]]:
        """
        Get list of code files for a job.
        
        Args:
            job_uid: Job UID
            
        Returns:
            List of file paths in the job's code directory
        """
        job = self.get_job(job_uid)
        if not job:
            return None
        
        job_dir = self._get_job_dir(job)
        if not job_dir.exists():
            return None
        
        return list(job_dir.iterdir())
    
    def get_job_code_content(self, job_uid: str, filename: str) -> Optional[str]:
        """
        Get the content of a specific code file in a job.
        
        Args:
            job_uid: Job UID
            filename: Name of file to read
            
        Returns:
            File content as string, None if file not found
        """
        job = self.get_job(job_uid)
        if not job:
            return None
        
        job_dir = self._get_job_dir(job)
        file_path = job_dir / filename
        
        if file_path.exists():
            try:
                return file_path.read_text()
            except Exception as e:
                logger.warning(f"Failed to read {filename}: {e}")
                return None
        
        return None
    
    # Job Approval and Rejection
    
    def approve_job(self, job_uid: str, reason: Optional[str] = None) -> bool:
        """
        Approve a pending job.
        
        Args:
            job_uid: Job UID to approve
            reason: Optional reason for approval
            
        Returns:
            True if successful, False otherwise
        """
        job = self.get_job(job_uid)
        if not job:
            logger.error(f"Job {job_uid} not found")
            return False
        
        if job.status != JobStatus.pending:
            logger.error(f"Job {job.name} is not pending (status: {job.status.value})")
            return False
        
        if job.target_email != self.email:
            logger.error(f"Job is not targeted at this datasite ({job.target_email})")
            return False
        
        # Update job status
        message = f"Approved by {self.email}"
        if reason:
            message += f": {reason}"
        
        job.update_status(JobStatus.approved, message)
        self._save_job(job)
        
        logger.info(f"Approved job: {job.name}")
        return True
    
    def reject_job(self, job_uid: str, reason: Optional[str] = None) -> bool:
        """
        Reject a pending job.
        
        Args:
            job_uid: Job UID to reject
            reason: Optional reason for rejection
            
        Returns:
            True if successful, False otherwise
        """
        job = self.get_job(job_uid)
        if not job:
            logger.error(f"Job {job_uid} not found")
            return False
        
        if job.status != JobStatus.pending:
            logger.error(f"Job {job.name} is not pending (status: {job.status.value})")
            return False
        
        if job.target_email != self.email:
            logger.error(f"Job is not targeted at this datasite ({job.target_email})")
            return False
        
        # Update job status
        message = f"Rejected by {self.email}"
        if reason:
            message += f": {reason}"
        
        job.update_status(JobStatus.rejected, message)
        self._save_job(job)
        
        logger.info(f"Rejected job: {job.name}")
        return True
    
    def bulk_approve(self, job_uids: List[str], reason: Optional[str] = None) -> dict:
        """
        Approve multiple jobs at once.
        
        Args:
            job_uids: List of job UIDs to approve
            reason: Optional reason for approval
            
        Returns:
            Dict with 'success' and 'failed' lists of job UIDs
        """
        results = {"success": [], "failed": []}
        
        for job_uid in job_uids:
            if self.approve_job(job_uid, reason):
                results["success"].append(job_uid)
            else:
                results["failed"].append(job_uid)
        
        return results
    
    # Queue Statistics and Monitoring
    
    def get_queue_stats(self) -> dict:
        """
        Get comprehensive queue statistics.
        
        Returns:
            Dictionary with job counts by status and other metrics
        """
        stats = {
            "data_owner": self.email,
            "queue_directory": str(self._get_queue_dir()),
            "job_counts": {},
            "total_jobs": 0
        }
        
        for status in JobStatus:
            jobs = self._get_jobs_by_status(status)
            my_jobs = [job for job in jobs if job.target_email == self.email]
            count = len(my_jobs)
            stats["job_counts"][status.value] = count
            stats["total_jobs"] += count
        
        return stats
    
    def get_job_summary(self) -> dict:
        """
        Get a summary of recent job activity.
        
        Returns:
            Dictionary with recent job activity summary
        """
        import time
        from datetime import datetime, timedelta
        
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        
        recent_jobs = self.list_all_jobs(limit=1000)  # Get more for analysis
        
        summary = {
            "total_jobs": len(recent_jobs),
            "jobs_last_24h": len([j for j in recent_jobs if j.created_at >= day_ago]),
            "jobs_last_week": len([j for j in recent_jobs if j.created_at >= week_ago]),
            "pending_jobs": len(self.list_pending_jobs()),
            "running_jobs": len(self.list_running_jobs()),
            "most_active_requesters": {}
        }
        
        # Find most active requesters
        requester_counts = {}
        for job in recent_jobs:
            requester_counts[job.requester_email] = requester_counts.get(job.requester_email, 0) + 1
        
        # Sort by job count
        sorted_requesters = sorted(requester_counts.items(), key=lambda x: x[1], reverse=True)
        summary["most_active_requesters"] = dict(sorted_requesters[:5])
        
        return summary
    
    # Convenience Methods
    
    def approve_all_pending(self, reason: Optional[str] = None) -> dict:
        """
        Approve all pending jobs at once.
        
        Args:
            reason: Optional reason for mass approval
            
        Returns:
            Dict with approval results
        """
        pending = self.list_pending_jobs()
        job_uids = [str(job.uid) for job in pending]
        return self.bulk_approve(job_uids, reason)
    
    def has_pending_jobs(self) -> bool:
        """Check if there are any pending jobs."""
        return len(self.list_pending_jobs()) > 0
    
    def process_queue_cycle(self) -> dict:
        """
        Manually trigger a queue processing cycle.
        
        Returns:
            Dict with processing results
        """
        try:
            self.app.run()
            return {"success": True, "message": "Queue processed successfully"}
        except Exception as e:
            logger.error(f"Queue processing failed: {e}")
            return {"success": False, "error": str(e)} 