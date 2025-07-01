#!/usr/bin/env python3
"""
Verification script to ensure ping only targets datasites from q.datasites collection.
"""

import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import syft_code_queue as scq

def main():
    print("🔍 Ping Verification Test")
    print("=" * 40)
    
    # Show which datasites would be pinged
    print("\n📡 Datasites with Code Queues (q.datasites):")
    try:
        datasites_list = scq.q.datasites.to_list()
        if datasites_list:
            for i, ds in enumerate(datasites_list, 1):
                status = "✅ Responsive to me" if ds["responsiveness"] == "responsive_to_me" else "❓ Unknown/New"
                print(f"   {i}. {ds['email']} - {ds['total_jobs']} jobs - {status}")
        else:
            print("   No datasites with code queues found")
            
        # Show current user email (won't be pinged)
        print(f"\n👤 Your email: {scq.q.email} (will be skipped in ping)")
        
        # Calculate how many will actually be pinged
        ping_targets = [ds for ds in datasites_list if ds["email"] != scq.q.email]
        print(f"\n🎯 Will ping {len(ping_targets)} datasites:")
        for ds in ping_targets:
            print(f"   • {ds['email']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Ask if user wants to proceed with actual ping
    if ping_targets:
        response = input(f"\n❓ Send ping jobs to these {len(ping_targets)} datasites? (y/N): ")
        if response.lower().startswith('y'):
            print("\n🏓 Sending pings...")
            result = scq.q.ping_all_datasites(timeout_minutes=5)
            
            print(f"\n✅ Results:")
            print(f"   • Sent to: {result['sent_to']}")
            print(f"   • Failed: {result['failed_to_send']}")
            print(f"   • Job count: {len(result['jobs'])}")
        else:
            print("👋 Skipping actual ping test")
    else:
        print("\n💡 No other datasites to ping (only found yourself or no datasites)")

if __name__ == "__main__":
    main() 