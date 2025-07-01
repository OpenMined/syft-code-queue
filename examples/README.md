# Examples Directory

This directory contains examples and tutorials for using syft-code-queue.

## Tutorials

- **Part 1 — Data Scientist Tutorial.ipynb** - Learn how to submit and monitor jobs as a data scientist
- **Part 2 — Data Owner Tutorial.ipynb** - Learn how to review and approve jobs as a data owner

## Example Code

- **example_cross_datasite_workflow.py** - Demonstrates cross-datasite job submission and approval workflow
- **example_output_viewer.py** - Shows how to use the interactive output viewer functionality  
- **demo_filesystem_ui.py** - Demonstrates the filesystem UI components

## Example Job Packages

- **example_job/** - Sample job package structure with analysis scripts
- **my_analysis_package/** - Another example of how to structure analysis code

## Running Examples

```bash
# Run workflow demonstration
python examples/example_cross_datasite_workflow.py

# Run output viewer demo  
python examples/example_output_viewer.py

# Run filesystem UI demo
python examples/demo_filesystem_ui.py
```

## Tutorial Usage

Open the Jupyter notebooks in your preferred environment:

```bash
jupyter notebook "examples/Part 1 — Data Scientist Tutorial.ipynb"
jupyter notebook "examples/Part 2 — Data Owner Tutorial.ipynb"
```

The tutorials walk through the complete workflow from job submission to result analysis. 