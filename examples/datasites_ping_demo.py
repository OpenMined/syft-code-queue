#!/usr/bin/env python3
"""
Demo script showing the new ping API on datasites collections.

Shows how to:
1. Ping all datasites: q.datasites.ping()
2. Ping only responsive datasites: q.datasites.responsive_to_me().ping()
3. Ping datasites with pending jobs: q.datasites.with_pending_jobs().ping()
4. Sort and then ping: q.datasites.sort_by('total_jobs').ping()
"""

import sys
import time
from pathlib import Path

# Add the src directory to the path so we can import syft_code_queue
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import syft_code_queue as scq

def main():
    print("🏓 SyftBox Code Queue - Datasites Ping Demo")
    print("=" * 55)
    
    # Show current datasites
    print("\n📡 Current Datasites (sorted by last response to me):")
    try:
        print(scq.q.datasites)
        datasites_count = len(scq.q.datasites)
    except Exception as e:
        print(f"Error getting datasites: {e}")
        return
    
    if datasites_count == 0:
        print("No datasites found. Make sure SyftBox is running and you have other datasites.")
        return
    
    print(f"\n🎯 Demo Options:")
    print("1. Ping all datasites")
    print("2. Ping only responsive datasites")
    print("3. Ping datasites with pending jobs")
    print("4. Ping top datasites by job count")
    print("5. Include yourself in ping")
    
    choice = input("\nSelect option (1-5) or press Enter for option 1: ").strip() or "1"
    
    try:
        if choice == "1":
            print("\n🏓 Pinging all datasites...")
            result = scq.q.datasites.ping(timeout_minutes=5)
            
        elif choice == "2":
            responsive = scq.q.datasites.responsive_to_me()
            print(f"\n🏓 Pinging {len(responsive)} responsive datasites...")
            if len(responsive) > 0:
                result = responsive.ping(timeout_minutes=5)
            else:
                print("No responsive datasites found!")
                return
                
        elif choice == "3":
            pending = scq.q.datasites.with_pending_jobs()
            print(f"\n🏓 Pinging {len(pending)} datasites with pending jobs...")
            if len(pending) > 0:
                result = pending.ping(timeout_minutes=5)
            else:
                print("No datasites with pending jobs found!")
                return
                
        elif choice == "4":
            top_sites = scq.q.datasites.sort_by('total_jobs', reverse=True)[:3]
            print(f"\n🏓 Pinging top {len(top_sites)} datasites by job count...")
            if len(top_sites) > 0:
                result = top_sites.ping(timeout_minutes=5)
            else:
                print("No datasites found!")
                return
                
        elif choice == "5":
            print("\n🏓 Pinging all datasites (including yourself)...")
            result = scq.q.datasites.ping(timeout_minutes=5, include_self=True)
            
        else:
            print("Invalid choice!")
            return
        
        # Display results
        print(f"\n✅ Ping Results:")
        print(f"   • Collection size: {result.get('collection_size', 0)} datasites")
        print(f"   • Sent to: {len(result['sent_to'])} datasites")
        print(f"   • Failed to send: {len(result['failed_to_send'])} datasites")
        print(f"   • Timeout: {result['timeout_minutes']} minutes")
        
        if result['sent_to']:
            print(f"\n📤 Successfully sent pings to:")
            for email in result['sent_to']:
                print(f"   • {email}")
        
        if result['failed_to_send']:
            print(f"\n❌ Failed to send pings to:")
            for failure in result['failed_to_send']:
                print(f"   • {failure['email']}: {failure['error']}")
        
        # Show ping jobs details
        if result['jobs']:
            print(f"\n🔍 Ping Job Details:")
            for job in result['jobs']:
                print(f"   • To: {job.target_email} | Job ID: {job.short_id} | Status: {job.status}")
        
        print(f"\n💡 What you can do next:")
        print(f"   • Check job status: scq.q.get_job('<job_id>')")
        print(f"   • View your submitted jobs: scq.q.jobs_for_others")
        print(f"   • See responsive datasites: scq.q.datasites.responsive_to_me()")
        print(f"   • Sort datasites: scq.q.datasites.sort_by('last_response_to_me')")
        
    except Exception as e:
        print(f"❌ Error during ping: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 