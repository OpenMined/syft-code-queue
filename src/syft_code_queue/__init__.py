"""
syft-code-queue: Simple code execution queue for SyftBox.

This package provides a lightweight way to submit code for execution on remote datasites.
Code is submitted as folders containing a run.sh script, and executed in a secure queue system.
"""

from .client import CodeQueueClient, create_client
from .models import CodeJob, JobStatus, QueueConfig
from .runner import CodeRunner, SafeCodeRunner
from .server import CodeQueueServer, create_server

__version__ = "0.1.0"
__all__ = [
    # Client API
    "CodeQueueClient",
    "create_client",
    
    # Server API
    "CodeQueueServer", 
    "create_server",
    
    # Models
    "CodeJob",
    "JobStatus",
    "QueueConfig",
    
    # Runners
    "CodeRunner",
    "SafeCodeRunner",
]

# Convenience functions
def submit_code(target_email: str, code_folder, name: str, **kwargs) -> CodeJob:
    """
    Quick way to submit code for execution.
    
    Args:
        target_email: Email of the data owner
        code_folder: Path to folder containing run.sh
        name: Name for the job
        **kwargs: Additional arguments passed to submit_code
        
    Returns:
        CodeJob: The submitted job
    """
    client = create_client()
    return client.submit_code(target_email, code_folder, name, **kwargs)


def start_queue_server(**config_kwargs) -> CodeQueueServer:
    """
    Quick way to start a queue processing server.
    
    Args:
        **config_kwargs: Configuration options
        
    Returns:
        CodeQueueServer: The started server
    """
    server = create_server(**config_kwargs)
    server.start()
    return server 