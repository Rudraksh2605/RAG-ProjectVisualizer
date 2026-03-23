import json
import os
from datetime import datetime
from typing import Dict, List, Optional

HISTORY_FILE = ".visualizer_history.json"

def _load_history() -> Dict:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"projects": {}, "chats": {}}

def _save_history(data: Dict):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def add_project_history(path: str, stats: Dict):
    """Save/update project indexing history."""
    data = _load_history()
    
    # Store minimal stats and timestamp
    data["projects"][path] = {
        "last_accessed": datetime.now().isoformat(),
        "stats": {
            "total_files": stats.get("total_files", stats.get("parsed", 0)),
            "total_chunks": stats.get("total_chunks", stats.get("chunks", 0))
        }
    }
    _save_history(data)

def get_all_projects() -> List[Dict]:
    """Return a list of projects sorted by last accessed."""
    data = _load_history()
    projects = []
    for path, info in data.get("projects", {}).items():
        projects.append({
            "path": path,
            "last_accessed": info.get("last_accessed", ""),
            "stats": info.get("stats", {})
        })
    # Sort descending by last accessed
    projects.sort(key=lambda x: x["last_accessed"], reverse=True)
    return projects

def save_chat_history(project_path: str, chat_history: List[Dict]):
    """Save chat history for a specific project."""
    if not project_path:
        return
    data = _load_history()
    data["chats"][project_path] = chat_history
    _save_history(data)

def load_chat_history(project_path: str) -> List[Dict]:
    """Load chat history for a specific project."""
    if not project_path:
        return []
    data = _load_history()
    return data.get("chats", {}).get(project_path, [])
