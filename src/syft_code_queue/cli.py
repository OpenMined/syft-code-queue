#!/usr/bin/env python3
"""
Command-line interface for managing syft-code-queue jobs.

This CLI provides data owners with tools to:
- List pending jobs
- Review job details
- Approve or reject jobs
- Monitor job execution
"""

import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

import click
from loguru import logger
from tabulate import tabulate

try:
    from syft_core import Client as SyftBoxClient
except ImportError:
    logger.warning("syft_core not available - using mock client")
    class MockSyftBoxClient:
        def __init__(self):
            self.email = "demo@example.com"
        
        def app_data(self, app_name):
            import tempfile
            return Path(tempfile.gettempdir()) / f"syftbox_demo_{app_name}"
        
        @classmethod
        def load(cls):
            return cls()
    
    SyftBoxClient = MockSyftBoxClient

from .models import JobStatus, QueueConfig
from .app import CodeQueueApp


class JobManager:
    """Manages job approval workflow for data owners."""
    
    def __init__(self):
        self.syftbox_client = SyftBoxClient.load()
        self.config = QueueConfig(queue_name="code-queue")
        self.app = CodeQueueApp()
    
    def list_pending_jobs(self) -> None:
        """List all pending jobs for this datasite."""
        pending_jobs = self.app._get_jobs_by_status(JobStatus.pending)
        my_jobs = [job for job in pending_jobs if job.target_email == self.app.email]
        
        if not my_jobs:
            click.echo("✅ No pending jobs to review")
            return
        
        click.echo(f"📋 {len(my_jobs)} job(s) pending approval:\n")
        
        headers = ["ID", "Name", "From", "Created", "Tags"]
        rows = []
        
        for job in my_jobs:
            rows.append([
                str(job.uid)[:8] + "...",
                job.name[:30],
                job.requester_email,
                job.created_at.strftime("%Y-%m-%d %H:%M"),
                ", ".join(job.tags[:3])  # Show first 3 tags
            ])
        
        click.echo(tabulate(rows, headers=headers, tablefmt="grid"))
        click.echo(f"\n💡 Use 'scq review <job_id>' to inspect a job")
        click.echo(f"💡 Use 'scq approve <job_id>' to approve a job")
        click.echo(f"💡 Use 'scq reject <job_id>' to reject a job")
    
    def review_job(self, job_id: str) -> None:
        """Review a specific job in detail."""
        job = self._get_job_by_partial_id(job_id)
        if not job:
            return
        
        click.echo(f"📋 Job Review: {job.name}")
        click.echo("=" * 60)
        click.echo(f"🆔 ID: {job.uid}")
        click.echo(f"📧 From: {job.requester_email}")
        click.echo(f"🎯 Target: {job.target_email}")
        click.echo(f"📅 Created: {job.created_at}")
        click.echo(f"🏷️  Status: {job.status.value}")
        
        if job.description:
            click.echo(f"📝 Description: {job.description}")
        
        if job.tags:
            click.echo(f"🏷️  Tags: {', '.join(job.tags)}")
        
        # Show code structure
        click.echo(f"\n📁 Code Structure:")
        job_dir = self.app._get_job_dir(job)
        if job_dir.exists():
            self._show_directory_tree(job_dir, prefix="   ")
        
        # Show run.sh content
        run_script = job_dir / "run.sh"
        if run_script.exists():
            click.echo(f"\n🔧 run.sh contents:")
            click.echo("-" * 40)
            try:
                content = run_script.read_text()
                click.echo(content)
            except Exception as e:
                click.echo(f"❌ Error reading run.sh: {e}")
            click.echo("-" * 40)
        
        click.echo(f"\n💡 Commands:")
        click.echo(f"   scq approve {str(job.uid)[:8]}  # Approve this job")
        click.echo(f"   scq reject {str(job.uid)[:8]}   # Reject this job")
    
    def approve_job(self, job_id: str, reason: Optional[str] = None) -> None:
        """Approve a pending job."""
        job = self._get_job_by_partial_id(job_id)
        if not job:
            return
        
        if job.status != JobStatus.pending:
            click.echo(f"❌ Job {job.name} is not pending (status: {job.status.value})")
            return
        
        if job.target_email != self.app.email:
            click.echo(f"❌ Job is not targeted at this datasite ({job.target_email})")
            return
        
        # Update job status
        message = f"Approved by {self.app.email}"
        if reason:
            message += f": {reason}"
        
        job.update_status(JobStatus.approved, message)
        self.app._save_job(job)
        
        click.echo(f"✅ Approved job: {job.name}")
        click.echo(f"💡 Job will be executed on next queue processing cycle")
    
    def reject_job(self, job_id: str, reason: Optional[str] = None) -> None:
        """Reject a pending job."""
        job = self._get_job_by_partial_id(job_id)
        if not job:
            return
        
        if job.status != JobStatus.pending:
            click.echo(f"❌ Job {job.name} is not pending (status: {job.status.value})")
            return
        
        if job.target_email != self.app.email:
            click.echo(f"❌ Job is not targeted at this datasite ({job.target_email})")
            return
        
        # Update job status
        message = f"Rejected by {self.app.email}"
        if reason:
            message += f": {reason}"
        
        job.update_status(JobStatus.rejected, message)
        self.app._save_job(job)
        
        click.echo(f"🚫 Rejected job: {job.name}")
        if reason:
            click.echo(f"📝 Reason: {reason}")
    
    def list_all_jobs(self) -> None:
        """List all jobs with their statuses."""
        all_jobs = []
        for status in JobStatus:
            jobs = self.app._get_jobs_by_status(status)
            my_jobs = [job for job in jobs if job.target_email == self.app.email]
            all_jobs.extend(my_jobs)
        
        if not all_jobs:
            click.echo("📋 No jobs found")
            return
        
        # Sort by creation time
        all_jobs.sort(key=lambda j: j.created_at, reverse=True)
        
        click.echo(f"📋 All jobs for {self.app.email}:\n")
        
        headers = ["ID", "Name", "From", "Status", "Created"]
        rows = []
        
        status_emojis = {
            JobStatus.pending: "⏳",
            JobStatus.approved: "✅", 
            JobStatus.running: "🏃",
            JobStatus.completed: "🎉", 
            JobStatus.failed: "❌",
            JobStatus.rejected: "🚫"
        }
        
        for job in all_jobs:
            emoji = status_emojis.get(job.status, "❓")
            rows.append([
                str(job.uid)[:8] + "...",
                job.name[:25],
                job.requester_email[:20],
                f"{emoji} {job.status.value}",
                job.created_at.strftime("%m-%d %H:%M")
            ])
        
        click.echo(tabulate(rows, headers=headers, tablefmt="grid"))
    
    def _get_job_by_partial_id(self, partial_id: str):
        """Get job by partial UUID."""
        try:
            # Try full UUID first
            if len(partial_id) == 36:  # Full UUID length
                job_uuid = UUID(partial_id)
                return self.app._load_job_from_file(
                    self.app._get_queue_dir() / f"{job_uuid}.json"
                )
            
            # Search by partial ID
            queue_dir = self.app._get_queue_dir()
            if not queue_dir.exists():
                click.echo("❌ No jobs directory found")
                return None
            
            matches = []
            for job_file in queue_dir.glob("*.json"):
                if job_file.stem.startswith(partial_id):
                    job = self.app._load_job_from_file(job_file)
                    if job and job.target_email == self.app.email:
                        matches.append(job)
            
            if not matches:
                click.echo(f"❌ No job found with ID starting with '{partial_id}'")
                return None
            
            if len(matches) > 1:
                click.echo(f"❌ Multiple jobs match '{partial_id}'. Be more specific:")
                for job in matches:
                    click.echo(f"   {str(job.uid)[:12]}... - {job.name}")
                return None
            
            return matches[0]
            
        except Exception as e:
            click.echo(f"❌ Error finding job: {e}")
            return None
    
    def _show_directory_tree(self, path: Path, prefix: str = ""):
        """Show directory structure."""
        try:
            items = sorted(path.iterdir())
            for item in items:
                if item.is_dir():
                    click.echo(f"{prefix}📁 {item.name}/")
                else:
                    size = item.stat().st_size
                    click.echo(f"{prefix}📄 {item.name} ({size} bytes)")
        except Exception as e:
            click.echo(f"{prefix}❌ Error reading directory: {e}")


