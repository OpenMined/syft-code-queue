# 🚀 Syft Code Queue

A simple, lightweight system for executing code on remote SyftBox datasites with **manual approval workflows**.

## Overview

Syft Code Queue provides a clean separation between **data scientists** who submit code for execution and **data owners** who review and approve that code. All code execution requires explicit manual approval - there is no automatic approval built into the core system.

## Architecture

```
Data Scientist → Submit Code → Data Owner Reviews → Manual Approve → Execute → Results
```

## Key Features

- **📦 Simple Code Submission**: Package code as folders with `run.sh` scripts
- **🔒 Manual Approval Only**: Data owners must explicitly approve every job
- **🛡️ Security**: Safe execution with sandboxing and resource limits  
- **🤖 External Automation**: Automation systems call the manual approval API
- **📊 Job Management**: Track job status and retrieve results
- **⚡ Lightweight**: Much simpler than RDS while being fully functional
- **🎨 Interactive Jupyter UI**: Beautiful HTML tables with clickable approve/reject buttons
- **🔍 Tab Completion**: Full tab completion support for all properties and methods

## Quick Start

### Simple Unified API

```python
import syft_code_queue as q

# Submit jobs to others
job = q.submit_job(
    target_email="data-owner@university.edu",
    code_folder="./my_analysis",
    name="Statistical Analysis",
    description="Aggregate statistics computation",
    tags=["statistics", "privacy-safe"]
)

# Or submit a simple script
job = q.submit_script(
    target_email="data-owner@university.edu",
    script_content="print('Hello, world!')",
    name="Hello World Test"
)

# Monitor your jobs
q.my_jobs()                    # Jobs you've submitted
q.pending_for_me()             # Jobs submitted to you for approval
q.approve("job-id", "Looks safe")  # Approve a job
q.status()                     # Overall status

print(f"Job submitted: {job.uid}")
print(f"Status: {job.status}")  # Will be 'pending'
```

### Interactive Jupyter Interface

In Jupyter notebooks, jobs display as beautiful interactive cards:

```python
# Individual job with interactive buttons
job  # Shows approval/rejection buttons you can click

# Job collections with filterable tables
q.jobs_for_me     # Interactive table with batch approve/reject
q.jobs_for_others # Table showing your submitted jobs with logs/output buttons
q.pending_for_me  # Shows only jobs awaiting your approval
```

**Interactive Features:**
- 🔍 **Real-time search** - Filter jobs by name or email
- 📊 **Status filtering** - View pending, running, or completed jobs
- ✅ **One-click actions** - Approve/reject jobs directly from the interface
- 🎯 **Batch operations** - Approve or reject multiple jobs at once
- 📜 **Inline code review** - See job details and code files instantly

### Managing Jobs (Python API)

```python
import syft_code_queue as q

# View jobs submitted to you
q.pending_for_me()             # Jobs waiting for your approval
q.all_jobs_for_me()            # All jobs submitted to you

# Review and approve/reject jobs
q.review_job("job-id")         # Get job details
q.approve("job-id", "Looks safe")  # Approve job
q.reject("job-id", "Too broad")    # Reject job

# Overall status
q.status()                     # Your queue status
```

### CLI Tools (Alternative)

```bash
# CLI Tools for Job Management (optional)
scq pending                    # List jobs pending approval
scq review a1b2c3d4           # Review specific job details  
scq approve a1b2c3d4 -r "Looks safe"  # Approve job
scq reject a1b2c3d4 -r "Too broad"    # Reject job
scq list                      # List all jobs
scq status                    # Show queue status
```

## Installation

```bash
pip install syft-code-queue
```

## Tutorials

We provide role-specific tutorials for different users:

- **🔬 Data Scientists**: `examples/Part 1 — Data Scientist Tutorial.ipynb` - Learn to submit and monitor jobs
- **🏛️ Data Owners**: `examples/Part 2 — Data Owner Tutorial.ipynb` - Learn to review and approve jobs

## Manual Approval Architecture

The core design principle is **manual approval only**:

### ✅ What's Included
- Job submission and queuing
- Manual approval/rejection API
- Safe code execution engine
- Job status tracking and results retrieval

### ❌ What's NOT Included  
- Built-in auto-approval rules
- Automatic approval logic
- Built-in trust systems

### 🤖 External Automation

Any automation must be **external** and call the manual approval CLI or API:

```python
# External automation example using CLI
import subprocess

def smart_approval_bot():
    # Get pending jobs
    result = subprocess.run(['scq', 'pending'], capture_output=True, text=True)
    
    # Parse and approve based on criteria
    for job_id in get_job_ids_from_output(result.stdout):
        if meets_my_criteria(job_id):
            subprocess.run(['scq', 'approve', job_id, '-r', 'Auto-approved by bot'])
        else:
            subprocess.run(['scq', 'reject', job_id, '-r', 'Does not meet criteria'])
```

