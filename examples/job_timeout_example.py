#!/usr/bin/env python3
"""
Job Timeout Example

This example demonstrates how to use job timeouts in syft-code-queue.
All jobs now have a timeout parameter that defaults to 24 hours (86400 seconds).
"""

import syft_code_queue as scq
from pathlib import Path
import tempfile

def main():
    print("=== Job Timeout Example ===\n")
    
    # Example 1: Submit job with default timeout (24 hours)
    print("1. Submit job with default timeout (24 hours)...")
    
    # Create a simple test script
    temp_dir = Path(tempfile.mkdtemp())
    run_script = temp_dir / "run.sh"
    run_script.write_text("#!/bin/bash\necho 'Hello from timeout example'\n")
    run_script.chmod(0o755)
    
    try:
        # Submit with default timeout
        # job = scq.q.submit_job(
        #     target_email="dataowner@example.com",
        #     code_folder=temp_dir,
        #     name="default_timeout_job"
        # )
        print("   ✓ Would submit job with 24-hour timeout")
    except Exception as e:
        print(f"   Note: {e}")
    
    # Example 2: Submit job with custom timeout (1 hour)
    print("\n2. Submit job with custom timeout (1 hour)...")
    
    try:
        # Submit with 1-hour timeout
        # job = scq.q.submit_job(
        #     target_email="dataowner@example.com",
        #     code_folder=temp_dir,
        #     name="short_timeout_job",
        #     timeout_seconds=3600  # 1 hour
        # )
        print("   ✓ Would submit job with 1-hour timeout")
    except Exception as e:
        print(f"   Note: {e}")
    
    # Example 3: Submit Python job with custom timeout
    print("\n3. Submit Python job with custom timeout...")
    
    python_script = '''
import time
print("Starting long-running analysis...")
time.sleep(10)  # Simulate work
print("Analysis complete!")
'''
    
    try:
        # job = scq.q.submit_python(
        #     target_email="dataowner@example.com",
        #     script_content=python_script,
        #     name="python_timeout_job",
        #     timeout_seconds=1800,  # 30 minutes
        #     requirements=["numpy", "pandas"]
        # )
        print("   ✓ Would submit Python job with 30-minute timeout")
    except Exception as e:
        print(f"   Note: {e}")
    
    # Example 4: Check job timeout status
    print("\n4. Checking job timeout properties...")
    
    from syft_code_queue.models import CodeJob, JobCreate
    from datetime import datetime, timedelta
    
    # Create a sample job to demonstrate timeout checking
    job_create = JobCreate(
        name="demo_job",
        target_email="dataowner@example.com",
        code_folder=temp_dir,
        timeout_seconds=3600  # 1 hour
    )
    
    job = CodeJob(**job_create.model_dump(), requester_email="scientist@example.com")
    
    print(f"   ✓ Job timeout: {job.timeout_seconds} seconds")
    print(f"   ✓ Job is expired: {job.is_expired}")
    print(f"   ✓ Time remaining: {job.time_remaining} seconds")
    print(f"   ✓ Would become: {job.get_timeout_status()} if expired")
    
    # Simulate an expired job
    job.created_at = datetime.now() - timedelta(hours=2)  # 2 hours ago
    print(f"\n   After 2 hours (past 1-hour timeout):")
    print(f"   ✓ Job is expired: {job.is_expired}")
    print(f"   ✓ Time remaining: {job.time_remaining} seconds")
    print(f"   ✓ Would become: {job.get_timeout_status()}")
    
    print("\n=== Timeout Behavior ===")
    print("• Pending jobs that timeout → timedout (datasite owner never responded)")
    print("• Approved/running jobs that timeout → failed (execution timeout)")
    print("• Terminal jobs (completed/failed/rejected) cannot expire")
    print("• Cleanup runs automatically on every syft-code-queue import")
    
    print("\n=== Available Timeout Settings ===")
    print("• 1 hour: timeout_seconds=3600")
    print("• 6 hours: timeout_seconds=21600") 
    print("• 12 hours: timeout_seconds=43200")
    print("• 24 hours: timeout_seconds=86400 (default)")
    print("• 48 hours: timeout_seconds=172800")
    print("• 1 week: timeout_seconds=604800")

if __name__ == "__main__":
    main() 