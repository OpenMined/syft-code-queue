#!/usr/bin/env python3
"""
Example: Integration between syft-nsai and syft-code-queue.

This shows how syft-nsai can generate code and then execute it remotely
using syft-code-queue.
"""

import tempfile
from pathlib import Path

import syft_code_queue as scq

# This would normally import syft_nsai
# import syft_nsai as nsai


def generate_analysis_code_with_ai(prompt: str) -> str:
    """
    Simulate generating code with syft-nsai.
    In practice, this would use the actual nsai.client.chat.completions.create()
    """
    # This is a mock - normally you'd use:
    # response = nsai.client.chat.completions.create(
    #     messages=[{"role": "user", "content": prompt}],
    #     enclave="andrew@openmined.org"
    # )
    # return response.choices[0].message.content
    
    # Mock generated code based on the prompt
    if "sales analysis" in prompt.lower():
        return """#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def analyze_sales_data():
    \"\"\"Analyze sales data and generate insights.\"\"\"
    print("Starting sales data analysis...")
    
    # Mock data - in practice this would read from the datasite
    data = {
        'month': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        'sales': [1000, 1200, 1100, 1300, 1250, 1400],
        'profit': [200, 240, 220, 260, 250, 280]
    }
    
    df = pd.DataFrame(data)
    print("Data loaded:")
    print(df)
    
    # Calculate metrics
    total_sales = df['sales'].sum()
    avg_profit_margin = (df['profit'].sum() / df['sales'].sum()) * 100
    
    print(f"\\nTotal Sales: ${total_sales:,}")
    print(f"Average Profit Margin: {avg_profit_margin:.1f}%")
    
    # Create visualization
    plt.figure(figsize=(10, 6))
    plt.subplot(1, 2, 1)
    plt.plot(df['month'], df['sales'], marker='o')
    plt.title('Monthly Sales')
    plt.ylabel('Sales ($)')
    
    plt.subplot(1, 2, 2)
    plt.plot(df['month'], df['profit'], marker='o', color='green')
    plt.title('Monthly Profit')
    plt.ylabel('Profit ($)')
    
    plt.tight_layout()
    plt.savefig(f'{os.environ["SYFT_OUTPUT_DIR"]}/sales_analysis.png')
    
    # Save results
    results = {
        'total_sales': total_sales,
        'avg_profit_margin': avg_profit_margin,
        'growth_rate': ((df['sales'].iloc[-1] - df['sales'].iloc[0]) / df['sales'].iloc[0]) * 100
    }
    
    import json
    with open(f'{os.environ["SYFT_OUTPUT_DIR"]}/results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("Analysis complete! Results saved.")

if __name__ == "__main__":
    analyze_sales_data()
"""
    else:
        return """#!/usr/bin/env python3
print("Hello from AI-generated code!")
print(f"Job ID: {os.environ.get('SYFT_JOB_ID', 'unknown')}")
print(f"Output dir: {os.environ.get('SYFT_OUTPUT_DIR', 'unknown')}")

with open(f'{os.environ["SYFT_OUTPUT_DIR"]}/output.txt', 'w') as f:
    f.write("AI-generated analysis complete!\\n")
"""


def create_code_package(python_code: str, requirements: list = None) -> Path:
    """Create a complete code package ready for execution."""
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp())
    
    # Write Python code
    (temp_dir / "analysis.py").write_text(python_code)
    
    # Create requirements.txt
    if requirements:
        (temp_dir / "requirements.txt").write_text("\n".join(requirements))
    else:
        (temp_dir / "requirements.txt").write_text("pandas\nmatplotlib\nseaborn\n")
    
    # Create run.sh wrapper
    run_script = temp_dir / "run.sh"
    run_script.write_text("""#!/bin/bash
set -e

echo "🚀 Starting AI-generated analysis..."
echo "Job: $SYFT_JOB_NAME"
echo "Requester: $SYFT_REQUESTER"
echo "Output: $SYFT_OUTPUT_DIR"

# Install requirements
if [ -f requirements.txt ]; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Run the analysis
echo "🔍 Running analysis..."
python analysis.py

echo "✅ Analysis complete!"
""")
    
    run_script.chmod(0o755)
    return temp_dir


