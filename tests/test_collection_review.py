#!/usr/bin/env python3
"""
Test the collection review button fix.
"""

import sys

sys.path.insert(0, "src")

import shutil
import tempfile
from pathlib import Path

import syft_code_queue as q


def test_collection_review():
    """Test that collection review button generates simple code."""

    temp_dir = Path(tempfile.mkdtemp())

    try:
        # Create test files
        (temp_dir / "run.sh").write_text('#!/bin/bash\necho "Collection review test"')

        # Submit job
        job = q.submit_job(
            "test@example.com", temp_dir, "Collection Review Test", "Testing collection review fix"
        )
        print(f"Created job: {job.uid}")

        # Get the collection's HTML representation
        collection = q.pending_for_me
        html_content = collection._repr_html_()

        # Check that the generated code is simple
        if "q.pending_for_me[0].review()" in html_content:
            print("✅ Found simple review code pattern")
        else:
            print("❌ Simple review code pattern not found")

        if "display(" in html_content:
            print("✅ Found display() usage")
        else:
            print("❌ display() usage not found")

        # Check that complex code is NOT present
        if "Find the job by ID" in html_content:
            print("❌ Still contains complex job finding code")
        else:
            print("✅ No complex job finding code found")

        if "for collection_name in" in html_content:
            print("❌ Still contains collection iteration code")
        else:
            print("✅ No collection iteration code found")

        # Save HTML for manual testing
        with open("collection_review_test.html", "w") as f:
            f.write(f"""
<!DOCTYPE html>
<html>
<head>
    <title>Collection Review Test</title>
</head>
<body>
    <h1>Collection Review Test</h1>
    <p>Click the eye button - it should generate simple code like q.pending_for_me[0].review():</p>
    {html_content}
</body>
</html>
""")

        print("\n💾 Saved collection_review_test.html")
        print("🌐 Open this file and click the eye button to test")
        print(
            "💡 Should generate: from IPython.display import display; q.pending_for_me[0].review()"
        )

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    test_collection_review()
