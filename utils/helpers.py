"""
Utility helpers: file scanning, text cleaning, formatting.
"""

import os
from pathlib import Path
from typing import List, Dict
import config


def scan_project_files(project_path: str) -> List[Dict]:
    """
    Recursively scans a project directory and returns metadata for each
    supported source file.

    Returns a list of dicts:
        {"path": str, "relative": str, "extension": str, "size": int}
    """
    files = []
    root = Path(project_path)

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in config.IGNORE_DIRS]

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext in config.SUPPORTED_EXTENSIONS:
                full = Path(dirpath) / fname
                files.append({
                    "path": str(full),
                    "relative": str(full.relative_to(root)),
                    "extension": ext,
                    "size": full.stat().st_size,
                })
    return files


def read_file_safe(path: str, max_chars: int = 500_000) -> str:
    """Read a file with encoding fallback and size limit."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_chars)
    except Exception:
        return ""


def truncate(text: str, max_len: int = 1500) -> str:
    """Truncate text to max_len characters with an ellipsis marker."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n... [truncated]"


def detect_android_layer(component_type: str, class_name: str,
                         superclass: str, annotations: List[str]) -> str:
    """Heuristically assign an architectural layer."""
    name_lower = class_name.lower()
    super_lower = (superclass or "").lower()
    ann_str = " ".join(annotations).lower()

    # UI layer
    if component_type in ("Activity", "Fragment") or \
       "activity" in super_lower or "fragment" in super_lower or \
       name_lower.endswith("activity") or name_lower.endswith("fragment"):
        return "UI"

    # ViewModel
    if "viewmodel" in super_lower or "viewmodel" in name_lower:
        return "Business Logic"

    # Repository / UseCase
    if "repository" in name_lower or "usecase" in name_lower or \
       "interactor" in name_lower:
        return "Business Logic"

    # Data layer
    if "dao" in name_lower or "database" in name_lower or \
       "entity" in ann_str or "table" in ann_str or \
       "model" in name_lower or "dto" in name_lower:
        return "Data"

    # Service
    if "service" in super_lower or name_lower.endswith("service"):
        return "Service"

    # DI
    if "module" in ann_str or "component" in ann_str or "inject" in ann_str:
        return "DI"

    return "Other"
