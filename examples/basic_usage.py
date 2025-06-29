#!/usr/bin/env python3
"""
Basic usage example for syft-code-queue.

This example shows how to:
1. Submit code for execution on a remote datasite
2. Check job status
3. Retrieve results
"""

import time
from pathlib import Path
from tempfile import TemporaryDirectory

import syft_code_queue as scq


def create_example_code():
    """Create a simple example code folder with run.sh."""
    temp_dir = Path(TemporaryDirectory().name)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a simple run.sh script
    run_script = temp_dir / "run.sh"
    run_script.write_text("""#!/bin/bash

echo "Starting simple data analysis job..."
echo "Job ID: $SYFT_JOB_ID"
echo "Requester: $SYFT_REQUESTER"
echo "Output directory: $SYFT_OUTPUT_DIR"

# Do some simple analysis
echo "Analyzing data..."
sleep 2

# Create some output
echo "Analysis complete!" > "$SYFT_OUTPUT_DIR/result.txt"
echo "Found 42 interesting patterns" >> "$SYFT_OUTPUT_DIR/result.txt"

# Generate a simple report
cat > "$SYFT_OUTPUT_DIR/report.md" << EOF
# Analysis Report

## Summary
Successfully completed data analysis.

## Results
- Processed dataset
- Found 42 interesting patterns
- Generated insights

## Timestamp
$(date)
EOF

echo "Job completed successfully!"
""")
    
    # Make it executable
    run_script.chmod(0o755)
    
    return temp_dir


def main():
    """Demonstrate basic usage of syft-code-queue."""
    
    print("🚀 Syft Code Queue - Basic Usage Example")
    print("=" * 50)
    
    # Create example code
    print("1. Creating example code folder...")
    code_folder = create_example_code()
    print(f"   Created: {code_folder}")
    
    # Submit job
    print("\n2. Submitting job to remote datasite...")
    target_email = "data-owner@example.com"  # Replace with actual email
    
    job = scq.submit_code(
        target_email=target_email,
        code_folder=code_folder,
        name="Simple Data Analysis",
        description="Basic analysis job for demonstration",
        tags=["data-analysis", "demo"],
        auto_approval=True  # Allow auto-approval if rules permit
    )
    
    print(f"   Job submitted!")
    print(f"   Job ID: {job.uid}")
    print(f"   Status: {job.status.value}")
    
    # Check status
    print("\n3. Monitoring job status...")
    client = scq.create_client()
    
    for i in range(30):  # Check for up to 30 seconds
        current_job = client.get_job(job.uid)
        if not current_job:
            print("   Job not found!")
            break
            
        print(f"   Status: {current_job.status.value}")
        
        if current_job.is_terminal:
            if current_job.status == scq.JobStatus.completed:
                print("   ✅ Job completed successfully!")
                
                # Get results
                output_path = client.get_job_output(job.uid)
                if output_path and output_path.exists():
                    print(f"   📁 Output: {output_path}")
                    
                    # Show results
                    result_file = output_path / "result.txt"
                    if result_file.exists():
                        print(f"   📄 Result: {result_file.read_text()}")
                
                # Show logs
                logs = client.get_job_logs(job.uid)
                if logs:
                    print("\n📋 Execution logs:")
                    print("-" * 30)
                    print(logs)
                
            elif current_job.status == scq.JobStatus.failed:
                print("   ❌ Job failed!")
                if current_job.error_message:
                    print(f"   Error: {current_job.error_message}")
                    
            elif current_job.status == scq.JobStatus.rejected:
                print("   🚫 Job was rejected")
                if current_job.error_message:
                    print(f"   Reason: {current_job.error_message}")
            
            break
        
        time.sleep(1)
    else:
        print("   ⏰ Timeout waiting for job completion")
    
    # List recent jobs
    print("\n4. Recent jobs:")
    recent_jobs = client.list_jobs(limit=5)
    for job in recent_jobs:
        print(f"   - {job.name} ({job.status.value}) - {job.created_at}")
    
    print("\n✅ Example completed!")


def server_example():
    """Example of running a queue server."""
    print("\n🖥️  Starting Queue Server Example")
    print("=" * 50)
    
    def custom_approval_rules(job):
        """Custom auto-approval logic."""
        # Auto-approve demo jobs
        if "demo" in job.tags:
            print(f"Auto-approving demo job: {job.name}")
            return True
        
        # Auto-approve from trusted users
        trusted_users = ["trusted@example.com"]
        if job.requester_email in trusted_users:
            print(f"Auto-approving job from trusted user: {job.requester_email}")
            return True
        
        return False
    
    # Create and start server
    server = scq.create_server(
        auto_approval_callback=custom_approval_rules,
        max_concurrent_jobs=2,
        job_timeout=600  # 10 minutes
    )
    
    print("Starting server...")
    server.start()
    
    try:
        # Show pending jobs
        pending = server.list_pending_jobs()
        print(f"Pending jobs: {len(pending)}")
        
        # Run for a bit
        print("Server running... (Ctrl+C to stop)")
        time.sleep(60)
        
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.stop()
        print("Server stopped.")


if __name__ == "__main__":
    main()
    
    # Uncomment to run server example
    # server_example() 