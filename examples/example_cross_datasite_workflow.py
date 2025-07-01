#!/usr/bin/env python3
"""
Example demonstrating the new cross-datasite workflow for syft-code-queue.

Cross-Datasite Workflow:
1. Job Creation: Jobs are submitted to the TARGET's datasite "pending" folder
2. Job Review: Approved/rejected jobs move within the REVIEWER's own datasite
3. Job Discovery:
   - list_all_jobs() finds jobs submitted TO you (in your local datasite)
   - list_my_jobs() finds jobs submitted BY you (searches across all datasites)
"""

import tempfile
from pathlib import Path

from syft_code_queue import create_client


def demonstrate_cross_datasite_workflow():
    """Demonstrate the new cross-datasite job workflow."""

    print("=== Cross-Datasite Job Workflow Demo ===\n")

    # Example scenario: Alice submits a job to Bob
    alice_email = "alice@example.com"
    bob_email = "bob@example.com"

    print(f"Scenario: {alice_email} submits a job to {bob_email}")
    print("Expected behavior:")
    print(f"  1. Job gets created in {bob_email}'s datasite 'pending' folder")
    print(f"  2. When {bob_email} approves, it moves to {bob_email}'s 'approved' folder")
    print(f"  3. {alice_email} can find her submitted jobs by searching across datasites")
    print(f"  4. {bob_email} can find jobs submitted to him in his local datasite\n")

    # Create a simple test script
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test code files
        script_content = """
print("Hello from cross-datasite job!")
print("Processing data...")
with open("output.txt", "w") as f:
    f.write("Job completed successfully!")
"""

        script_file = temp_path / "analyze.py"
        script_file.write_text(script_content)

        # Create run script
        run_script = temp_path / "run.sh"
        run_script.write_text("#!/bin/bash\nset -e\npython analyze.py\n")
        run_script.chmod(0o755)

        print("=== Alice submitting job to Bob ===")
        try:
            # Alice creates a client and submits job to Bob
            alice_client = create_client()
            # Note: In real usage, you'd set up proper SyftBoxClient with alice's credentials

            print("Alice submitting job to Bob's datasite...")
            job = alice_client.submit_code(
                target_email=bob_email,
                code_folder=temp_path,
                name="Data Analysis Job",
                description="Cross-datasite analysis job",
                tags=["analysis", "demo"],
            )

            print(f"✅ Job {job.uid} created successfully!")
            print(f"   - Job stored in: {bob_email}'s datasite/pending/{job.uid}/")
            print(f"   - Status: {job.status}")
            print(f"   - Requester: {job.requester_email}")
            print(f"   - Target: {job.target_email}")

        except Exception as e:
            print(f"❌ Error creating job: {e}")
            print("Note: This demo requires proper SyftBox setup with multiple datasites")

        print("\n=== Bob reviewing and approving job ===")
        try:
            # Bob creates a client and finds jobs submitted to him
            bob_client = create_client()
            # Note: In real usage, you'd set up proper SyftBoxClient with bob's credentials

            print("Bob checking jobs submitted to him...")
            jobs_to_bob = bob_client.list_all_jobs()
            print(f"Found {len(jobs_to_bob)} jobs submitted to Bob")

            if jobs_to_bob:
                job_to_approve = jobs_to_bob[0]
                print(f"Bob approving job: {job_to_approve.name}")

                success = bob_client.approve_job(job_to_approve.uid)
                if success:
                    print("✅ Job approved!")
                    print(
                        f"   - Job moved to: {bob_email}'s datasite/approved/{job_to_approve.uid}/"
                    )
                else:
                    print("❌ Failed to approve job")

        except Exception as e:
            print(f"❌ Error in approval workflow: {e}")
            print("Note: This demo requires proper SyftBox setup with multiple datasites")

        print("\n=== Alice checking her submitted jobs ===")
        try:
            # Alice checks jobs she submitted
            print("Alice checking jobs she submitted...")
            alice_jobs = alice_client.list_my_jobs()
            print(f"Found {len(alice_jobs)} jobs submitted by Alice")

            for job in alice_jobs:
                print(f"  - Job: {job.name}")
                print(f"    Status: {job.status}")
                print(f"    Target: {job.target_email}")
                print(f"    Location: {job.target_email}'s datasite/{job.status}/{job.uid}/")

        except Exception as e:
            print(f"❌ Error checking Alice's jobs: {e}")
            print("Note: This demo requires proper SyftBox setup with multiple datasites")

    print("\n=== Summary ===")
    print("The new cross-datasite workflow ensures:")
    print("✅ Jobs are stored in the target user's datasite")
    print("✅ Job reviews happen within the reviewer's own datasite")
    print("✅ Proper job discovery across datasites")
    print("✅ Clear separation of job ownership and storage")


if __name__ == "__main__":
    demonstrate_cross_datasite_workflow()
