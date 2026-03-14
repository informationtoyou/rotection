"""
Scanner package
"""

from scanner.engine import run_scan, is_scanning
from scanner.progress import scan_progress
from scanner.cache import (
    load_cache, save_cache, get_previous_scans, get_scan_by_id,
    save_scan, delete_scan_by_id, find_duplicate_scan, tag_scan_field,
)
from scanner.constants import FLAG_TYPES

__all__ = [
    "run_scan",
    "is_scanning",
    "scan_progress",
    "load_cache",
    "save_cache",
    "get_previous_scans",
    "get_scan_by_id",
    "save_scan",
    "delete_scan_by_id",
    "find_duplicate_scan",
    "tag_scan_field",
    "FLAG_TYPES",
]