See the examples directory for more automation examples.

## Code Package Structure

Every job submission must be a folder containing:

```
my_analysis/
├── run.sh              # Main execution script (required)
├── analyze.py          # Your analysis code
├── requirements.txt    # Python dependencies (optional)
└── README.md          # Documentation (optional)
```

### Example `run.sh`:

```bash
#!/bin/bash
set -e

echo "Starting analysis..."

# Install dependencies
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

# Run analysis
python analyze.py

echo "Analysis complete!"
```

## Security Features

- **Safe Execution**: `SafeCodeRunner` with timeouts and resource limits
- **Command Filtering**: Block dangerous operations
- **Sandboxing**: Isolated execution environment
- **Manual Review**: Human oversight of all code execution
- **Audit Trail**: All approvals/rejections are logged

## Job Lifecycle

```
📤 submit → ⏳ pending → ✅ approved → 🏃 running → 🎉 completed
                     ↘ 🚫 rejected            ↘ ❌ failed
```

### Status Reference
- **pending**: Waiting for data owner approval
- **approved**: Approved by data owner, waiting to execute
- **running**: Currently executing on datasite
- **completed**: Finished successfully, results available
- **failed**: Execution failed (see error logs)
- **rejected**: Rejected by data owner

## Best Practices

### When Submitting Jobs
- Use clear, descriptive job names and descriptions
- Include privacy-safe tags like `aggregate-analysis`, `statistics`
- Only request aggregate computations, never individual records
- Test code locally before submission
- Be responsive to questions about your submissions

### When Managing Jobs Submitted to You
- Review all submitted code thoroughly
- Check for privacy compliance and data safety
- Provide clear feedback when rejecting requests
- Set up regular monitoring of your pending jobs
- Maintain clear approval criteria for your organization
- Use `q.review_job()` to examine job details before approving

## API Reference

### Unified Python API

```python
import syft_code_queue as q

# Submit jobs
job = q.submit_job(target_email, code_folder, name, description, tags)
job = q.submit_script(target_email, script_content, name, description, requirements, tags)

# Monitor your submitted jobs
q.my_jobs()                    # All your jobs
q.get_job(job_uid)            # Specific job
q.get_job_output(job_uid)     # Job output
q.get_job_logs(job_uid)       # Job logs
q.wait_for_completion(job_uid) # Wait for completion

# Manage jobs submitted to you
q.pending_for_me()            # Jobs waiting for approval
q.all_jobs_for_me()           # All jobs submitted to you
q.review_job(job_uid)         # Review job details
q.approve(job_uid, reason)    # Approve job
q.reject(job_uid, reason)     # Reject job

# Status and help
q.status()                    # Overall status
q.help()                      # Show help
```

### CLI API

```bash
# List pending jobs
scq pending

# Review job details
scq review <job_id>

# Approve/reject jobs
scq approve <job_id> --reason "Approved because..."
scq reject <job_id> --reason "Rejected because..."

# Monitor jobs
scq list        # All jobs
scq status      # Queue status
scq --help      # All available commands
```

## SyftBox App Setup

To enable syft-code-queue on your datasite:

1. **Add to your SyftBox datasite** - Copy the `syft-code-queue` folder to your datasite
2. **SyftBox auto-execution** - SyftBox will periodically call `run.sh` to process jobs
3. **Use CLI tools** - Data owners use `scq` commands to manage job approvals

### Configuration

The app uses sensible defaults, but can be customized:

```python
from syft_code_queue import QueueConfig

config = QueueConfig(
    queue_name="code-queue",
    max_concurrent_jobs=3,
    job_timeout=600,  # 10 minutes
    cleanup_completed_after=86400  # 24 hours
)
```

### SyftBox Integration

The `run.sh` script handles the entire queue processing cycle:
- ✅ Checks for pending jobs (logs info for data owners)
- 🚀 Executes approved jobs
- 🧹 Cleans up old completed jobs  
- 🚪 Exits (no long-running processes)

## Integration with Other Tools

- **syft-nsai**: Generate analysis code with AI, execute with queue
- **SyftBox**: Leverages existing datasite infrastructure
- **Custom Apps**: Easy integration with any Python application

## Development

```bash
git clone <repository>
cd syft-code-queue

# Install in development mode
pip install -e .

# Run tests
pytest

# Run examples
python examples/example_cross_datasite_workflow.py
```

## Contributing

See `CONTRIBUTING.md` for development guidelines.

## License

Licensed under the Apache License 2.0. See `LICENSE` file for details.

---

**Simple. Secure. Manual. 🚀** 