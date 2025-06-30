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
            self.email = self._detect_user_email()
        
        def _detect_user_email(self):
            """Try to detect the user's email from SyftBox directory structure."""
            import os
            
            # Try to find user's own datasite directory
            possible_datasites_dirs = [
                Path.home() / "SyftBox" / "datasites",
                Path("/Users") / os.getlogin() / "SyftBox" / "datasites" if hasattr(os, 'getlogin') else None,
            ]
            
            for datasites_dir in possible_datasites_dirs:
                if datasites_dir and datasites_dir.exists():
                    # First try to find liamtrask@gmail.com specifically
                    liam_email = "liamtrask@gmail.com"
                    if (datasites_dir / liam_email).exists():
                        return liam_email
                    
                    # Look for common user email patterns in datasite names
                    # Check if there's a datasite that looks like it could be the current user's
                    for datasite in datasites_dir.iterdir():
                        if datasite.is_dir():
                            datasite_name = datasite.name.lower()
                            # Check for common patterns that might indicate the current user
                            if any(pattern in datasite_name for pattern in ['liam', 'trask']):
                                return datasite.name
            
            # Fallback to demo email
            return "demo@example.com"
        
        def app_data(self, app_name):
            import tempfile
            from pathlib import Path

            return Path(tempfile.gettempdir()) / f"syftbox_demo_{app_name}"
        
        @property
        def datasites(self):
            """Return the SyftBox datasites directory if it exists, otherwise a temp directory."""
            from pathlib import Path
            import os
            
            # Try to find the actual SyftBox directory
            possible_paths = [
                Path.home() / "SyftBox" / "datasites",
                Path("/Users") / os.getlogin() / "SyftBox" / "datasites" if hasattr(os, 'getlogin') else None,
                Path("/tmp/syftbox_demo_datasites")  # Fallback
            ]
            
            for path in possible_paths:
                if path and path.exists():
                    return path
            
            # Create a fallback temp directory
            fallback = Path("/tmp/syftbox_demo_datasites")
            fallback.mkdir(exist_ok=True)
            return fallback
        
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
        
        # Copy code to queue location
        self._copy_code_to_queue(job)
        
        # Save job to local queue
        self._save_job(job)
        
        # Set up permissions for cross-datasite job approval
        self._setup_job_permissions(job)
        
        logger.info(f"Submitted job '{name}' to {target_email}")
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

        logger.debug(f"Updating job {job_uid} status from {job.status} to approved")
        
        try:
            job.update_status(JobStatus.approved)
            logger.debug(f"Saving job {job_uid} with new status")
            self._save_job(job)
            logger.info(f"Approved job: {job.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to approve job {job_uid}: {e}")
            return False

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

    def _setup_job_permissions(self, job: CodeJob):
        """Set up permissions for cross-datasite job approval."""
        try:
            target_email = job.target_email
            requester_email = job.requester_email
            
            if target_email and target_email != requester_email:
                # Create syft.pub.yaml for the specific job directory
                job_dir = self._get_job_dir(job)
                syft_pub_path = job_dir / "syft.pub.yaml"
                
                # Create permission rules that allow target user to approve/reject
                permission_content = {
                    "rules": [
                        {
                            "pattern": "**",  # All files in this job directory
                            "access": {
                                "read": [requester_email, target_email],
                                "write": [target_email],  # Target can approve/reject
                                "admin": [requester_email]  # Requester keeps admin rights
                            }
                        }
                    ]
                }
                
                # Write the syft.pub.yaml file
                import yaml
                with open(syft_pub_path, "w") as f:
                    yaml.dump(permission_content, f, default_flow_style=False, sort_keys=False, indent=2)
                
                logger.info(f"Created syft.pub.yaml for job {job.uid} - {target_email} can now approve/reject")
                
                # Also create permissions for the status directories if they don't exist
                queue_dir = self._get_queue_dir()
                for status in JobStatus:
                    status_dir = queue_dir / status.value
                    status_dir.mkdir(parents=True, exist_ok=True)
                    
                    status_syft_pub = status_dir / "syft.pub.yaml"
                    if not status_syft_pub.exists():
                        # Create permissive rules for status directories
                        status_permission_content = {
                            "rules": [
                                {
                                    "pattern": "**",
                                    "access": {
                                        "read": ["*"],  # Anyone can read job listings
                                        "write": ["*"], # Anyone can move jobs between statuses
                                        "admin": [requester_email]
                                    }
                                }
                            ]
                        }
                        
                        with open(status_syft_pub, "w") as f:
                            yaml.dump(status_permission_content, f, default_flow_style=False, sort_keys=False, indent=2)
                        
                        logger.debug(f"Created syft.pub.yaml for status directory: {status.value}")
                
        except Exception as e:
            logger.warning(f"Could not set up job permissions: {e}")
            # Don't fail job submission if permission setup fails
            import traceback
            logger.debug(f"Permission setup error details: {traceback.format_exc()}")


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
