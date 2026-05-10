"""
Snapshot - Local caching for Tally data snapshots.
Used to provide fallback data when Tally goes offline.
"""
import json
import os
from datetime import datetime

SNAPSHOT_DIR = ".tally_snapshots"


def _ensure_dir():
    """Create snapshot directory if it doesn't exist."""
    if not os.path.exists(SNAPSHOT_DIR):
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def save(cache_key: str, data: str) -> None:
    """Save a data snapshot with timestamp.
    
    Args:
        cache_key: unique name for this data (e.g. "ledgers", "trial_balance")
        data: the data to cache (usually formatted string)
    """
    _ensure_dir()
    file_path = os.path.join(SNAPSHOT_DIR, f"{cache_key}.json")
    snapshot_data = {
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    with open(file_path, "w") as f:
        json.dump(snapshot_data, f, indent=2)


def load(cache_key: str) -> dict | None:
    """Load a cached snapshot.
    
    Args:
        cache_key: unique name for this data
        
    Returns:
        dict with "data" and "timestamp" keys, or None if not found
    """
    _ensure_dir()
    file_path = os.path.join(SNAPSHOT_DIR, f"{cache_key}.json")
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def age_str(cache_key: str) -> str:
    """Get human-readable age of a cached snapshot.
    
    Args:
        cache_key: unique name for this data
        
    Returns:
        string like "5 minutes ago" or "never" if not cached
    """
    cached = load(cache_key)
    if not cached:
        return "never"
    
    timestamp_str = cached.get("timestamp", "")
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        age = datetime.now() - timestamp
        
        seconds = int(age.total_seconds())
        if seconds < 60:
            return f"{seconds} seconds ago"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minutes ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hours ago"
        else:
            days = seconds // 86400
            return f"{days} days ago"
    except Exception:
        return "unknown time"
