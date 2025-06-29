#!/usr/bin/env python3
"""
External Automation Example for Syft Code Queue

This example shows how external systems can automate approval decisions
by calling the manual approval API. The core syft-code-queue system 
only provides manual approval - all automation is external and calls this API.
"""

import time
from pathlib import Path
import sys

# Add the src directory to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import syft_code_queue as scq
from syft_code_queue.models import JobStatus


class SmartApprovalBot:
    """
    Example external automation that applies intelligent approval rules.
    
    This demonstrates how organizations can build their own approval logic
    that calls the manual approval API.
    """
    
    def __init__(self, server):
        self.server = server
        self.approval_rules = []
        
    def add_rule(self, rule_func, name):
        """Add an approval rule function."""
        self.approval_rules.append((rule_func, name))
        print(f"📋 Added approval rule: {name}")
    
    def process_pending_jobs(self):
        """Process all pending jobs with approval rules."""
        pending_jobs = self.server.list_pending_jobs()
        
        print(f"🔍 Found {len(pending_jobs)} pending job(s) to review")
        
        for job in pending_jobs:
            print(f"\n📄 Reviewing job: {job.name}")
            print(f"   📧 From: {job.requester_email}")
            print(f"   🏷️  Tags: {job.tags}")
            
            # Apply approval rules
            approved = False
            approval_reason = "No matching approval rules"
            
            for rule_func, rule_name in self.approval_rules:
                try:
                    if rule_func(job):
                        print(f"   ✅ Matched rule: {rule_name}")
                        approved = True
                        approval_reason = f"Auto-approved by rule: {rule_name}"
                        break
                    else:
                        print(f"   ❌ Rule '{rule_name}': No match")
                except Exception as e:
                    print(f"   ⚠️  Rule '{rule_name}' failed: {e}")
            
            # Make approval decision
            if approved:
                success = self.server.approve_job(str(job.uid))
                if success:
                    print(f"   🎉 Job APPROVED: {approval_reason}")
                else:
                    print(f"   ❌ Failed to approve job")
            else:
                success = self.server.reject_job(str(job.uid), approval_reason)
                if success:
                    print(f"   🚫 Job REJECTED: {approval_reason}")
                else:
                    print(f"   ❌ Failed to reject job")


def main():
    """Demonstrate external approval automation."""
    print("🤖 External Approval Automation Example")
    print("=" * 50)
    
    # Create server (manual approval only)
    try:
        server = scq.create_server(
            queue_name="external-automation-demo",
            max_concurrent_jobs=2,
            job_timeout=300
        )
        print(f"🖥️ Created manual approval server: {server.email}")
        
    except Exception as e:
        print(f"❌ Error creating server: {e}")
        print("💡 This example requires SyftBox to be configured")
        return
    
    # Create external approval bot
    bot = SmartApprovalBot(server)
    
    # Define approval rules (these are external to the core system)
    def approve_safe_analysis(job):
        """Approve jobs tagged as safe analysis."""
        safe_tags = {"privacy-safe", "aggregate-analysis", "statistics"}
        return any(tag in safe_tags for tag in job.tags)
    
    def approve_trusted_requesters(job):
        """Approve jobs from trusted domains."""
        trusted_domains = ["@university.edu", "@research.org", "@openmined.org"]
        return any(domain in job.requester_email for domain in trusted_domains)
    
    def approve_demo_jobs(job):
        """Approve demo and tutorial jobs."""
        demo_tags = {"demo", "tutorial", "test"}
        return any(tag in demo_tags for tag in job.tags)
    
    def reject_risky_operations(job):
        """Reject jobs with risky operations."""
        # This is an example - in practice you'd analyze the actual code
        risky_tags = {"raw-data", "export", "individual-records"}
        if any(tag in risky_tags for tag in job.tags):
            return False  # Force rejection
        return None  # No decision (continue to other rules)
    
    # Add rules to the bot
    bot.add_rule(approve_demo_jobs, "Demo/Tutorial Jobs")
    bot.add_rule(approve_trusted_requesters, "Trusted Requesters")
    bot.add_rule(approve_safe_analysis, "Safe Analysis Jobs")
    
    print(f"\n🔍 Checking for pending jobs...")
    
    # Process pending jobs
    bot.process_pending_jobs()
    
    # Start server to execute approved jobs
    print(f"\n🖥️ Starting server to execute approved jobs...")
    try:
        server.start()
        
        # Let it run briefly
        time.sleep(5)
        
        # Check for any newly pending jobs and process them
        print(f"\n🔄 Checking for new pending jobs...")
        bot.process_pending_jobs()
        
        time.sleep(5)
        
    finally:
        print(f"\n🛑 Stopping server...")
        server.stop()
    
    print(f"\n✅ External automation example complete!")
    print(f"💡 This shows how external systems can automate approval decisions")
    print(f"   while keeping the core syft-code-queue system purely manual.")


if __name__ == "__main__":
    main() 