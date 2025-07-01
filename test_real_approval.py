#!/usr/bin/env python3
"""
Test script for real cross-datasite job approval with proper permissions.
"""

import sys
from pathlib import Path

# Add the src directory to the path so we can import the module
sys.path.insert(0, str(Path(__file__).parent / "src"))

import syft_code_queue


def main():
    print("🔍 Testing cross-datasite job approval with proper permissions...")

    q = syft_code_queue.jobs
    print(f"Current user: {q.email}")
    print()

    # Get pending jobs
    pending_jobs = q.pending_for_me
    print(f"Found {len(pending_jobs)} pending jobs")

    if len(pending_jobs) == 0:
        print("ℹ️  No pending jobs to test with.")
        print("   To test: Have someone submit a job to you using the new version")
        return

    # Show the first few jobs
    for i, job in enumerate(pending_jobs[:3]):
        print(f"{i + 1}. {job.name}")
        print(f"   From: {job.requester_email}")
        print(f"   Status: {job.status}")

        # Check if this job has proper permissions (syft-perm creates these automatically)
        if hasattr(job, "_datasite_path") and job._datasite_path is not None:
            job_dir = job._datasite_path / "pending" / str(job.uid)
            syft_pub_path = job_dir / "syft.pub.yaml"

            if syft_pub_path.exists():
                print("   ✅ Has syft.pub.yaml permissions (syft-perm managed)")
            else:
                print(
                    "   ❌ Missing syft.pub.yaml (old job - needs resubmission with new version)"
                )
        print()

    # Optionally approve the first job
    if len(pending_jobs) > 0:
        first_job = pending_jobs[0]
        response = input(f"Approve '{first_job.name}'? (y/N): ")

        if response.lower() in ["y", "yes"]:
            try:
                result = first_job.approve("Approved via test script")
                if result:
                    print("✅ Job approved successfully!")
                    print("   Check the original datasite for the approved folder")
                else:
                    print("❌ Job approval failed")
            except Exception as e:
                print(f"❌ Approval failed with error: {e}")


if __name__ == "__main__":
    main()
