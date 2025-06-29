# 📚 Syft Code Queue Examples

This directory contains comprehensive examples and tutorials for using syft-code-queue.

## 📓 Notebooks

### 📖 [SyftCodeQueue_Tutorial.ipynb](SyftCodeQueue_Tutorial.ipynb)
**Comprehensive tutorial covering all features**

- 🏗️ Creating code packages
- 🚀 Submitting jobs  
- 📊 Monitoring and results
- 🖥️ Running queue servers
- 🛡️ Security features
- 🔧 Configuration options
- 🤖 AI integration examples

*Perfect for learning all aspects of syft-code-queue*

### ⚡ [QuickStart.ipynb](QuickStart.ipynb)
**Get started in 5 minutes**

- Minimal example to submit and run a simple job
- Perfect for first-time users
- Just 4 steps to see it working

## 🐍 Python Scripts

### 📝 [basic_usage.py](basic_usage.py)
**Complete workflow example**

```bash
python basic_usage.py
```

Shows:
- Code package creation
- Job submission and monitoring
- Result retrieval
- Server setup

### 🤖 [nsai_integration.py](nsai_integration.py)
**AI-powered code generation and execution**

```bash
python nsai_integration.py
```

Demonstrates:
- AI code generation (mock)
- Automatic code packaging
- Remote execution of AI-generated code
- AI-powered code review for auto-approval

## 🚀 Quick Examples

### Submit a Simple Job

```python
import syft_code_queue as scq

# Submit code for execution
job = scq.submit_code(
    target_email="data-owner@example.com",
    code_folder="./my_analysis",  # Contains run.sh
    name="Data Analysis",
    tags=["analysis"],
    auto_approval=True
)

print(f"Job submitted: {job.uid}")
```

### Start a Queue Server

```python
import syft_code_queue as scq

# Define approval rules
def approval_rules(job):
    return "demo" in job.tags

# Start server
server = scq.create_server(
    auto_approval_callback=approval_rules,
    max_concurrent_jobs=2
)
server.start()
```

---

**Ready to build something amazing with syft-code-queue? Start with the QuickStart notebook! 🚀**