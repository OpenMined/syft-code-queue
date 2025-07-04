# Changelog

## [0.1.27] - 2025-01-04

### Added
- Enhanced `help()` method with comprehensive getting started guide
- Added `quick_help()` function for brief usage instructions
- Improved help documentation with step-by-step tutorials
- Added practical examples for all major operations
- Added pro tips and resource links in help output

### Changed
- Updated help method to be more beginner-friendly with clear sections
- Reorganized help content for better readability

---

# Cross-Datasite Workflow Changes

## Summary

Modified syft-code-queue to implement a cross-datasite workflow where jobs are stored in the target user's datasite instead of the requester's datasite.

## Changes Made

### Job Creation Flow
- **Before**: Jobs were created in the requester's local datasite
- **After**: Jobs are created in the target user's datasite "pending" folder

### Job Review Flow  
- **Before**: Job approval/rejection happened in the requester's datasite
- **After**: Job approval/rejection moves jobs within the reviewer's own datasite

### Job Discovery
- **Before**: All jobs were stored locally
- **After**: 
  - `list_all_jobs()` - finds jobs submitted TO you (in your local datasite)
  - `list_my_jobs()` - finds jobs submitted BY you (searches across all datasites)

## Technical Changes

### Modified Methods in `CodeQueueClient`:

1. **`submit_code()`**
   - Now sets `job._datasite_path` to target user's datasite
   - Jobs are saved to target's "pending" folder instead of requester's

2. **`approve_job()` and `reject_job()`**
   - Enhanced to ensure jobs move within reviewer's own datasite
   - Added proper error handling for cross-datasite operations

3. **`_copy_code_to_queue()`**
   - Enhanced to handle cross-datasite code copying
   - Added proper error handling for permission issues

4. **`_get_job_dir()`**
   - Modified to respect `_datasite_path` for cross-datasite jobs

5. **`list_my_jobs()`**
   - Now searches across all datasites to find jobs submitted by current user

### New Methods:

1. **`_get_target_queue_dir(target_email)`**
   - Helper method to get target user's datasite queue directory

## Benefits

1. **Clear Job Ownership**: Jobs are stored where they will be executed
2. **Proper Permissions**: Target users have full control over jobs in their datasite
3. **Intuitive Discovery**: Users find jobs in logical locations
4. **Cross-Datasite Support**: Seamless operation across multiple datasites

## Example Usage

```python
from syft_code_queue import create_client

# Alice submits job to Bob
alice_client = create_client()  # alice@example.com
job = alice_client.submit_code(
    target_email="bob@example.com",
    code_folder=Path("./my_analysis"),
    name="Data Analysis"
)
# Job is now in bob@example.com's datasite pending folder

# Bob reviews and approves job  
bob_client = create_client()  # bob@example.com
jobs = bob_client.list_all_jobs()  # Finds jobs in Bob's datasite
bob_client.approve_job(job.uid)  # Moves to Bob's approved folder

# Alice checks her submitted jobs
my_jobs = alice_client.list_my_jobs()  # Searches across all datasites
```

## Compatibility

- Maintains backward compatibility with existing job models
- Existing jobs will continue to work with the enhanced workflow
- No breaking changes to the public API

## Files Modified

- `syft-code-queue/src/syft_code_queue/client.py`

## Files Added

- `syft-code-queue/example_cross_datasite_workflow.py` - Demonstration script
- `syft-code-queue/example_output_viewer.py` - Output viewer demonstration script
- `syft-code-queue/CHANGELOG_CROSS_DATASITE.md` - This changelog

## Additional Features Added

### Job Output Viewer
Added a convenient `.output_viewer` property to the `CodeJob` class that provides an interactive filesystem UI for viewing job output files in Jupyter notebooks.

**New Methods Added:**
- `CodeJob.list_output_files()` - List all files in job's output directory
- `CodeJob.read_output_file(filename)` - Read specific output file contents
- `CodeJob.output_viewer` - Interactive output file browser (property)
- `CodeQueueClient.list_job_output_files()` - Client method to list output files
- `CodeQueueClient.read_job_output_file()` - Client method to read output files

**New Class:**
- `OutputViewerWidget` - Interactive HTML/JavaScript widget for viewing output files

**Features:**
- Interactive file browser with syntax highlighting
- File type detection with appropriate icons
- Content preview with line/character counts
- Support for text, data, image, and result files
- Graceful handling of binary files and errors
- Beautiful UI matching existing code review interface
- Security checks to prevent directory traversal

**Usage:**
```python
# Get a completed job
job = client.get_job(job_uid)

# View output files interactively in Jupyter
job.output_viewer

# Or access files programmatically
files = job.list_output_files()
content = job.read_output_file("results.csv")
``` 