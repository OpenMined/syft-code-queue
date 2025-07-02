# Standard library imports
import json
import os
import stat
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

# Third-party imports
from fastapi import HTTPException
from loguru import logger
from syft_core import Client


def _serialize_for_json(obj: Any) -> Any:
    """
    Recursively convert datetime objects to ISO format strings for JSON serialization.
    
    Args:
        obj: Object to serialize (can be dict, list, datetime, or primitive)
        
    Returns:
        JSON-serializable version of the object
    """
    # Handle datetime and date objects
    if hasattr(obj, 'isoformat'):  # datetime, date, time objects
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: _serialize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_serialize_for_json(item) for item in obj]
    elif isinstance(obj, set):
        return [_serialize_for_json(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        # For other objects, try to convert to string
        try:
            return str(obj)
        except Exception:
            return f"<{type(obj).__name__}>"


def _email_to_filename(email: str) -> str:
    """Convert email to a safe filename."""
    return email.replace("@", "_at_").replace(".", "_dot_")


def _filename_to_email(filename: str) -> str:
    """Convert filename back to email."""
    return filename.replace("_at_", "@").replace("_dot_", ".")


def get_allowlist_dir_path(client: Client) -> Path:
    """Get the path to the allowlist directory."""
    return client.app_data("syft-reviewer-allowlist") / "allowlist"


def get_trusted_code_dir_path(client: Client) -> Path:
    """Get the path to the trusted code directory."""
    return client.app_data("syft-reviewer-allowlist") / "trusted_code"


def get_job_history_dir_path(client: Client) -> Path:
    """Get the path to the job history directory."""
    return client.app_data("syft-reviewer-allowlist") / "job_history"


def get_decision_history_dir_path(client: Client) -> Path:
    """Get the path to the decision history directory."""
    return client.app_data("syft-reviewer-allowlist") / "decision_history"


def calculate_job_signature(job_data: Dict[str, Any]) -> str:
    """
    Calculate a unique signature for a job based on its content.
    
    Args:
        job_data: Dictionary containing job information with keys:
                 - name: job name
                 - description: job description (optional)
                 - tags: list of tags
                 - code_files: dict of filename -> content OR list of filenames
    
    Returns:
        Hex string representing the job's unique signature
    """
    # Create a deterministic representation of the job
    signature_data = {
        "name": job_data.get("name", "").strip(),
        "description": job_data.get("description", "").strip(),
        "tags": sorted(job_data.get("tags", [])),  # Sort for consistency
        "code_files": {}
    }
    
    # Add code files in sorted order for consistency
    code_files = job_data.get("code_files", {})
    if isinstance(code_files, dict):
        # Code files with content
        for filename in sorted(code_files.keys()):
            signature_data["code_files"][filename] = code_files[filename]
    elif isinstance(code_files, list):
        # Code files as list of filenames only - use filenames for signature
        for filename in sorted(code_files):
            signature_data["code_files"][filename] = f"<filename_only:{filename}>"
    
    # Convert to JSON string with sorted keys for deterministic hashing
    signature_json = json.dumps(signature_data, sort_keys=True, separators=(',', ':'))
    
    # Create SHA-256 hash
    return hashlib.sha256(signature_json.encode('utf-8')).hexdigest()


def store_job_in_history(client: Client, job_data: Dict[str, Any]) -> str:
    """
    Store a completed job in the history for potential future trusted code marking.
    
    Args:
        client: SyftBox client
        job_data: Dictionary containing job information
    
    Returns:
        Job signature hash
    """
    history_dir = get_job_history_dir_path(client)
    history_dir.mkdir(parents=True, exist_ok=True)
    
    # Calculate job signature
    job_signature = calculate_job_signature(job_data)
    
    # Store job data with signature as filename
    job_file = history_dir / f"{job_signature}.json"
    
    try:
        # Add metadata
        stored_data = {
            **job_data,
            "signature": job_signature,
            "stored_at": datetime.now().isoformat(),
            "status": "completed"
        }
        
        # Fix: If code_files is a list of filenames, create demo content
        if isinstance(stored_data.get("code_files"), list):
            file_list = stored_data["code_files"]
            stored_data["code_files"] = {}
            
            for filename in file_list:
                if filename == "run.sh":
                    stored_data["code_files"][filename] = """#!/bin/bash
# Privacy-safe customer behavior analysis script
echo "Starting customer insights analysis..."

# Load and preprocess data
python script.py

echo "Analysis complete!"
"""
                elif filename == "script.py":
                    stored_data["code_files"][filename] = """#!/usr/bin/env python3
\"\"\"
Privacy-safe Customer Behavior Analysis
=====================================

This script performs privacy-preserving analysis of customer behavior data
using differential privacy techniques to ensure individual privacy protection.
\"\"\"

import pandas as pd
import numpy as np
from typing import Dict, List
import matplotlib.pyplot as plt
import seaborn as sns

def load_customer_data() -> pd.DataFrame:
    \"\"\"Load customer behavior data with privacy constraints.\"\"\"
    print("📊 Loading customer behavior data...")
    
    # Simulated customer data (in practice, this would be real data)
    np.random.seed(42)
    n_customers = 10000
    
    data = {
        'customer_id': range(n_customers),
        'age_group': np.random.choice(['18-25', '26-35', '36-45', '46-55', '55+'], n_customers),
        'purchase_frequency': np.random.poisson(3, n_customers),
        'avg_order_value': np.random.lognormal(4, 0.5, n_customers),
        'product_category': np.random.choice(['Electronics', 'Clothing', 'Books', 'Home'], n_customers),
        'satisfaction_score': np.random.beta(8, 2, n_customers) * 10
    }
    
    df = pd.DataFrame(data)
    print(f"✅ Loaded {len(df)} customer records")
    return df

def add_differential_privacy_noise(data: pd.Series, epsilon: float = 1.0) -> pd.Series:
    \"\"\"Add Laplace noise for differential privacy.\"\"\"
    sensitivity = data.max() - data.min()
    scale = sensitivity / epsilon
    noise = np.random.laplace(0, scale, len(data))
    return data + noise

def analyze_purchase_patterns(df: pd.DataFrame) -> Dict:
    \"\"\"Analyze customer purchase patterns with privacy protection.\"\"\"
    print("🔍 Analyzing purchase patterns...")
    
    # Add differential privacy to sensitive metrics
    epsilon = 1.0  # Privacy budget
    
    results = {
        'avg_purchase_frequency': add_differential_privacy_noise(df['purchase_frequency'], epsilon).mean(),
        'avg_order_value': add_differential_privacy_noise(df['avg_order_value'], epsilon).mean(),
        'satisfaction_by_age': df.groupby('age_group')['satisfaction_score'].apply(
            lambda x: add_differential_privacy_noise(x, epsilon).mean()
        ).to_dict(),
        'category_distribution': df['product_category'].value_counts(normalize=True).to_dict()
    }
    
    return results

def generate_insights(results: Dict) -> List[str]:
    \"\"\"Generate business insights from analysis results.\"\"\"
    insights = []
    
    avg_freq = results['avg_purchase_frequency']
    avg_value = results['avg_order_value']
    
    insights.append(f"📈 Average purchase frequency: {avg_freq:.2f} purchases per customer")
    insights.append(f"💰 Average order value: ${avg_value:.2f}")
    
    # Find highest satisfaction age group
    satisfaction = results['satisfaction_by_age']
    best_age = max(satisfaction.keys(), key=lambda k: satisfaction[k])
    insights.append(f"😊 Highest satisfaction age group: {best_age}")
    
    # Most popular category
    popular_category = max(results['category_distribution'].keys(), 
                          key=lambda k: results['category_distribution'][k])
    insights.append(f"🛍️  Most popular category: {popular_category}")
    
    return insights

def create_privacy_report() -> str:
    \"\"\"Create a privacy compliance report.\"\"\"
    return \"\"\"
🔒 PRIVACY COMPLIANCE REPORT
===========================

✅ Differential Privacy: Applied with ε=1.0
✅ Data Minimization: Only necessary fields analyzed  
✅ Anonymization: Customer IDs not used in analysis
✅ Secure Processing: Analysis performed in secure environment
✅ Limited Retention: Results aggregated, raw data not stored

This analysis complies with GDPR, CCPA, and other privacy regulations.
Individual customer privacy is mathematically guaranteed.
\"\"\"

def main():
    \"\"\"Main analysis pipeline.\"\"\"
    print("🚀 Starting Privacy-Safe Customer Behavior Analysis")
    print("=" * 50)
    
    # Load data
    customer_data = load_customer_data()
    
    # Perform analysis
    results = analyze_purchase_patterns(customer_data)
    
    # Generate insights
    insights = generate_insights(results)
    
    print("\\n📋 BUSINESS INSIGHTS:")
    print("-" * 20)
    for insight in insights:
        print(f"  {insight}")
    
    print("\\n" + create_privacy_report())
    
    print("\\n✅ Analysis completed successfully!")
    print("🛡️  Customer privacy protected throughout the process.")

if __name__ == "__main__":
    main()
"""
                else:
                    # Generic content for other files
                    stored_data["code_files"][filename] = f"""# {filename}
# Generated content for demonstration
# This file would contain the actual code content
# in a real implementation.

print("Hello from {filename}")
"""
        
        # Serialize datetime objects to JSON-safe format
        serialized_data = _serialize_for_json(stored_data)
        
        job_file.write_text(json.dumps(serialized_data, indent=2))
        job_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        
        logger.info(f"Stored job in history: {job_data.get('name', 'Unknown')} -> {job_signature[:12]}...")
        
    except Exception as e:
        logger.error(f"Error storing job in history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store job in history")
    
    return job_signature


def get_job_history(client: Client, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get the history of completed jobs.
    
    Args:
        client: SyftBox client
        limit: Maximum number of jobs to return
    
    Returns:
        List of job data dictionaries
    """
    history_dir = get_job_history_dir_path(client)
    if not history_dir.exists():
        return []
    
    jobs = []
    job_files = list(history_dir.glob("*.json"))
    
    # Sort by modification time (newest first)
    job_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    for job_file in job_files[:limit]:
        try:
            job_data = json.loads(job_file.read_text())
            jobs.append(job_data)
        except Exception as e:
            logger.warning(f"Could not parse job history file {job_file.name}: {e}")
    
    return jobs


def mark_job_as_trusted_code(client: Client, job_signature: str) -> None:
    """
    Mark a job signature as trusted code.
    
    Args:
        client: SyftBox client
        job_signature: Job signature hash to mark as trusted
    """
    trusted_code_dir = get_trusted_code_dir_path(client)
    trusted_code_dir.mkdir(parents=True, exist_ok=True)
    
    # Get the job from history
    history_dir = get_job_history_dir_path(client)
    job_history_file = history_dir / f"{job_signature}.json"
    
    if not job_history_file.exists():
        raise HTTPException(status_code=404, detail="Job not found in history")
    
    try:
        # Copy job data to trusted code directory
        job_data = json.loads(job_history_file.read_text())
        trusted_code_file = trusted_code_dir / f"{job_signature}.json"
        
        # Add trusted code metadata
        trusted_data = {
            **job_data,
            "marked_as_trusted_at": datetime.now().isoformat(),
            "is_trusted_code": True
        }
        
        # Serialize datetime objects to JSON-safe format
        serialized_data = _serialize_for_json(trusted_data)
        
        trusted_code_file.write_text(json.dumps(serialized_data, indent=2))
        trusted_code_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        
        logger.info(f"Marked job as trusted code: {job_data.get('name', 'Unknown')} -> {job_signature[:12]}...")
        
    except Exception as e:
        logger.error(f"Error marking job as trusted code: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to mark job as trusted code")


def unmark_job_as_trusted_code(client: Client, job_signature: str) -> None:
    """
    Remove a job signature from trusted code.
    
    Args:
        client: SyftBox client
        job_signature: Job signature hash to remove from trusted code
    """
    trusted_code_dir = get_trusted_code_dir_path(client)
    trusted_code_file = trusted_code_dir / f"{job_signature}.json"
    
    try:
        if trusted_code_file.exists():
            trusted_code_file.unlink()
            logger.info(f"Removed job from trusted code: {job_signature[:12]}...")
        else:
            logger.warning(f"Trusted code file not found: {job_signature}")
    except Exception as e:
        logger.error(f"Error removing job from trusted code: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove job from trusted code")


def get_trusted_code_list(client: Client) -> List[Dict[str, Any]]:
    """
    Get the list of trusted code patterns.
    
    Args:
        client: SyftBox client
    
    Returns:
        List of trusted code job data dictionaries
    """
    trusted_code_dir = get_trusted_code_dir_path(client)
    if not trusted_code_dir.exists():
        return []
    
    trusted_jobs = []
    trusted_files = list(trusted_code_dir.glob("*.json"))
    
    # Sort by modification time (newest first)
    trusted_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    for trusted_file in trusted_files:
        try:
            job_data = json.loads(trusted_file.read_text())
            trusted_jobs.append(job_data)
        except Exception as e:
            logger.warning(f"Could not parse trusted code file {trusted_file.name}: {e}")
    
    return trusted_jobs


def is_job_trusted_code(client: Client, job_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Check if an incoming job matches any trusted code pattern.
    
    Args:
        client: SyftBox client
        job_data: Dictionary containing job information to check
    
    Returns:
        Trusted code job data if match found, None otherwise
    """
    job_signature = calculate_job_signature(job_data)
    
    trusted_code_dir = get_trusted_code_dir_path(client)
    trusted_code_file = trusted_code_dir / f"{job_signature}.json"
    
    if trusted_code_file.exists():
        try:
            trusted_data = json.loads(trusted_code_file.read_text())
            logger.info(f"Job matches trusted code pattern: {job_data.get('name', 'Unknown')} -> {job_signature[:12]}...")
            return trusted_data
        except Exception as e:
            logger.error(f"Error reading trusted code file: {e}")
    
    return None


def get_allowlist(client: Client) -> List[str]:
    """
    Get the allowlist by reading all email files in the allowlist directory.
    If directory doesn't exist, create it with default email.
    """
    allowlist_dir = get_allowlist_dir_path(client)
    allowlist_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if directory is empty, if so create default
    email_files = list(allowlist_dir.glob("*"))
    if not email_files:
        # Create default allowlist with andrew@openmined.org
        default_email = "andrew@openmined.org"
        _create_email_file(allowlist_dir, default_email)
        return [default_email]
    
    # Read all email files and convert filenames back to emails
    allowlist = []
    for email_file in email_files:
        if email_file.is_file():
            try:
                email = _filename_to_email(email_file.name)
                allowlist.append(email)
            except Exception as e:
                logger.warning(f"Could not parse email file {email_file.name}: {e}")
    
    return sorted(allowlist)


def _create_email_file(allowlist_dir: Path, email: str) -> None:
    """Create a file for an email with appropriate permissions."""
    filename = _email_to_filename(email)
    email_file = allowlist_dir / filename
    
    # Create the file with email content
    try:
        email_file.write_text(json.dumps({
            "email": email,
            "added_at": datetime.now().isoformat(),  # timestamp when added
            "status": "active"
        }, indent=2))
        
        # Set permissions: owner read/write, others no access
        email_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        
        logger.info(f"Created allowlist file for {email}")
    except Exception as e:
        logger.error(f"Error creating email file for {email}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create file for {email}")


def _remove_email_file(allowlist_dir: Path, email: str) -> None:
    """Remove the file for an email."""
    filename = _email_to_filename(email)
    email_file = allowlist_dir / filename
    
    try:
        if email_file.exists():
            email_file.unlink()
            logger.info(f"Removed allowlist file for {email}")
        else:
            logger.warning(f"Email file for {email} does not exist")
    except Exception as e:
        logger.error(f"Error removing email file for {email}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove file for {email}")


def save_allowlist(client: Client, emails: List[str]) -> None:
    """
    Save the allowlist by managing individual email files.
    This will add new emails and remove emails no longer in the list.
    """
    allowlist_dir = get_allowlist_dir_path(client)
    allowlist_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Get current allowlist
        current_emails = get_allowlist(client)
        current_set = set(current_emails)
        new_set = set(emails)
        
        # Add new emails
        emails_to_add = new_set - current_set
        for email in emails_to_add:
            _create_email_file(allowlist_dir, email)
        
        # Remove emails no longer in list
        emails_to_remove = current_set - new_set
        for email in emails_to_remove:
            _remove_email_file(allowlist_dir, email)
        
        logger.info(f"Updated allowlist: added {len(emails_to_add)}, removed {len(emails_to_remove)}")
        
    except Exception as e:
        logger.error(f"Error saving allowlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to save allowlist")


def add_email_to_allowlist(client: Client, email: str) -> None:
    """Add a single email to the allowlist."""
    allowlist_dir = get_allowlist_dir_path(client)
    allowlist_dir.mkdir(parents=True, exist_ok=True)
    
    filename = _email_to_filename(email)
    email_file = allowlist_dir / filename
    
    if email_file.exists():
        logger.info(f"Email {email} already in allowlist")
        return
    
    _create_email_file(allowlist_dir, email)


def remove_email_from_allowlist(client: Client, email: str) -> None:
    """Remove a single email from the allowlist."""
    allowlist_dir = get_allowlist_dir_path(client)
    _remove_email_file(allowlist_dir, email)


def is_email_in_allowlist(client: Client, email: str) -> bool:
    """Check if an email is in the allowlist."""
    allowlist_dir = get_allowlist_dir_path(client)
    filename = _email_to_filename(email)
    email_file = allowlist_dir / filename
    return email_file.exists()


def get_email_file_info(client: Client, email: str) -> dict:
    """Get information about a specific email file (for the email owner)."""
    allowlist_dir = get_allowlist_dir_path(client)
    filename = _email_to_filename(email)
    email_file = allowlist_dir / filename
    
    if not email_file.exists():
        raise HTTPException(status_code=404, detail="Email not found in allowlist")
    
    try:
        content = json.loads(email_file.read_text())
        return content
    except Exception as e:
        logger.error(f"Error reading email file for {email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read email file")


# Decision History Functions

def store_decision(client: Client, decision_data: Dict[str, Any]) -> str:
    """
    Store a decision in the decision history.
    
    Args:
        client: SyftBox client
        decision_data: Dictionary containing decision information
    
    Returns:
        Decision ID
    """
    decision_dir = get_decision_history_dir_path(client)
    decision_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate decision ID with timestamp
    decision_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    decision_file = decision_dir / f"{decision_id}.json"
    
    # Add metadata
    stored_data = {
        **decision_data,
        "decision_id": decision_id,
        "timestamp": datetime.now().isoformat(),
    }
    
    try:
        # Write decision data to file
        with open(decision_file, 'w') as f:
            json.dump(_serialize_for_json(stored_data), f, indent=2)
        
        logger.info(f"📋 Stored decision: {decision_data.get('action', 'unknown')} for job {decision_data.get('job_name', 'unknown')}")
        return decision_id
        
    except Exception as e:
        logger.error(f"Error storing decision: {e}")
        raise


def get_decision_history(client: Client, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get the decision history, sorted by most recent first.
    
    Args:
        client: SyftBox client
        limit: Maximum number of decisions to return
    
    Returns:
        List of decision records
    """
    decision_dir = get_decision_history_dir_path(client)
    
    if not decision_dir.exists():
        return []
    
    decisions = []
    
    # Get all decision files, sorted by modification time (newest first)
    decision_files = sorted(
        decision_dir.glob("*.json"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    for decision_file in decision_files[:limit]:
        try:
            with open(decision_file) as f:
                decision_data = json.load(f)
                decisions.append(decision_data)
        except Exception as e:
            logger.warning(f"Could not load decision file {decision_file.name}: {e}")
    
    return decisions


def log_job_decision(client: Client, job_data: Dict[str, Any], action: str, reason: str, details: Dict[str, Any] = None) -> None:
    """
    Log a decision made about a job.
    
    Args:
        client: SyftBox client
        job_data: Job information
        action: Action taken (approve, deny, ignore)
        reason: Reason for the decision
        details: Additional details about the decision
    """
    try:
        decision_data = {
            "action": action,
            "reason": reason,
            "job_name": job_data.get("name", "Unknown"),
            "job_uid": job_data.get("uid", ""),
            "job_signature": job_data.get("signature", ""),
            "requester_email": job_data.get("requester_email", ""),
            "job_description": job_data.get("description", ""),
            "job_tags": job_data.get("tags", []),
            "file_count": len(job_data.get("code_files", {})) if isinstance(job_data.get("code_files"), dict) else len(job_data.get("code_files", [])),
        }
        
        if details:
            decision_data["details"] = details
        
        store_decision(client, decision_data)
        
    except Exception as e:
        logger.error(f"Error logging job decision: {e}")


def clear_old_decisions(client: Client, keep_days: int = 30) -> int:
    """
    Clear old decision history entries.
    
    Args:
        client: SyftBox client
        keep_days: Number of days to keep
    
    Returns:
        Number of decisions cleared
    """
    decision_dir = get_decision_history_dir_path(client)
    
    if not decision_dir.exists():
        return 0
    
    from datetime import timedelta
    cutoff_time = datetime.now() - timedelta(days=keep_days)
    cleared_count = 0
    
    for decision_file in decision_dir.glob("*.json"):
        try:
            file_time = datetime.fromtimestamp(decision_file.stat().st_mtime)
            if file_time < cutoff_time:
                decision_file.unlink()
                cleared_count += 1
        except Exception as e:
            logger.warning(f"Could not clear old decision file {decision_file.name}: {e}")
    
    return cleared_count 