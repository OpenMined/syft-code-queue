#!/usr/bin/env python3
"""Test script to verify pending_for_others searches across all datasites."""

import sys
import importlib

# Force reload of the module to pick up our changes
if 'syft_code_queue' in sys.modules:
    importlib.reload(sys.modules['syft_code_queue'])

import syft_code_queue as q

def test_pending_for_others():
    """Test that pending_for_others searches across all datasites."""
    print("🔍 Testing pending_for_others cross-datasite search...")
    
    # Test the old behavior vs new behavior
    # Get the current user email from the global API instance
    current_email = q.jobs.email
    print(f"📧 Current user email: {current_email}")
    
    # Get pending jobs for others using the new implementation
    pending_jobs = q.pending_for_others
    print(f"📋 Found {len(pending_jobs)} pending jobs I've submitted to others")
    
    for i, job in enumerate(pending_jobs):
        print(f"\n--- Job {i+1}: {job.name} ---")
        print(f"  📧 Requester: {job.requester_email}")
        print(f"  📧 Target: {job.target_email}")
        print(f"  📊 Status: {job.status}")
        print(f"  🔗 Has client: {job._client is not None}")
        print(f"  🌐 Has datasite path: {hasattr(job, '_datasite_path') and job._datasite_path is not None}")
        
        # Verify this is actually my job
        if job.requester_email == current_email:
            print("  ✅ Correctly identified as my job")
        else:
            print("  ❌ Error: This should be my job but requester doesn't match!")
    
    # Test my_pending alias
    my_pending_jobs = q.my_pending
    print(f"\n🔄 my_pending alias returned {len(my_pending_jobs)} jobs")
    
    if len(pending_jobs) == len(my_pending_jobs):
        print("✅ my_pending and pending_for_others return same number of jobs")
    else:
        print("❌ my_pending and pending_for_others mismatch!")
    
    # Test that it's different from local-only search
    try:
        # Get jobs using the old method (local only)
        local_jobs = q.list_jobs(status=q.JobStatus.pending, search_all_datasites=False)
        local_my_jobs = [job for job in local_jobs if job.requester_email == current_email]
        
        print(f"\n📍 Local-only search found {len(local_my_jobs)} pending jobs I submitted")
        print(f"🌐 Cross-datasite search found {len(pending_jobs)} pending jobs I submitted")
        
        if len(pending_jobs) >= len(local_my_jobs):
            print("✅ Cross-datasite search found same or more jobs than local-only")
        else:
            print("⚠️ Cross-datasite search found fewer jobs than local-only - unexpected!")
            
    except Exception as e:
        print(f"⚠️ Could not compare with local search: {e}")
    
    print("\n🎉 pending_for_others cross-datasite search test completed!")
    
    return pending_jobs

if __name__ == "__main__":
    jobs = test_pending_for_others()
    
    if jobs:
        print(f"\n💡 Found {len(jobs)} pending jobs. You can review them with:")
        for job in jobs:
            print(f"   q.get_job('{job.uid}').review()")
    else:
        print("\n💡 No pending jobs found. Submit a job to test:\n   q.submit_python('target@example.com', 'print(\"test\")', 'Test Job')") 