#!/usr/bin/env python3
"""Test script to demonstrate enhanced syftperm robustness."""

import importlib
import sys

# Force reload to pick up latest changes
if "syft_code_queue" in sys.modules:
    importlib.reload(sys.modules["syft_code_queue"])

import syft_code_queue as q


def test_enhanced_syftperm():
    """Test the enhanced syftperm implementation."""
    print("🔍 Testing enhanced syftperm implementation...")

    # Get the client
    client = q.jobs.client

    # Test 1: Verify current pending directory has correct syftperm
    pending_dir = client._get_status_dir(q.JobStatus.pending)
    syftperm_file = pending_dir / ".syftperm"

    print(f"📁 Pending directory: {pending_dir}")
    print(f"📄 .syftperm exists: {syftperm_file.exists()}")

    if syftperm_file.exists():
        content = syftperm_file.read_text()
        print("✅ Current .syftperm content:")
        print(content)

    # Test 2: Test the enhanced _create_pending_syftperm method
    print("\n🧪 Testing enhanced _create_pending_syftperm method...")

    # Create a test directory
    test_dir = pending_dir.parent / "test_pending"

    try:
        # Test creating syftperm in new directory
        print(f"📁 Creating test directory: {test_dir}")
        client._create_pending_syftperm(test_dir)

        test_syftperm = test_dir / ".syftperm"
        if test_syftperm.exists():
            print("✅ Successfully created .syftperm in new directory")
            content = test_syftperm.read_text()
            if "read:" in content and "write:" in content and "'*'" in content:
                print("✅ .syftperm has correct permissions")
            else:
                print("❌ .syftperm has incorrect permissions")
        else:
            print("❌ Failed to create .syftperm file")

        # Test updating existing syftperm with wrong content
        print("\n🔄 Testing syftperm update functionality...")
        wrong_content = "wrong content"
        test_syftperm.write_text(wrong_content)

        # Call _create_pending_syftperm again - should detect wrong content and fix it
        client._create_pending_syftperm(test_dir)

        updated_content = test_syftperm.read_text()
        if "rules:" in updated_content and "'*'" in updated_content:
            print("✅ Successfully updated incorrect .syftperm file")
        else:
            print("❌ Failed to update incorrect .syftperm file")

    except Exception as e:
        print(f"❌ Error during enhanced syftperm test: {e}")

    finally:
        # Clean up test directory
        try:
            import shutil

            if test_dir.exists():
                shutil.rmtree(test_dir)
                print("🧹 Cleaned up test directory")
        except Exception:
            pass

    print("\n🎉 Enhanced syftperm test completed!")


if __name__ == "__main__":
    test_enhanced_syftperm()
