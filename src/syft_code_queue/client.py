"""Simple client for syft-code-queue."""

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from uuid import UUID

from loguru import logger

from syft_core import Client as SyftBoxClient
from .models import CodeJob, JobCreate, JobStatus, QueueConfig

# Import syft-perm for permission management (required)

from syft_perm import set_file_permissions



class CodeQueueClient:
    """
    Client for interacting with the code queue.
    
    Cross-Datasite Workflow:
    1. Job Creation: When a job is submitted, it gets stored in the TARGET's datasite "pending" folder
    2. Job Review: When someone approves/rejects a job, it moves within THEIR own datasite
       (from "pending" to "approved"/"rejected" folder in the reviewer's datasite)
    3. Job Discovery: 
       - list_all_jobs() finds jobs submitted TO you (in your local datasite)
       - list_my_jobs() finds jobs submitted BY you (searches across all datasites)
    """

    def __init__(self, syftbox_client: SyftBoxClient, config: QueueConfig):
        """Initialize the client."""
        self.syftbox_client = syftbox_client
        self.queue_name = config.queue_name
        self.email = syftbox_client.email

        # Create status directories with proper permissions
        logger.debug(f"Initializing syft-code-queue for {self.email}")
        
        for status in JobStatus:
            status_dir = self._get_status_dir(status)
            try:
                status_dir.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Created status directory: {status_dir}")
                
                # Create syft.pub.yaml file for pending folder to allow cross-datasite writes
                if status == JobStatus.pending:
                    self._create_pending_syftperm(status_dir)
                    logger.info(f"Initialized pending directory with cross-datasite permissions: {status_dir}")
                    
            except Exception as e:
                logger.error(f"Failed to initialize status directory {status_dir}: {e}")
                # Don't fail completely - try to continue with other directories
                continue

    def _get_target_queue_dir(self, target_email: str) -> Path:
        """Get the queue directory for a target email's datasite."""
        return self.syftbox_client.datasites / target_email / "app_data" / self.queue_name / "jobs"

    def _get_status_dir(self, status: JobStatus) -> Path:
        """Get directory for a specific job status."""
        return self._get_queue_dir() / status.value

    def _get_queue_dir(self) -> Path:
        """Get the local queue directory."""
        return self.syftbox_client.app_data(self.queue_name) / "jobs"
    
    def _create_pending_syftperm(self, pending_dir: Path):
        """Create syft.pub.yaml file for pending directory to allow cross-datasite writes."""
        syftperm_file = pending_dir / "syft.pub.yaml"
        
        # Required syft.pub.yaml content for cross-datasite writes
        required_syftperm_content = """rules:
- pattern: '**'
  access:
    read:
    - '*'
    write:
    - '*'
"""
        
        try:
            # Always ensure the pending directory exists
            pending_dir.mkdir(parents=True, exist_ok=True)
            
            # Check if syft.pub.yaml file exists and has correct content
            needs_creation = True
            if syftperm_file.exists():
                try:
                    existing_content = syftperm_file.read_text().strip()
                    required_content = required_syftperm_content.strip()
                    if existing_content == required_content:
                        needs_creation = False
                        logger.debug(f"Correct syft.pub.yaml file already exists in {pending_dir}")
                    else:
                        logger.info(f"Updating syft.pub.yaml file in {pending_dir} with correct permissions")
                except Exception as e:
                    logger.warning(f"Could not read existing syft.pub.yaml file in {pending_dir}: {e}")
            
            # Create or update the syft.pub.yaml file if needed
            if needs_creation:
                with open(syftperm_file, 'w') as f:
                    f.write(required_syftperm_content)
                logger.info(f"Created/updated syft.pub.yaml file for pending directory: {pending_dir}")
                
        except PermissionError as e:
            logger.error(f"Permission denied creating syft.pub.yaml file in {pending_dir}: {e}")
            raise RuntimeError(f"Cannot create syft.pub.yaml file - insufficient permissions: {e}")
        except Exception as e:
            logger.error(f"Failed to create syft.pub.yaml file in {pending_dir}: {e}")
            raise RuntimeError(f"Failed to setup pending directory permissions: {e}")

    def _ensure_target_pending_directory(self, target_email: str):
        """Ensure the target's pending directory exists with proper syft.pub.yaml for cross-datasite writes."""
        target_queue_dir = self._get_target_queue_dir(target_email)
        pending_dir = target_queue_dir / JobStatus.pending.value
        
        try:
            # Create pending directory and syft.pub.yaml file (handles both directory creation and permissions)
            self._create_pending_syftperm(pending_dir)
            logger.debug(f"Ensured pending directory exists with permissions for {target_email}")
        except Exception as e:
            logger.error(f"Failed to ensure pending directory for {target_email}: {e}")
            raise RuntimeError(f"Cannot set up pending directory for {target_email}: {e}")

    def _get_job_dir(self, job: CodeJob) -> Path:
        """Get directory for a specific job."""
        # If this is a cross-datasite job, use the datasite path
        if hasattr(job, '_datasite_path') and job._datasite_path is not None:
            return job._datasite_path / job.status.value / str(job.uid)
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
        """Save job to local storage or original datasite location."""
        old_job = self.get_job(job.uid)
        old_status = old_job.status if old_job else None

        # Determine if this is a cross-datasite job
        if hasattr(job, '_datasite_path') and job._datasite_path is not None:
            # Cross-datasite job - work with the original datasite location
            base_queue_dir = job._datasite_path
            
            def get_cross_datasite_status_dir(status: JobStatus) -> Path:
                return base_queue_dir / status.value
            
            def get_cross_datasite_job_dir(job_status: JobStatus) -> Path:
                return get_cross_datasite_status_dir(job_status) / str(job.uid)
            
            # If status changed, move job directory to new status directory
            if old_status and old_status != job.status:
                old_job_dir = get_cross_datasite_status_dir(old_status) / str(job.uid)
                new_job_dir = get_cross_datasite_job_dir(job.status)

                if old_job_dir.exists():
                    try:
                        # Move the entire job directory
                        new_job_dir.parent.mkdir(parents=True, exist_ok=True)
                        # Ensure syft.pub.yaml exists for pending directories
                        if job.status == JobStatus.pending:
                            self._create_pending_syftperm(new_job_dir.parent)
                        if new_job_dir.exists():
                            shutil.rmtree(new_job_dir)
                        shutil.move(str(old_job_dir), str(new_job_dir))
                        logger.info(f"Moved job {job.uid} from {old_status} to {job.status} in datasite")
                    except PermissionError as e:
                        logger.error(f"Permission denied moving job {job.uid}: {e}")
                        raise RuntimeError(f"Cannot approve job - insufficient permissions to modify job in original datasite")
                    except Exception as e:
                        logger.error(f"Error moving job {job.uid}: {e}")
                        raise RuntimeError(f"Failed to move job: {e}")

            # Ensure job directory exists and save metadata
            job_dir = get_cross_datasite_job_dir(job.status)
            try:
                job_dir.mkdir(parents=True, exist_ok=True)
                # Ensure syft.pub.yaml exists for pending directories in cross-datasite jobs
                if job.status == JobStatus.pending:
                    self._create_pending_syftperm(job_dir.parent)
                job_file = job_dir / "metadata.json"

                with open(job_file, "w") as f:
                    def custom_serializer(obj):
                        if isinstance(obj, Path):
                            return str(obj)
                        elif isinstance(obj, UUID):
                            return str(obj)
                        elif isinstance(obj, datetime):
                            return obj.isoformat()
                        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

                    json.dump(job.model_dump(), f, indent=2, default=custom_serializer)
                    
                logger.info(f"Updated job {job.uid} metadata in original datasite")
                
            except PermissionError as e:
                logger.error(f"Permission denied updating job {job.uid} metadata: {e}")
                raise RuntimeError(f"Cannot approve job - insufficient permissions to update job in original datasite")
            except Exception as e:
                logger.error(f"Error updating job {job.uid} metadata: {e}")
                raise RuntimeError(f"Failed to update job metadata: {e}")
        else:
            # Local job - use original logic
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

            with open(job_file, "w") as f:

                def custom_serializer(obj):
                    if isinstance(obj, Path):
                        return str(obj)
                    elif isinstance(obj, UUID):
                        return str(obj)
                    elif isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

                json.dump(job.model_dump(), f, indent=2, default=custom_serializer)

    def list_jobs(
        self,
        target_email: Optional[str] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        search_all_datasites: bool = False,
    ) -> list[CodeJob]:
        """
        List jobs, optionally filtered.

        Args:
            target_email: Filter by target email
            status: Filter by job status
            limit: Maximum number of jobs to return
            search_all_datasites: If True, search across all datasites instead of just local queue

        Returns:
            List of matching jobs
        """
        jobs = []

        if search_all_datasites:
            # Search across all datasites for jobs where current user is target_email
            jobs = self._search_all_datasites_for_jobs(target_email, status, limit)
        else:
            # Original behavior: search only local queue directory
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

    def _search_all_datasites_for_jobs(
        self,
        target_email: Optional[str] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
    ) -> list[CodeJob]:
        """
        Search across all datasites for jobs.
        
        Args:
            target_email: Filter by target email
            status: Filter by job status
            limit: Maximum number of jobs to return
            
        Returns:
            List of matching jobs
        """
        jobs = []
        
        try:
            # Get the datasites directory
            datasites_dir = self.syftbox_client.datasites
            if not datasites_dir.exists():
                logger.warning(f"Datasites directory does not exist: {datasites_dir}")
                return jobs

            logger.debug(f"Searching for jobs across all datasites in: {datasites_dir}")

            # Iterate through all datasites
            for datasite_dir in datasites_dir.iterdir():
                if not datasite_dir.is_dir():
                    continue

                # Check if this datasite has the code queue app
                queue_dir = datasite_dir / "app_data" / self.queue_name / "jobs"
                if not queue_dir.exists():
                    continue

                logger.debug(f"Searching in datasite: {datasite_dir.name}")

                # Determine which status directories to search
                if status:
                    status_dirs = [queue_dir / status.value]
                else:
                    status_dirs = [queue_dir / s.value for s in JobStatus]

                # Search in each status directory for this datasite
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
                                
                                # Track the original datasite queue directory for cross-datasite jobs
                                job._datasite_path = queue_dir

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

                if len(jobs) >= limit:
                    break

        except Exception as e:
            logger.error(f"Error searching all datasites for jobs: {e}")

        return jobs

    def create_python_job(
        self,
        target_email: str,
        script_content: str,
        name: str,
        description: Optional[str] = None,
        requirements: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
    ) -> CodeJob:
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
                tags=tags,
            )

        finally:
            # Note: We don't delete temp_dir here because it's copied by submit_code
            # The temp directory will be cleaned up by the system later
            pass

    def create_bash_job(
        self,
        target_email: str,
        script_content: str,
        name: str,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> CodeJob:
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
            return self.submit_code(
                target_email=target_email,
                code_folder=temp_dir,
                name=name,
                description=description,
                tags=tags,
            )

        finally:
            # Note: We don't delete temp_dir here because it's copied by submit_code
            # The temp directory will be cleaned up by the system later
            pass

    def submit_code(
        self,
                    target_email: str,
                    code_folder: Path,
                    name: str,
                    description: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> CodeJob:
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
            tags=tags or [],
        )

        job = CodeJob(**job_create.model_dump(), requester_email=self.email)
        job._client = self  # Set the client reference
        
        # Set up cross-datasite job - save to target's datasite instead of requester's
        target_queue_dir = self._get_target_queue_dir(target_email)
        job._datasite_path = target_queue_dir
        
        # Ensure target's pending directory exists with proper permissions BEFORE copying/saving
        self._ensure_target_pending_directory(target_email)
        
        # Copy code to target's queue location
        self._copy_code_to_queue(job)
        
        # Save job to target's datasite queue (pending folder)
        self._save_job(job)
        
        # Set permissions using syft-perm so recipient can access the job
        self._set_job_permissions(job)
        
        logger.info(f"Submitted job '{name}' to {target_email}'s datasite")
        return job
    
    def get_job(self, job_uid: UUID) -> Optional[CodeJob]:
        """Get a job by its UID, searching locally first then across all datasites."""
        # First try to find the job locally
        job_file = self._get_job_file(job_uid)
        if job_file.exists():
            with open(job_file) as f:
                import json
                from datetime import datetime
                from uuid import UUID

                data = json.load(f)
                
                # Convert string representations back to proper types
                if "uid" in data and isinstance(data["uid"], str):
                    data["uid"] = UUID(data["uid"])
                
                for date_field in ["created_at", "updated_at", "started_at", "completed_at"]:
                    if date_field in data and data[date_field] and isinstance(data[date_field], str):
                        data[date_field] = datetime.fromisoformat(data[date_field])
                
                return CodeJob.model_validate(data)
        
        # If not found locally, search across all datasites
        logger.debug(f"Job {job_uid} not found locally, searching across all datasites")
        
        try:
            datasites_dir = self.syftbox_client.datasites
            if not datasites_dir.exists():
                return None

            # Search through all datasites
            for datasite_dir in datasites_dir.iterdir():
                if not datasite_dir.is_dir():
                    continue

                # Check if this datasite has the code queue app
                queue_dir = datasite_dir / "app_data" / self.queue_name / "jobs"
                if not queue_dir.exists():
                    continue

                # Search in all status directories for this datasite
                for status in JobStatus:
                    status_dir = queue_dir / status.value
                    if not status_dir.exists():
                        continue
                        
                    job_dir = status_dir / str(job_uid)
                    if job_dir.exists():
                        metadata_file = job_dir / "metadata.json"
                        if metadata_file.exists():
                            with open(metadata_file) as f:
                                import json
                                data = json.load(f)
                                job = CodeJob.model_validate(data)
                                job._client = self
                                # Track the original datasite path for cross-datasite operations
                                job._datasite_path = queue_dir
                                
                                logger.debug(f"Found job {job_uid} in datasite {datasite_dir.name}")
                                return job
                
        except Exception as e:
            logger.warning(f"Error searching for job {job_uid} across datasites: {e}")
        
        return None
    
    def list_my_jobs(self, limit: int = 50) -> list[CodeJob]:
        """List jobs submitted by me (searches across all datasites since jobs are stored in target's datasite)."""
        # Since jobs are now stored in the target's datasite, we need to search across all datasites
        # to find jobs that I submitted to others
        return self.list_jobs(target_email=None, limit=limit, search_all_datasites=True)

    def list_all_jobs(self, limit: int = 50) -> list[CodeJob]:
        """List jobs submitted to me (searches local datasite since jobs are now stored in target's datasite)."""
        # Since jobs are now stored in the target's datasite, jobs submitted to me 
        # will be in my local datasite
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
        """Copy code folder to the queue location (supports cross-datasite jobs)."""
        job_dir = self._get_job_dir(job)
        
        try:
            job_dir.mkdir(parents=True, exist_ok=True)
            
            # Ensure syft.pub.yaml exists for pending directories when copying to cross-datasite locations
            if (job.status == JobStatus.pending and 
                hasattr(job, '_datasite_path') and job._datasite_path is not None):
                self._create_pending_syftperm(job_dir.parent)
            
            code_dir = job_dir / "code"
            if code_dir.exists():
                shutil.rmtree(code_dir)
            
            shutil.copytree(job.code_folder, code_dir)
            job.code_folder = code_dir  # Update to queue location
            
            # Log where the code was copied
            if hasattr(job, '_datasite_path') and job._datasite_path is not None:
                logger.debug(f"Copied code to cross-datasite location: {code_dir}")
            else:
                logger.debug(f"Copied code to local location: {code_dir}")
                
        except PermissionError as e:
            logger.error(f"Permission denied copying code to {job_dir}: {e}")
            raise RuntimeError(f"Cannot submit job - insufficient permissions to create job in target datasite")
        except Exception as e:
            logger.error(f"Error copying code to {job_dir}: {e}")
            raise RuntimeError(f"Failed to copy code: {e}")

    def _set_job_permissions(self, job: CodeJob):
        """Set proper permissions for job files so the recipient can see and approve them."""
        try:
            job_dir = self._get_job_dir(job)
            
            # Set permissions for the metadata.json file
            # Target user needs write access to approve/reject (change status)
            metadata_file = job_dir / "metadata.json"
            if metadata_file.exists():
                set_file_permissions(
                    str(metadata_file),
                    read_users=[job.target_email, job.requester_email],
                    write_users=[job.target_email, job.requester_email],  # Both can modify for approval/updates
                    admin_users=[job.requester_email]  # Requester has admin rights
                )
                logger.debug(f"Set permissions for metadata file: {metadata_file}")

            # Set permissions for the entire code directory (read-only for target)
            code_dir = job_dir / "code"
            if code_dir.exists():
                # Set permissions for all files in the code directory
                for file_path in code_dir.rglob("*"):
                    if file_path.is_file():
                        set_file_permissions(
                            str(file_path),
                            read_users=[job.target_email, job.requester_email],
                            write_users=[job.requester_email],  # Only requester can modify code
                            admin_users=[job.requester_email]
                        )
                        logger.debug(f"Set permissions for code file: {file_path}")

            # Set directory-level permissions to allow job status changes
            set_file_permissions(
                str(job_dir),
                read_users=[job.target_email, job.requester_email],
                write_users=[job.target_email, job.requester_email],  # Both can modify directory for job moves
                admin_users=[job.requester_email]
            )

            logger.info(f"Successfully set permissions for job {job.uid} - {job.target_email} can now access and approve/reject the job")

        except Exception as e:
            logger.warning(f"Failed to set permissions for job {job.uid}: {e}")
            # Don't fail the job submission if permissions can't be set
            pass
    
    def approve_job(self, job_uid: Union[str, UUID], reason: Optional[str] = None) -> bool:
        """
        Approve a job for execution.
        
        The job will be moved from pending to approved within the reviewer's own datasite.

        Args:
            job_uid: The job's UUID
            reason: Optional reason for approval

        Returns:
            bool: True if approved successfully
        """
        logger.debug(f"Attempting to approve job {job_uid}")
        
        job = self.get_job(job_uid)
        if not job:
            logger.warning(f"Job {job_uid} not found")
            return False

        logger.debug(f"Found job {job_uid}: target={job.target_email}, current_user={self.email}")
        
        if job.target_email != self.email:
            logger.warning(f"Cannot approve job {job_uid} - not the target owner (target={job.target_email}, current={self.email})")
            return False

        if job.status != JobStatus.pending:
            logger.warning(f"Cannot approve job {job_uid} with status {job.status}")
            return False

        logger.debug(f"Updating job {job_uid} status from {job.status} to approved in reviewer's datasite")
        
        try:
            # Ensure the job is configured to be saved in the reviewer's own datasite
            if not hasattr(job, '_datasite_path') or job._datasite_path is None:
                # If no datasite path set, default to reviewer's own datasite
                job._datasite_path = self._get_target_queue_dir(self.email)
            
            job.update_status(JobStatus.approved)
            logger.debug(f"Saving approved job {job_uid} to reviewer's datasite")
            self._save_job(job)
            logger.info(f"Approved job '{job.name}' - moved to approved folder in {self.email}'s datasite")
            return True
        except Exception as e:
            logger.error(f"Failed to approve job {job_uid}: {e}")
            return False

    def reject_job(self, job_uid: Union[str, UUID], reason: Optional[str] = None) -> bool:
        """
        Reject a job.
        
        The job will be moved from pending to rejected within the reviewer's own datasite.

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

        try:
            # Ensure the job is configured to be saved in the reviewer's own datasite
            if not hasattr(job, '_datasite_path') or job._datasite_path is None:
                # If no datasite path set, default to reviewer's own datasite
                job._datasite_path = self._get_target_queue_dir(self.email)

            job.update_status(JobStatus.rejected, reason)
            self._save_job(job)

            logger.info(f"Rejected job '{job.name}' - moved to rejected folder in {self.email}'s datasite")
            return True
        except Exception as e:
            logger.error(f"Failed to reject job {job_uid}: {e}")
            return False

    def list_job_files(self, job_uid: Union[str, UUID]) -> list[str]:
        """
        List all files in a job's code directory.

        Args:
            job_uid: The job's UUID

        Returns:
            List of relative file paths in the job's code directory
        """
        job = self.get_job(job_uid)
        if not job:
            return []

        code_dir = self._get_job_dir(job) / "code"
        if not code_dir.exists():
            return []

        files = []
        for item in code_dir.rglob("*"):
            if item.is_file():
                # Get relative path from the code directory
                relative_path = item.relative_to(code_dir)
                files.append(str(relative_path))
        
        return sorted(files)

    def read_job_file(self, job_uid: Union[str, UUID], filename: str) -> Optional[str]:
        """
        Read the contents of a specific file in a job's code directory.

        Args:
            job_uid: The job's UUID
            filename: Relative path to the file within the code directory

        Returns:
            File contents as string, or None if file doesn't exist
        """
        job = self.get_job(job_uid)
        if not job:
            return None

        code_dir = self._get_job_dir(job) / "code"
        file_path = code_dir / filename

        # Security check: ensure the file is within the code directory
        try:
            file_path.resolve().relative_to(code_dir.resolve())
        except ValueError:
            logger.warning(f"Attempted to access file outside code directory: {filename}")
            return None

        if not file_path.exists() or not file_path.is_file():
            return None

        try:
            return file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # For binary files, return a placeholder
            return f"<Binary file: {filename}>"
        except Exception as e:
            logger.warning(f"Error reading file {filename}: {e}")
            return None

    def get_job_code_structure(self, job_uid: Union[str, UUID]) -> dict:
        """
        Get a comprehensive view of a job's code structure including file contents.

        Args:
            job_uid: The job's UUID

        Returns:
            Dictionary containing file structure and contents
        """
        job = self.get_job(job_uid)
        if not job:
            return {}

        code_dir = self._get_job_dir(job) / "code"
        if not code_dir.exists():
            return {"error": "Code directory not found"}

        structure = {
            "files": {},
            "directories": [],
            "total_files": 0,
            "has_run_script": False,
            "run_script_content": None,
        }

        # Walk through all files and directories
        for item in code_dir.rglob("*"):
            relative_path = str(item.relative_to(code_dir))
            
            if item.is_file():
                structure["total_files"] += 1
                
                # Read file content
                try:
                    content = item.read_text(encoding='utf-8')
                    structure["files"][relative_path] = {
                        "content": content,
                        "size": len(content),
                        "lines": len(content.splitlines()),
                        "type": "text"
                    }
                except UnicodeDecodeError:
                    structure["files"][relative_path] = {
                        "content": f"<Binary file: {item.stat().st_size} bytes>",
                        "size": item.stat().st_size,
                        "lines": 0,
                        "type": "binary"
                    }
                except Exception as e:
                    structure["files"][relative_path] = {
                        "content": f"<Error reading file: {e}>",
                        "size": 0,
                        "lines": 0,
                        "type": "error"
                    }
                
                # Check for run script
                if relative_path in ("run.sh", "run.py", "run.bash"):
                    structure["has_run_script"] = True
                    if structure["files"][relative_path]["type"] == "text":
                        structure["run_script_content"] = structure["files"][relative_path]["content"]
            
            elif item.is_dir():
                structure["directories"].append(relative_path)

        return structure

    def list_job_output_files(self, job_uid: Union[str, UUID]) -> list[str]:
        """
        List all files in a job's output directory.

        Args:
            job_uid: The job's UUID

        Returns:
            List of relative file paths in the job's output directory
        """
        job = self.get_job(job_uid)
        if not job or not job.output_folder:
            return []

        output_dir = Path(job.output_folder)
        if not output_dir.exists():
            return []

        files = []
        try:
            for item in output_dir.rglob("*"):
                if item.is_file():
                    # Get relative path from the output directory
                    relative_path = item.relative_to(output_dir)
                    files.append(str(relative_path))
        except Exception as e:
            logger.warning(f"Error listing output files for job {job_uid}: {e}")
            return []
        
        return sorted(files)

    def read_job_output_file(self, job_uid: Union[str, UUID], filename: str) -> Optional[str]:
        """
        Read the contents of a specific file in a job's output directory.

        Args:
            job_uid: The job's UUID
            filename: Relative path to the file within the output directory

        Returns:
            File contents as string, or None if file doesn't exist
        """
        job = self.get_job(job_uid)
        if not job or not job.output_folder:
            return None

        output_dir = Path(job.output_folder)
        file_path = output_dir / filename

        # Security check: ensure the file is within the output directory
        try:
            file_path.resolve().relative_to(output_dir.resolve())
        except ValueError:
            logger.warning(f"Attempted to access file outside output directory: {filename}")
            return None

        if not file_path.exists() or not file_path.is_file():
            return None

        try:
            return file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # For binary files, return a placeholder
            return f"<Binary file: {filename}>"
        except Exception as e:
            logger.warning(f"Error reading output file {filename}: {e}")
            return None


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
