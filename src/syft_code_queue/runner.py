"""Simple code execution runner for syft-code-queue."""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger

from .models import CodeJob, JobStatus


class CodeRunner:
    """Simple runner that executes code in folders with run.sh."""
    
    def __init__(self, timeout: int = 300, max_output_size: int = 10 * 1024 * 1024):  # 10MB
        """
        Initialize the code runner.
        
        Args:
            timeout: Maximum execution time in seconds
            max_output_size: Maximum output size in bytes
        """
        self.timeout = timeout
        self.max_output_size = max_output_size
    
    def run_job(self, job: CodeJob) -> Tuple[int, str, str]:
        """
        Execute a code job.
        
        Args:
            job: The CodeJob to execute
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        code_dir = job.code_folder
        run_script = code_dir / "run.sh"
        
        if not run_script.exists():
            raise ValueError(f"run.sh not found in {code_dir}")
        
        # Create output directory
        output_dir = self._create_output_dir(job)
        
        # Make run.sh executable
        os.chmod(run_script, 0o755)
        
        # Set up environment
        env = os.environ.copy()
        env["SYFT_JOB_ID"] = str(job.uid)
        env["SYFT_JOB_NAME"] = job.name
        env["SYFT_OUTPUT_DIR"] = str(output_dir)
        env["SYFT_REQUESTER"] = job.requester_email
        
        # Create log file
        log_file = self._get_job_dir(job) / "execution.log"
        
        logger.info(f"Starting execution of job {job.uid} in {code_dir}")
        
        try:
            # Start the process
            process = subprocess.Popen(
                ["bash", "run.sh"],
                cwd=code_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Monitor execution with timeout
            start_time = time.time()
            stdout_lines = []
            stderr_lines = []
            
            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
                exit_code = process.returncode
                
                # Check output size
                if len(stdout) > self.max_output_size:
                    stdout = stdout[:self.max_output_size] + "\n[OUTPUT TRUNCATED - TOO LARGE]"
                if len(stderr) > self.max_output_size:
                    stderr = stderr[:self.max_output_size] + "\n[ERROR OUTPUT TRUNCATED - TOO LARGE]"
                
            except subprocess.TimeoutExpired:
                logger.warning(f"Job {job.uid} timed out after {self.timeout}s")
                process.kill()
                stdout, stderr = process.communicate()
                exit_code = -1
                stderr += f"\n[JOB TERMINATED - TIMEOUT AFTER {self.timeout}s]"
            
            # Write execution log
            duration = time.time() - start_time
            with open(log_file, 'w') as f:
                f.write(f"Job: {job.name} ({job.uid})\n")
                f.write(f"Requester: {job.requester_email}\n")
                f.write(f"Started: {job.started_at}\n")
                f.write(f"Duration: {duration:.2f}s\n")
                f.write(f"Exit Code: {exit_code}\n")
                f.write("-" * 50 + "\n")
                f.write("STDOUT:\n")
                f.write(stdout)
                f.write("\n" + "-" * 50 + "\n")
                f.write("STDERR:\n")
                f.write(stderr)
            
            # Update job with output location
            job.output_folder = output_dir
            job.exit_code = exit_code
            
            logger.info(f"Job {job.uid} completed with exit code {exit_code} in {duration:.2f}s")
            return exit_code, stdout, stderr
            
        except Exception as e:
            error_msg = f"Failed to execute job {job.uid}: {e}"
            logger.error(error_msg)
            
            # Write error log
            with open(log_file, 'w') as f:
                f.write(f"Job: {job.name} ({job.uid})\n")
                f.write(f"EXECUTION FAILED: {error_msg}\n")
            
            return -1, "", str(e)
    
    def _create_output_dir(self, job: CodeJob) -> Path:
        """Create output directory for the job."""
        output_dir = self._get_job_dir(job) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def _get_job_dir(self, job: CodeJob) -> Path:
        """Get the directory for a job."""
        # This should match the client's job directory structure
        from syft_core import Client as SyftBoxClient
        client = SyftBoxClient.load()
        return client.app_data("code-queue") / "jobs" / str(job.uid)


class SafeCodeRunner(CodeRunner):
    """A more secure version of CodeRunner with additional safety measures."""
    
    def __init__(self, 
                 timeout: int = 300,
                 max_output_size: int = 10 * 1024 * 1024,
                 allowed_commands: Optional[list] = None,
                 blocked_commands: Optional[list] = None):
        """
        Initialize the safe code runner.
        
        Args:
            timeout: Maximum execution time in seconds
            max_output_size: Maximum output size in bytes
            allowed_commands: List of allowed commands (whitelist)
            blocked_commands: List of blocked commands (blacklist)
        """
        super().__init__(timeout, max_output_size)
        self.allowed_commands = allowed_commands
        self.blocked_commands = blocked_commands or [
            "rm", "rmdir", "del", "format", "fdisk", "mkfs",
            "dd", "chmod", "chown", "sudo", "su", "passwd",
            "crontab", "at", "systemctl", "service"
        ]
    
    def run_job(self, job: CodeJob) -> Tuple[int, str, str]:
        """Execute a job with additional security checks."""
        # Read and validate the run.sh script
        run_script = job.code_folder / "run.sh"
        
        if not self._validate_script(run_script):
            error_msg = "Script contains potentially dangerous commands"
            logger.warning(f"Job {job.uid} rejected: {error_msg}")
            return -1, "", error_msg
        
        return super().run_job(job)
    
    def _validate_script(self, script_path: Path) -> bool:
        """Validate that the script is safe to execute."""
        try:
            content = script_path.read_text().lower()
            
            # Check for blocked commands
            for blocked in self.blocked_commands:
                if blocked in content:
                    logger.warning(f"Script contains blocked command: {blocked}")
                    return False
            
            # If whitelist is specified, check allowed commands
            if self.allowed_commands:
                # This is a simplified check - in production you'd want more sophisticated parsing
                for line in content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        command = line.split()[0] if line.split() else ""
                        if command and command not in self.allowed_commands:
                            logger.warning(f"Script contains non-whitelisted command: {command}")
                            return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate script: {e}")
            return False 