def ai_powered_remote_execution():
    """Example of using AI to generate code and execute it remotely."""
    print("🤖 AI-Powered Remote Execution Example")
    print("=" * 50)
    
    # 1. User provides natural language request
    user_request = """
    I need to analyze sales data for the last 6 months. 
    Please create a Python script that:
    - Loads the sales data
    - Calculates key metrics (total sales, profit margins)
    - Creates visualizations
    - Saves results as JSON and charts as PNG
    """
    
    print(f"📝 User request: {user_request[:100]}...")
    
    # 2. Generate code using AI (mock)
    print("\n🧠 Generating code with AI...")
    generated_code = generate_analysis_code_with_ai(user_request)
    print(f"   Generated {len(generated_code)} characters of code")
    
    # 3. Package the code
    print("\n📦 Creating code package...")
    code_package = create_code_package(
        generated_code, 
        requirements=["pandas", "matplotlib", "seaborn"]
    )
    print(f"   Package created: {code_package}")
    
    # 4. Submit for remote execution
    print("\n🚀 Submitting to remote datasite...")
    target_email = "data-owner@company.com"  # Replace with actual datasite
    
    job = scq.submit_code(
        target_email=target_email,
        code_folder=code_package,
        name="AI-Generated Sales Analysis",
        description="Analysis code generated by AI from natural language request",
        tags=["ai-generated", "sales-analysis", "automated"],
        auto_approval=True  # Trust AI-generated code with proper tags
    )
    
    print(f"   ✅ Job submitted: {job.uid}")
    print(f"   Status: {job.status.value}")
    
    # 5. Monitor execution
    print("\n⏳ Monitoring execution...")
    client = scq.create_client()
    
    import time
    for i in range(60):  # Check for 1 minute
        current_job = client.get_job(job.uid)
        if not current_job:
            print("   ❌ Job not found!")
            break
        
        print(f"   Status: {current_job.status.value}")
        
        if current_job.is_terminal:
            if current_job.status == scq.JobStatus.completed:
                print("   🎉 AI-generated analysis completed successfully!")
                
                # Get results
                output_path = client.get_job_output(job.uid)
                if output_path:
                    print(f"   📊 Results available at: {output_path}")
                    
                    # Show specific outputs
                    results_file = output_path / "results.json"
                    if results_file.exists():
                        import json
                        results = json.loads(results_file.read_text())
                        print("   📈 Key metrics:")
                        for key, value in results.items():
                            print(f"      {key}: {value}")
                
            else:
                print(f"   ❌ Job {current_job.status.value}")
                if current_job.error_message:
                    print(f"   Error: {current_job.error_message}")
            break
        
        time.sleep(2)
    
    print("\n✅ AI-powered execution example completed!")


def ai_code_review_approval():
    """Example of using AI to review and approve code submissions."""
    print("\n🔍 AI Code Review for Auto-Approval")
    print("=" * 40)
    
    def ai_code_reviewer(job: scq.CodeJob) -> bool:
        """AI-powered code review for auto-approval."""
        try:
            # Read the code
            run_script = job.code_folder / "run.sh"
            if not run_script.exists():
                return False
            
            script_content = run_script.read_text()
            
            # Check for Python analysis code
            if "analysis.py" in script_content and job.code_folder / "analysis.py":
                python_code = (job.code_folder / "analysis.py").read_text()
                
                # Simple AI-like checks (in practice, use actual AI)
                safe_patterns = [
                    "pandas", "matplotlib", "seaborn", "numpy",
                    "json.dump", "print(", "plt.savefig"
                ]
                
                dangerous_patterns = [
                    "os.system", "subprocess.call", "eval(", "exec(",
                    "open(", "__import__", "rm -rf", "DELETE"
                ]
                
                # Check for safe patterns
                has_safe_patterns = any(pattern in python_code for pattern in safe_patterns)
                has_dangerous_patterns = any(pattern in python_code for pattern in dangerous_patterns)
                
                if has_safe_patterns and not has_dangerous_patterns:
                    print(f"   ✅ AI approved code for job: {job.name}")
                    return True
                elif has_dangerous_patterns:
                    print(f"   ❌ AI rejected code (dangerous patterns): {job.name}")
                    return False
            
            # Default: require manual review
            print(f"   ⚠️  AI requires manual review for: {job.name}")
            return False
            
        except Exception as e:
            print(f"   ❌ AI review failed: {e}")
            return False
    
    # Create server with AI reviewer
    server = scq.create_server(
        auto_approval_callback=ai_code_reviewer,
        max_concurrent_jobs=2
    )
    
    print("🤖 Starting server with AI code reviewer...")
    server.start()
    
    try:
        print("Server running with AI auto-approval...")
        time.sleep(10)  # Run briefly for demo
    finally:
        server.stop()
        print("Server stopped.")


if __name__ == "__main__":
    # Run the main example
    ai_powered_remote_execution()
    
    # Optionally run the AI reviewer example
    # ai_code_review_approval() 