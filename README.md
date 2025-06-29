# 🚀 Syft Code Queue

Simple code execution queue for SyftBox datasites.

## 📋 Overview

`syft-code-queue` provides a lightweight way to submit code for execution on remote SyftBox datasites. It's designed to be much simpler than RDS while still providing essential functionality for secure code execution.

### Key Features

- **Simple API**: Submit code folders with `run.sh` scripts
- **Queue Management**: Automatic job queuing and processing
- **Security**: Safe code execution with configurable approval rules
- **Auto-approval**: Configurable rules for automatic job approval
- **Result Retrieval**: Easy access to job outputs and logs
- **Status Tracking**: Real-time job status monitoring

## 🏗️ Architecture

```
┌─────────────────┐    submit_code    ┌─────────────────┐
│   Client App    │ ──────────────────► │  Remote Queue   │
│   (Requester)   │                   │  (Data Owner)   │
└─────────────────┘                   └─────────────────┘
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │  Queue Server   │
                                      │  - Auto-approve │
                                      │  - Execute code │
                                      │  - Store results│
                                      └─────────────────┘
```

## 🚀 Quick Start

### Installation

```bash
pip install syft-code-queue
```

### Basic Usage

#### 1. Submit Code for Execution

```python
import syft_code_queue as scq
from pathlib import Path

# Create your code folder with run.sh
code_folder = Path("my_analysis")
code_folder.mkdir(exist_ok=True)

# Create run.sh script
(code_folder / "run.sh").write_text("""#!/bin/bash
echo "Analyzing data..."
python analysis.py > "$SYFT_OUTPUT_DIR/results.txt"
echo "Analysis complete!"
""")

# Submit to remote datasite
job = scq.submit_code(
    target_email="data-owner@example.com",
    code_folder=code_folder,
    name="Data Analysis Job",
    description="Statistical analysis of dataset",
    tags=["analysis", "statistics"],
    auto_approval=True
)

print(f"Job submitted: {job.uid}")
```

#### 2. Monitor Job Status

```python
client = scq.create_client()

# Check specific job
job = client.get_job(job_uid)
print(f"Status: {job.status}")

# List all jobs
jobs = client.list_jobs(limit=10)
for job in jobs:
    print(f"{job.name}: {job.status}")
```

#### 3. Retrieve Results

```python
# Get job output
output_path = client.get_job_output(job_uid)
if output_path:
    results = (output_path / "results.txt").read_text()
    print(results)

# Get execution logs
logs = client.get_job_logs(job_uid)
print(logs)
```

### Running a Queue Server

```python
import syft_code_queue as scq

def custom_approval_rules(job):
    """Define custom auto-approval logic."""
    # Auto-approve analysis jobs
    if "analysis" in job.tags:
        return True
    
    # Auto-approve from trusted domains
    if "@company.com" in job.requester_email:
        return True
    
    return False

# Start server
server = scq.create_server(
    auto_approval_callback=custom_approval_rules,
    max_concurrent_jobs=3,
    job_timeout=600  # 10 minutes
)

server.start()
```

## 📁 Code Folder Structure

Your code folder must contain a `run.sh` script:

```
my_analysis/
├── run.sh              # Required: Main execution script
├── analysis.py         # Your code files
├── requirements.txt    # Dependencies
└── data/              # Any data files
```

### Environment Variables

Your `run.sh` script has access to these variables:

- `SYFT_JOB_ID`: Unique job identifier
- `SYFT_JOB_NAME`: Human-readable job name
- `SYFT_OUTPUT_DIR`: Directory to write results
- `SYFT_REQUESTER`: Email of the requester

### Example run.sh

```bash
#!/bin/bash
set -e  # Exit on error

echo "Starting job: $SYFT_JOB_NAME"
echo "Requester: $SYFT_REQUESTER"

# Install dependencies if needed
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

# Run your analysis
python analysis.py

# Save results
echo "Job completed successfully" > "$SYFT_OUTPUT_DIR/status.txt"
cp results.csv "$SYFT_OUTPUT_DIR/"

echo "Output saved to: $SYFT_OUTPUT_DIR"
```

## 🔧 Configuration

### Client Configuration

```python
from syft_code_queue import QueueConfig

config = QueueConfig(
    queue_name="my-custom-queue",
    max_concurrent_jobs=5,
    job_timeout=1800,  # 30 minutes
    cleanup_completed_after=86400,  # 24 hours
    auto_approval_enabled=True
)

client = scq.CodeQueueClient(config=config)
```

### Server Configuration

```python
server = scq.create_server(
    queue_name="analysis-queue",
    max_concurrent_jobs=2,
    job_timeout=600,
    auto_approval_enabled=True
)
```

## 🛡️ Security Features

### Safe Code Runner

The default `SafeCodeRunner` includes security measures:

```python
from syft_code_queue import SafeCodeRunner

runner = SafeCodeRunner(
    timeout=300,
    max_output_size=10*1024*1024,  # 10MB
    blocked_commands=["rm", "sudo", "passwd"],  # Blacklist
    allowed_commands=["python", "pip", "echo"]  # Whitelist (optional)
)
```

### Auto-Approval Rules

Configure safe auto-approval:

```python
def safe_approval_rules(job):
    # Only auto-approve certain types
    safe_tags = {"visualization", "statistics", "report"}
    if not any(tag in safe_tags for tag in job.tags):
        return False
    
    # Check requester domain
    trusted_domains = ["@university.edu", "@research.org"]
    if not any(domain in job.requester_email for domain in trusted_domains):
        return False
    
    return True
```

## 📊 Job Lifecycle

```
Submit → Pending → Approved → Running → Completed
           ↓         ↓          ↓         ↓
        Rejected   Failed    Failed   (Results Available)
```

### Job Status

- `pending`: Waiting for approval
- `approved`: Approved, waiting to run  
- `running`: Currently executing
- `completed`: Finished successfully
- `failed`: Execution failed
- `rejected`: Rejected by data owner

## 🔍 Advanced Usage

### Custom Runners

```python
from syft_code_queue import CodeRunner

class CustomRunner(CodeRunner):
    def run_job(self, job):
        # Custom execution logic
        print(f"Running {job.name} with custom logic")
        return super().run_job(job)

server = scq.CodeQueueServer(runner=CustomRunner())
```

### Job Filtering

```python
# Filter jobs by status
pending_jobs = client.list_jobs(status=scq.JobStatus.pending)

# Filter by target
my_jobs = client.list_jobs(target_email="my-datasite@example.com")
```

### Manual Job Management

```python
# Approve/reject jobs manually
server.approve_job(job_uid)
server.reject_job(job_uid, reason="Security concerns")

# Cancel submitted jobs
client.cancel_job(job_uid)
```

## 🆚 Comparison with RDS

| Feature | syft-code-queue | RDS |
|---------|----------------|-----|
| **Complexity** | Simple | Full-featured |
| **Setup** | Minimal | Complex |
| **Code Format** | `run.sh` folders | Structured datasets |
| **Approval** | Built-in | Manual |
| **Performance** | Lightweight | Heavy |
| **Use Case** | Simple execution | Data science workflows |

## 📝 Examples

See the `examples/` directory for:
- `basic_usage.py`: Complete workflow example
- `server_setup.py`: Queue server configuration
- `custom_approval.py`: Advanced approval rules

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📄 License

Apache 2.0 License - see LICENSE file for details.

---

**Made with ❤️ by the OpenMined community** 