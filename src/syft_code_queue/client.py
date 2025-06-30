"""Simple client for syft-code-queue."""

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
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
            import tempfile
            from pathlib import Path
            return Path(tempfile.gettempdir()) / f"syftbox_demo_{app_name}"

        @classmethod
        def load(cls):
            return cls()

    SyftBoxClient = MockSyftBoxClient

from .models import CodeJob, JobCreate, JobStatus, QueueConfig


class CodeQueueClient:
    """Client for interacting with the code queue."""

    def __init__(self, syftbox_client: SyftBoxClient, config: QueueConfig):
        """Initialize the client."""
        self.syftbox_client = syftbox_client
        self.queue_name = config.queue_name
        self.email = syftbox_client.email

        # Create status directories
        for status in JobStatus:
            status_dir = self._get_status_dir(status)
            status_dir.mkdir(parents=True, exist_ok=True)

    def _get_status_dir(self, status: JobStatus) -> Path:
        """Get directory for a specific job status."""
        return self._get_queue_dir() / status.value

    def _get_queue_dir(self) -> Path:
        """Get the local queue directory."""
        return self.syftbox_client.app_data(self.queue_name) / "jobs"

    def _get_job_dir(self, job: CodeJob) -> Path:
        """Get directory for a specific job."""
        return self._get_status_dir(job.status) / str(job.uid)

    def _get_job_file(self, job_uid: UUID) -> Optional[Path]:
        """Get the metadata.json file path for a job."""
        # Search in all status directories
        for status in JobStatus:
            job_dir = self._get_status_dir(status) / str(job_uid)
            if job_dir.exists():
                job_file = job_dir / "metadata.json"
                if job_file.exists():
                    return job_file

        # If not found, return path in pending directory (for new jobs)
        job_dir = self._get_status_dir(JobStatus.pending) / str(job_uid)
        return job_dir / "metadata.json"

    def _save_job(self, job: CodeJob):
        """Save job to local storage."""
        old_job = self.get_job(job.uid)
        old_status = old_job.status if old_job else None

        # If status changed, move job directory to new status directory
        if old_status and old_status != job.status:
            old_job_dir = self._get_status_dir(old_status) / str(job.uid)
            new_job_dir = self._get_job_dir(job)

            if old_job_dir.exists():
                # Move the entire job directory
                new_job_dir.parent.mkdir(parents=True, exist_ok=True)
                if new_job_dir.exists():
                    shutil.rmtree(new_job_dir)
                shutil.move(str(old_job_dir), str(new_job_dir))

        # Ensure job directory exists
        job_dir = self._get_job_dir(job)
        job_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata file inside job directory
        job_file = job_dir / "metadata.json"

        with open(job_file, 'w') as f:
            def custom_serializer(obj):
                if isinstance(obj, Path):
                    return str(obj)
                elif isinstance(obj, UUID):
                    return str(obj)
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            json.dump(job.model_dump(), f, indent=2, default=custom_serializer)

    def list_jobs(self,
                  target_email: Optional[str] = None,
                  status: Optional[JobStatus] = None,
                  limit: int = 50) -> list[CodeJob]:
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

        # Determine which status directories to search
        if status:
            status_dirs = [self._get_status_dir(status)]
        else:
            status_dirs = [self._get_status_dir(s) for s in JobStatus]

        # Search in each status directory
        for status_dir in status_dirs:
            if not status_dir.exists():
                continue

            # Look for job directories with metadata.json
            for job_dir in status_dir.glob("*"):
                if not job_dir.is_dir():
                    continue

                try:
                    metadata_file = job_dir / "metadata.json"
                    if not metadata_file.exists():
                        continue

                    with open(metadata_file) as f:
                        data = json.load(f)
                        job = CodeJob.model_validate(data)
                        job._client = self  # Set client reference

                        # Apply filters
                        if target_email and job.target_email != target_email:
                            continue

                        jobs.append(job)

                        if len(jobs) >= limit:
                            break

                except Exception as e:
                    logger.warning(f"Failed to load job from {metadata_file}: {e}")
                    continue

            if len(jobs) >= limit:
                break

        # Sort by creation time, newest first
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    def create_python_job(self,
                         target_email: str,
                         script_content: str,
                         name: str,
                         description: Optional[str] = None,
                         requirements: Optional[list[str]] = None,
                         tags: Optional[list[str]] = None) -> CodeJob:
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
            return self.submit_code(
                target_email=target_email,
                code_folder=temp_dir,
                name=name,
                description=description,
                tags=tags
            )

        finally:
            # Note: We don't delete temp_dir here because it's copied by submit_code
            # The temp directory will be cleaned up by the system later
            pass

    def submit_code(self,
                    target_email: str,
                    code_folder: Path,
                    name: str,
                    description: Optional[str] = None,
                    tags: Optional[list[str]] = None) -> CodeJob:
        """
        Submit code for execution on a remote datasite.

        Args:
            target_email: Email of the data owner
            code_folder: Local folder containing code and run.sh
            name: Human-readable name for the job
            description: Optional description
            tags: Optional tags for categorization

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
            tags=tags or []
        )

        job = CodeJob(
            **job_create.model_dump(),
            requester_email=self.email
        )
        job._client = self  # Set the client reference

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

        with open(job_file) as f:
            import json
            from datetime import datetime
            from uuid import UUID
            data = json.load(f)

            # Convert string representations back to proper types
            if 'uid' in data and isinstance(data['uid'], str):
                data['uid'] = UUID(data['uid'])

            for date_field in ['created_at', 'updated_at', 'started_at', 'completed_at']:
                if date_field in data and data[date_field] and isinstance(data[date_field], str):
                    data[date_field] = datetime.fromisoformat(data[date_field])

            return CodeJob.model_validate(data)

    def list_my_jobs(self, limit: int = 50) -> list[CodeJob]:
        """List jobs submitted by me."""
        return self.list_jobs(target_email=None, limit=limit)

    def list_all_jobs(self, limit: int = 50) -> list[CodeJob]:
        """List jobs submitted to me."""
        return self.list_jobs(target_email=self.email, limit=limit)

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

    def wait_for_completion(self, job_uid: UUID, timeout: int = 600) -> CodeJob:
        """
        Wait for a job to complete.

        Args:
            job_uid: The job's UUID
            timeout: Maximum time to wait in seconds

        Returns:
            The completed job

        Raises:
            TimeoutError: If the job doesn't complete within the timeout
            RuntimeError: If the job fails or is rejected
        """
        import time
        start_time = time.time()
        poll_interval = 2  # seconds

        # Print initial status
        job = self.get_job(job_uid)
        if not job:
            raise RuntimeError(f"Job {job_uid} not found")
        print(f"\nWaiting for job '{job.name}' to complete...", end="", flush=True)

        while True:
            job = self.get_job(job_uid)
            if not job:
                raise RuntimeError(f"Job {job_uid} not found")

            if job.status == JobStatus.completed:
                print("\nJob completed successfully!")
                return job
            elif job.status in (JobStatus.failed, JobStatus.rejected):
                print(f"\nJob failed with status {job.status}: {job.error_message}")
                raise RuntimeError(f"Job failed with status {job.status}: {job.error_message}")

            if time.time() - start_time > timeout:
                print("\nTimeout!")
                raise TimeoutError(f"Job {job_uid} did not complete within {timeout} seconds")

            print(".", end="", flush=True)
            time.sleep(poll_interval)

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

    def approve_job(self, job_uid: Union[str, UUID], reason: Optional[str] = None) -> bool:
        """
        Approve a job for execution.

        Args:
            job_uid: The job's UUID
            reason: Optional reason for approval

        Returns:
            bool: True if approved successfully
        """
        job = self.get_job(job_uid)
        if not job:
            return False

        if job.target_email != self.email:
            logger.warning(f"Cannot approve job {job_uid} - not the target owner")
            return False

        if job.status != JobStatus.pending:
            logger.warning(f"Cannot approve job {job_uid} with status {job.status}")
            return False

        job.update_status(JobStatus.approved)
        self._save_job(job)

        logger.info(f"Approved job: {job.name}")
        return True

    def reject_job(self, job_uid: Union[str, UUID], reason: Optional[str] = None) -> bool:
        """
        Reject a job.

        Args:
            job_uid: The job's UUID
            reason: Optional reason for rejection

        Returns:
            bool: True if rejected successfully
        """
        job = self.get_job(job_uid)
        if not job:
            return False

        if job.target_email != self.email:
            logger.warning(f"Cannot reject job {job_uid} - not the target owner")
            return False

        if job.status != JobStatus.pending:
            logger.warning(f"Cannot reject job {job_uid} with status {job.status}")
            return False

        job.update_status(JobStatus.rejected, reason)
        self._save_job(job)

        logger.info(f"Rejected job: {job.name}")
        return True


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
    return CodeQueueClient(SyftBoxClient.load(), config)