# CLI Commands
@click.group()
@click.version_option()
def cli():
    """Syft Code Queue - Job Management CLI for Data Owners"""
    pass

@cli.command()
def pending():
    """List jobs pending approval."""
    manager = JobManager()
    manager.list_pending_jobs()

@cli.command()
@click.argument('job_id')
def review(job_id: str):
    """Review a job in detail."""
    manager = JobManager()
    manager.review_job(job_id)

@cli.command()
@click.argument('job_id')
@click.option('--reason', '-r', help='Reason for approval')
def approve(job_id: str, reason: Optional[str]):
    """Approve a pending job."""
    manager = JobManager()
    manager.approve_job(job_id, reason)

@cli.command()
@click.argument('job_id')
@click.option('--reason', '-r', help='Reason for rejection')
def reject(job_id: str, reason: Optional[str]):
    """Reject a pending job."""
    manager = JobManager()
    manager.reject_job(job_id, reason)

@cli.command()
def list():
    """List all jobs."""
    manager = JobManager()
    manager.list_all_jobs()

@cli.command()
def status():
    """Show queue status."""
    manager = JobManager()
    click.echo(f"📧 Data Owner: {manager.app.email}")
    click.echo(f"📁 Queue Directory: {manager.app._get_queue_dir()}")
    
    # Count jobs by status
    status_counts = {}
    for status in JobStatus:
        jobs = manager.app._get_jobs_by_status(status)
        my_jobs = [job for job in jobs if job.target_email == manager.app.email]
        status_counts[status] = len(my_jobs)
    
    click.echo("\n📊 Job Counts:")
    for status, count in status_counts.items():
        if count > 0:
            emoji = {"pending": "⏳", "approved": "✅", "running": "🏃", 
                    "completed": "🎉", "failed": "❌", "rejected": "🚫"}.get(status.value, "❓")
            click.echo(f"   {emoji} {status.value}: {count}")


if __name__ == "__main__":
    cli() 