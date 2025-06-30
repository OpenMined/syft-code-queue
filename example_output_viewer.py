#!/usr/bin/env python3
"""
Example demonstrating the new .output_viewer functionality for syft-code-queue.

The .output_viewer property provides an interactive filesystem UI for viewing
job output files in Jupyter notebooks, similar to the existing code review functionality.
"""

import tempfile
from pathlib import Path
from syft_code_queue import create_client

def demonstrate_output_viewer():
    """Demonstrate the new output viewer functionality."""
    
    print("=== Job Output Viewer Demo ===\n")
    
    print("The .output_viewer property provides an interactive filesystem UI")
    print("for viewing job output files in Jupyter notebooks.\n")
    
    print("Usage in Jupyter:")
    print("```python")
    print("import syft_code_queue as q")
    print("")
    print("# Get a completed job")
    print("job = q.get_job('some-job-uid')")
    print("")
    print("# View the output files interactively")
    print("job.output_viewer")
    print("```")
    print("")
    
    print("Features of the output viewer:")
    print("✅ Interactive file browser for job output directory")
    print("✅ Syntax highlighting and file type detection")
    print("✅ File content preview with line/character counts")
    print("✅ Support for text, data, and result files")
    print("✅ Beautiful UI matching the existing code review interface")
    print("✅ Automatic handling of binary files")
    print("")
    
    print("Example output file types supported:")
    file_types = {
        "📊 Data files": [".csv", ".tsv", ".json"],
        "📝 Text files": [".txt", ".md", ".log"],
        "🐍 Python files": [".py"],
        "🖼️ Images": [".png", ".jpg", ".svg"],
        "🌐 Web files": [".html", ".htm"],
        "📤 Results": ["output.txt", "results.json"],
        "🎯 Analysis": ["analysis.txt", "report.md"]
    }
    
    for category, extensions in file_types.items():
        print(f"  {category}: {', '.join(extensions)}")
    print("")
    
    print("Error handling:")
    print("• Shows helpful message if no output folder is configured")
    print("• Displays error details if output directory is inaccessible")
    print("• Gracefully handles empty output directories")
    print("• Provides fallback for binary files")
    print("")
    
    print("Integration with existing workflow:")
    print("1. Submit job: `client.submit_code(...)`")
    print("2. Wait for completion: `job.wait_for_completion()`")
    print("3. Review results: `job.output_viewer`")
    print("4. Access specific files: `job.read_output_file('results.csv')`")
    print("")
    
    # Create a mock example structure
    print("Example Jupyter notebook usage:")
    jupyter_example = '''
    # Cell 1: Submit and wait for job
    import syft_code_queue as q
    
    client = q.create_client()
    job = client.submit_code(
        target_email="data-owner@example.com",
        code_folder=Path("./analysis"),
        name="Data Analysis Job"
    )
    
    # Wait for completion
    completed_job = job.wait_for_completion()
    
    # Cell 2: View output interactively
    completed_job.output_viewer
    
    # Cell 3: Access specific files programmatically
    results = completed_job.read_output_file("results.csv")
    print("Results:", results)
    '''
    
    print("```python")
    print(jupyter_example.strip())
    print("```")
    print("")
    
    print("Technical implementation:")
    print("• Added `list_output_files()` and `read_output_file()` methods to CodeJob")
    print("• Created OutputViewerWidget class with interactive HTML/JS interface")
    print("• Added `.output_viewer` property to CodeJob class")
    print("• Integrated with existing client methods for file access")
    print("• Provides security checks to prevent directory traversal")
    print("")
    
    print("The output viewer complements the existing code review functionality,")
    print("providing a complete workflow from code submission to result analysis!")

if __name__ == "__main__":
    demonstrate_output_viewer() 