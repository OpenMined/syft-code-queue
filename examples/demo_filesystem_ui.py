#!/usr/bin/env python3
"""
Demo of the new Interactive Filesystem UI for Code Review

This demonstrates the enhanced .review() method that shows a beautiful
two-panel file browser for reviewing job code submissions.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from src.syft_code_queue.models import CodeJob, JobStatus


def create_demo_job():
    """Create a demo job with sample files."""

    # Create temporary directory with sample files
    temp_dir = Path(tempfile.mkdtemp())

    # Create sample files
    (temp_dir / "run.sh").write_text("""#!/bin/bash
echo "🚀 Starting healthcare data analysis..."
echo "Installing dependencies..."
pip install -r requirements.txt

echo "Running analysis..."
python analyze_data.py

echo "Generating report..."
python generate_report.py

echo "✅ Analysis complete! Check output/ directory for results."
""")

    (temp_dir / "analyze_data.py").write_text('''import pandas as pd
import numpy as np
from pathlib import Path

def load_data():
    """Load patient data (simulated)."""
    print("📊 Loading patient data...")
    # Simulate loading data
    data = {
        'patient_id': range(1, 1001),
        'age': np.random.randint(18, 90, 1000),
        'condition': np.random.choice(['A', 'B', 'C'], 1000),
        'treatment_outcome': np.random.choice(['Improved', 'Stable', 'Declined'], 1000)
    }
    return pd.DataFrame(data)

def analyze_outcomes(df):
    """Perform privacy-safe statistical analysis."""
    print("🔍 Analyzing treatment outcomes...")

    # Aggregate statistics only - no individual records
    summary = df.groupby(['condition', 'treatment_outcome']).size().reset_index(name='count')
    age_stats = df.groupby('condition')['age'].agg(['mean', 'std', 'count'])

    return summary, age_stats

def main():
    """Main analysis function."""
    print("🏥 Healthcare Data Analysis Starting...")

    # Load and analyze data
    df = load_data()
    summary, age_stats = analyze_outcomes(df)

    # Save results
    output_dir = Path('output')
    output_dir.mkdir(exist_ok=True)

    summary.to_csv(output_dir / 'treatment_summary.csv', index=False)
    age_stats.to_csv(output_dir / 'age_statistics.csv')

    print("✅ Analysis complete!")
    print(f"📁 Results saved to {output_dir}/")

if __name__ == "__main__":
    main()
''')

    (temp_dir / "generate_report.py").write_text('''import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

def generate_visualizations():
    """Generate privacy-safe visualizations."""
    print("📈 Generating visualizations...")

    # Load aggregated results
    summary = pd.read_csv('output/treatment_summary.csv')
    age_stats = pd.read_csv('output/age_statistics.csv')

    # Create plots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Treatment outcomes by condition
    pivot = summary.pivot(index='condition', columns='treatment_outcome', values='count')
    pivot.plot(kind='bar', ax=ax1, title='Treatment Outcomes by Condition')
    ax1.set_ylabel('Number of Patients')

    # Age distribution by condition
    age_stats['mean'].plot(kind='bar', ax=ax2, title='Average Age by Condition')
    ax2.set_ylabel('Average Age')

    plt.tight_layout()
    plt.savefig('output/analysis_report.png', dpi=300, bbox_inches='tight')
    plt.close()

    print("✅ Visualizations saved!")

def main():
    """Generate the final report."""
    print("📋 Generating final report...")
    generate_visualizations()

    # Create summary report
    with open('output/README.md', 'w') as f:
        f.write("""# Healthcare Data Analysis Report

## Summary
This analysis examined treatment outcomes across different patient conditions
using privacy-preserving statistical methods.

## Files Generated
- `treatment_summary.csv`: Aggregated treatment outcomes by condition
- `age_statistics.csv`: Age statistics by condition
- `analysis_report.png`: Visualization of key findings

## Privacy Guarantees
- Only aggregated statistics are reported
- No individual patient records are exposed
- All analyses use differential privacy techniques
- Minimum group sizes enforced to prevent re-identification

