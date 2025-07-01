#!/usr/bin/env python3
"""
Example script to test the ping functionality for syft-code-queue.

This script demonstrates how to:
1. Ping all datasites to check connectivity
2. View the results
3. Check which datasites responded
"""

import sys
import time
from pathlib import Path

# Add the src directory to the path so we can import syft_code_queue
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import syft_code_queue as scq

def main():
    print("🏓 SyftBox Code Queue - Ping Test")
    print("=" * 50)
    
    # Show current datasites
    print("\n📡 Current Datasites:")
    try:
        print(scq.q.datasites)
    except Exception as e:
        print(f"Error getting datasites: {e}")
        return
    
    # Send pings with shorter timeout (5 minutes for testing)
    print("\n🏓 Sending ping jobs to all datasites...")
    try:
        ping_results = scq.q.ping_all_datasites(timeout_minutes=5)
        
        print(f"\n✅ Ping Summary:")
        print(f"   • Sent to: {len(ping_results['sent_to'])} datasites")
        print(f"   • Failed to send: {len(ping_results['failed_to_send'])} datasites")
        print(f"   • Timeout: {ping_results['timeout_minutes']} minutes")
        
        if ping_results['sent_to']:
            print(f"\n📤 Successfully sent pings to:")
            for email in ping_results['sent_to']:
                print(f"   • {email}")
        
        if ping_results['failed_to_send']:
            print(f"\n❌ Failed to send pings to:")
            for failure in ping_results['failed_to_send']:
                print(f"   • {failure['email']}: {failure['error']}")
        
        # Show ping jobs details
        if ping_results['jobs']:
            print(f"\n🔍 Ping Job Details:")
            for job in ping_results['jobs']:
                print(f"   • {job.target_email}: {job.name} (Job ID: {job.short_id})")
        
        # Wait a bit and then check status
        print(f"\n⏳ Waiting 30 seconds to check initial responses...")
        time.sleep(30)
        
        print(f"\n📊 Updated Datasite Status:")
        print(scq.q.datasites)
        
        print(f"\n💡 Tips:")
        print(f"   • Use scq.q.datasites.responsive_to_me() to see which datasites have responded to you")
        print(f"   • Check job status with scq.q.get_job('<job_id>')")
        print(f"   • View your submitted jobs with scq.q.jobs_for_others")
        
    except Exception as e:
        print(f"❌ Error during ping test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 