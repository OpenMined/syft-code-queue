"""
SyftBox File Permission Utilities

Minimal utilities for reading, setting, and removing permissions for individual files in SyftBox.
"""

import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any

# Try to import SyftBox client for proper file management
try:
    from syft_core import Client as SyftBoxClient
    from syft_core.url import SyftBoxURL
    SYFTBOX_AVAILABLE = True
except ImportError:
    SyftBoxClient = None
    SyftBoxURL = None
    SYFTBOX_AVAILABLE = False

__version__ = "0.1.0"

def _get_syftbox_client() -> Optional[SyftBoxClient]:
    """Get SyftBox client if available, otherwise return None"""
    if not SYFTBOX_AVAILABLE:
        return None
    try:
        return SyftBoxClient.load()
    except Exception:
        return None


def _extract_local_path_from_syft_url(syft_url: str) -> Optional[Path]:
    """Extract local path from a syft:// URL if it points to a local SyftBox path"""
    if not SYFTBOX_AVAILABLE:
        return None
    
    try:
        client = SyftBoxClient.load()
        syft_url_obj = SyftBoxURL(syft_url)
        return syft_url_obj.to_local_path(datasites_path=client.datasites)
    except Exception:
        return None


def set_file_permissions(
    file_path_or_syfturl: str,
    read_users: List[str],
    write_users: List[str] = None,
    admin_users: List[str] = None,
) -> None:
    """
    Set permissions for a file (local path or syft:// URL) by updating syft.pub.yaml.
    
    Args:
        file_path_or_syfturl: Local file path or syft:// URL
        read_users: List of users who can read the file
        write_users: List of users who can write the file
        admin_users: List of users who have admin access (defaults to write_users)
    """
    if write_users is None:
        write_users = []
    if admin_users is None:
        admin_users = write_users

    # Resolve to local path if syft://
    if isinstance(file_path_or_syfturl, str) and file_path_or_syfturl.startswith("syft://"):
        file_path = _extract_local_path_from_syft_url(file_path_or_syfturl)
    else:
        file_path = Path(file_path_or_syfturl)
    
    if file_path is None:
        raise ValueError("Could not resolve file path for permissions.")

    target_path = file_path.parent
    file_pattern = file_path.name
    syftpub_path = target_path / "syft.pub.yaml"

    # Ensure target directory exists
    target_path.mkdir(parents=True, exist_ok=True)

    # Format users for SyftBox
    def format_users(users):
        return ["*" if u in ["public", "*"] else u for u in users]

    access_dict = {}
    if read_users:
        access_dict["read"] = format_users(read_users)
    if write_users:
        access_dict["write"] = format_users(write_users)
    if admin_users:
        access_dict["admin"] = format_users(admin_users)
    
    if not access_dict:
        return

    new_rule = {"pattern": file_pattern, "access": access_dict}

    # Read existing syft.pub.yaml
    existing_content = {"rules": []}
    if syftpub_path.exists():
        try:
            with open(syftpub_path, 'r') as f:
                existing_content = yaml.safe_load(f) or {"rules": []}
        except Exception:
            existing_content = {"rules": []}
    
    if "rules" not in existing_content or not isinstance(existing_content["rules"], list):
        existing_content["rules"] = []
    
    # Remove any existing rules for this pattern
    existing_content["rules"] = [
        rule for rule in existing_content["rules"] if rule.get("pattern") != new_rule["pattern"]
    ]
    existing_content["rules"].append(new_rule)
    
    with open(syftpub_path, 'w') as f:
        yaml.dump(existing_content, f, default_flow_style=False, sort_keys=False, indent=2)


def get_file_permissions(file_path_or_syfturl: str) -> Optional[Dict[str, Any]]:
    """
    Read permissions for a file (local path or syft:// URL) from syft.pub.yaml.
    
    Args:
        file_path_or_syfturl: Local file path or syft:// URL
        
    Returns:
        The access dict for the file, or None if not found.
    """
    if isinstance(file_path_or_syfturl, str) and file_path_or_syfturl.startswith("syft://"):
        file_path = _extract_local_path_from_syft_url(file_path_or_syfturl)
    else:
        file_path = Path(file_path_or_syfturl)
    
    if file_path is None:
        return None
    
    syftpub_path = file_path.parent / "syft.pub.yaml"
    if not syftpub_path.exists():
        return None
    
    try:
        with open(syftpub_path, 'r') as f:
            content = yaml.safe_load(f) or {"rules": []}
        for rule in content.get("rules", []):
            if rule.get("pattern") == file_path.name:
                return rule.get("access")
    except Exception:
        return None
    
    return None


def remove_file_permissions(file_path_or_syfturl: str) -> None:
    """
    Remove permissions for a file (local path or syft:// URL) from syft.pub.yaml.
    
    Args:
        file_path_or_syfturl: Local file path or syft:// URL
    """
    if isinstance(file_path_or_syfturl, str) and file_path_or_syfturl.startswith("syft://"):
        file_path = _extract_local_path_from_syft_url(file_path_or_syfturl)
    else:
        file_path = Path(file_path_or_syfturl)
    
    if file_path is None:
        return
    
    syftpub_path = file_path.parent / "syft.pub.yaml"
    if not syftpub_path.exists():
        return
    
    try:
        with open(syftpub_path, 'r') as f:
            content = yaml.safe_load(f) or {"rules": []}
        new_rules = [rule for rule in content.get("rules", []) if rule.get("pattern") != file_path.name]
        content["rules"] = new_rules
        with open(syftpub_path, 'w') as f:
            yaml.dump(content, f, default_flow_style=False, sort_keys=False, indent=2)
    except Exception:
        pass


# Export the main functions
__all__ = [
    "set_file_permissions",
    "get_file_permissions", 
    "remove_file_permissions",
    "SYFTBOX_AVAILABLE",
] 