## Key Findings
The analysis reveals important patterns in treatment effectiveness
across different patient populations while maintaining strict privacy.
""")

    print("📄 Report generated: output/README.md")

if __name__ == "__main__":
    main()
''')

    (temp_dir / "requirements.txt").write_text("""pandas>=1.3.0
numpy>=1.21.0
matplotlib>=3.4.0
scipy>=1.7.0
scikit-learn>=1.0.0
""")

    (temp_dir / "README.md").write_text("""# Healthcare Data Analysis

## Overview
This project performs privacy-preserving statistical analysis on healthcare data
to identify treatment patterns while protecting patient privacy.

## Features
- ✅ Differential privacy techniques
- ✅ Aggregate-only reporting
- ✅ No individual record exposure
- ✅ Automated report generation
- ✅ Statistical visualizations

## Usage
Run the analysis with:
```bash
bash run.sh
```

## Output
Results will be saved to the `output/` directory including:
- CSV files with aggregated statistics
- PNG visualizations
- Summary report

## Privacy Compliance
This analysis is designed to comply with healthcare privacy regulations
by only reporting aggregate statistics and using privacy-preserving methods.
""")

    # Create the demo job
    job = CodeJob(
        uid=uuid4(),
        name="Healthcare Privacy Analysis",
        requester_email="researcher@university.edu",
        target_email="admin@hospital.org",
        code_folder=temp_dir,
        description="Privacy-preserving statistical analysis of treatment outcomes with differential privacy guarantees",
        status=JobStatus.pending,
        created_at=datetime.now(),
        tags=["healthcare", "privacy", "statistics", "research"],
    )

    return job, temp_dir


def setup_mock_client(job, temp_dir):
    """Set up a mock client for the demo."""

    class MockClient:
        def list_job_files(self, job_uid):
            return [
                "run.sh",
                "analyze_data.py",
                "generate_report.py",
                "requirements.txt",
                "README.md",
            ]

        def read_job_file(self, job_uid, filename):
            file_path = temp_dir / filename
            if file_path.exists():
                return file_path.read_text()
            return None

        def get_job(self, job_uid):
            return job

    job._client = MockClient()
    return job


def main():
    """Run the filesystem UI demo."""
    print("🎯 Interactive Filesystem UI Demo")
    print("=" * 50)

    # Create demo job
    job, temp_dir = create_demo_job()
    job = setup_mock_client(job, temp_dir)

    print("✅ Created demo job with sample files:")
    files = job.list_files()
    for f in files:
        print(f"  📄 {f}")

    print(f"\n📁 Files created in: {temp_dir}")
    print("\n🎉 To see the interactive filesystem UI, run:")
    print("   widget = job.review()")
    print("   # In Jupyter: just run job.review() and it will display automatically!")
    print("\n💡 This returns a Jupyter-compatible widget that displays:")
    print("   • Beautiful two-panel interface (file list + content viewer)")
    print("   • Click on files in the left panel to view them")
    print("   • Syntax highlighting and line numbers")
    print("   • File sizes and metadata")
    print("   • Executable files (run.sh) are highlighted")
    print("   • Approve or reject directly from the UI")
    print("\n🔧 Widget Features:")
    print("   • Proper _repr_html_() method for Jupyter display")
    print("   • Interactive JavaScript file browser")
    print("   • Copy-to-clipboard functionality")
    print("   • Professional, modern UI design")

    # Test the widget creation
    print("\n🧪 Testing widget creation...")
    widget = job.review()
    print(f"✅ Widget type: {type(widget).__name__}")
    print(f"✅ Has _repr_html_: {hasattr(widget, '_repr_html_')}")

    if hasattr(widget, "_repr_html_"):
        html = widget._repr_html_()
        print(f"✅ HTML generated: {len(html):,} characters")
        print("✅ Ready for Jupyter display!")

    # Return the job for interactive use
    return job


if __name__ == "__main__":
    demo_job = main()
    print("\n🔧 Demo job available as 'demo_job' variable")
    print("   Try: demo_job.review()  # Returns Jupyter-compatible widget!")
    print("   In Jupyter: The widget will display automatically ✨")
