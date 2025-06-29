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

## Quick Start

### For Data Scientists

```python
import syft_code_queue as scq

# Submit code for execution
job = scq.submit_code(
    target_email="data-owner@university.edu",
    code_folder=my_analysis_package,
    name="Statistical Analysis",
    description="Aggregate statistics computation",
    tags=["statistics", "privacy-safe"]
)

print(f"Job submitted: {job.uid}")
print(f"Status: {job.status}")  # Will be 'pending'
```

### For Data Owners

```python
import syft_code_queue as scq

# Create server and review pending jobs
server = scq.create_server()
pending_jobs = server.list_pending_jobs()

# Review and approve/reject manually
for job in pending_jobs:
    print(f"Job: {job.name} from {job.requester_email}")
    # ... inspect job.code_folder ...
    
    # Manual approval decision
    server.approve_job(job.uid)  # or
    server.reject_job(job.uid, "Reason for rejection")

# Start server to execute approved jobs
server.start()
```

## Installation

```bash
pip install syft-code-queue
```

## Tutorials

We provide role-specific tutorials for different users:

- **🔬 Data Scientists**: `examples/DataScientist_Tutorial.ipynb` - Learn to submit and monitor jobs
- **🏛️ Data Owners**: `examples/DataOwner_Tutorial.ipynb` - Learn to review and approve jobs  
- **📋 Overview**: `examples/SyftCodeQueue_Tutorial.ipynb` - System overview and concepts

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

Any automation must be **external** and call the manual approval API:

```python
# External automation example
def smart_approval_bot(server):
    pending = server.list_pending_jobs()
    for job in pending:
        if meets_my_criteria(job):
            server.approve_job(job.uid)
        else:
            server.reject_job(job.uid, "Does not meet criteria")
```

See `examples/external_automation_example.py` for a complete example.

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

### For Data Scientists
- Use clear, descriptive job names and descriptions
- Include privacy-safe tags like `aggregate-analysis`, `statistics`
- Only request aggregate computations, never individual records
- Test code locally before submission
- Be responsive to data owner questions

### For Data Owners
- Review all submitted code thoroughly
- Check for privacy compliance and data safety
- Provide clear feedback when rejecting requests
- Set up automated monitoring for your approval workflows
- Maintain clear approval criteria for your organization

## API Reference

### Client API

```python
# Submit code
job = scq.submit_code(target_email, code_folder, name, description, tags)

# Monitor jobs
client = scq.create_client()
jobs = client.list_jobs(status=scq.JobStatus.pending)
job = client.get_job(job_uid)
results = client.get_job_output(job_uid)
logs = client.get_job_logs(job_uid)
```

### Server API

```python
# Create and manage server
server = scq.create_server(max_concurrent_jobs=3, job_timeout=600)

# Review jobs
pending = server.list_pending_jobs()

# Manual approval
server.approve_job(job_uid)
server.reject_job(job_uid, reason)

# Execute approved jobs
server.start()  # Runs continuously
server.stop()
```

## Configuration

```python
from syft_code_queue import QueueConfig

config = QueueConfig(
    queue_name="my-datasite-queue",
    max_concurrent_jobs=3,
    job_timeout=600,  # 10 minutes
    cleanup_completed_after=86400  # 24 hours
)

server = scq.CodeQueueServer(config=config)
```

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
python examples/external_automation_example.py
```

## Contributing

See `CONTRIBUTING.md` for development guidelines.

## License

Licensed under the Apache License 2.0. See `LICENSE` file for details.

---

**Simple. Secure. Manual. 🚀** 