"""Background indexer for automatic drive scanning and periodic updates."""

import os
import platform
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Set
from dataclasses import dataclass

from .indexer import FileIndexer


@dataclass
class DriveInfo:
    """Information about a detected drive."""
    path: str
    name: str
    total_size: int
    free_space: int
    drive_type: str  # 'fixed', 'removable', 'network', 'unknown'


class BackgroundIndexer:
    """Manages automatic indexing of all drives with periodic updates."""
    
    def __init__(self, indexer: FileIndexer, update_interval: int = 300):
        """Initialize background indexer.
        
        Args:
            indexer: FileIndexer instance to use
            update_interval: Interval in seconds between incremental updates (default 5 min)
        """
        self.indexer = indexer
        self.update_interval = update_interval
        self._stop_flag = threading.Event()
        self._index_thread: Optional[threading.Thread] = None
        self._update_thread: Optional[threading.Thread] = None
        self._is_indexing = False
        self._indexed_drives: Set[str] = set()
        self._progress_callback: Optional[Callable] = None
        self._status_callback: Optional[Callable] = None
        self._exclude_dirs: Set[str] = {
            '.git', '__pycache__', 'node_modules', '.venv', 'venv',
            '.idea', '.vscode', '.cache', '.npm', '.nuget',
            'Windows', 'Program Files', 'Program Files (x86)',
            '$Recycle.Bin', '$RECYCLE.BIN', 'System Volume Information',
            '.Trash', '.Trashes'
        }
    
    def get_drives(self) -> List[DriveInfo]:
        """Detect all available drives on the system."""
        drives = []
        
        if platform.system() == 'Windows':
            # On Windows, check all drive letters
            for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                drive_path = f"{letter}:\\"
                if os.path.exists(drive_path):
                    try:
                        stat = os.statvfs(drive_path) if hasattr(os, 'statvfs') else None
                        if stat:
                            total = stat.f_blocks * stat.f_frsize
                            free = stat.f_bavail * stat.f_frsize
                        else:
                            # Windows doesn't have statvfs, use ctypes
                            import ctypes
                            free_bytes = ctypes.c_ulonglong(0)
                            total_bytes = ctypes.c_ulonglong(0)
                            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                                ctypes.c_wchar_p(drive_path),
                                None,
                                ctypes.pointer(total_bytes),
                                ctypes.pointer(free_bytes)
                            )
                            total = total_bytes.value
                            free = free_bytes.value
                        
                        drive_type = self._get_drive_type_windows(drive_path)
                        drives.append(DriveInfo(
                            path=drive_path,
                            name=f"Drive {letter}:",
                            total_size=total,
                            free_space=free,
                            drive_type=drive_type
                        ))
                    except (OSError, PermissionError):
                        continue
        else:
            # On Unix/Linux/macOS, check mount points
            for mount in ['/', '/home', '/mnt', '/media']:
                if os.path.exists(mount):
                    try:
                        stat = os.statvfs(mount)
                        drives.append(DriveInfo(
                            path=mount,
                            name=mount,
                            total_size=stat.f_blocks * stat.f_frsize,
                            free_space=stat.f_bavail * stat.f_frsize,
                            drive_type='fixed'
                        ))
                    except (OSError, PermissionError):
                        continue
            
            # Check for mounted volumes in /mnt and /media
            for base in ['/mnt', '/media']:
                if os.path.exists(base):
                    for name in os.listdir(base):
                        mount_path = os.path.join(base, name)
                        if os.path.ismount(mount_path):
                            try:
                                stat = os.statvfs(mount_path)
                                drives.append(DriveInfo(
                                    path=mount_path,
                                    name=name,
                                    total_size=stat.f_blocks * stat.f_frsize,
                                    free_space=stat.f_bavail * stat.f_frsize,
                                    drive_type='removable'
                                ))
                            except (OSError, PermissionError):
                                continue
        
        return drives
    
    def _get_drive_type_windows(self, drive_path: str) -> str:
        """Get drive type on Windows."""
        try:
            import ctypes
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_path)
            type_map = {
                1: 'unknown',
                2: 'removable',
                3: 'fixed',
                4: 'network',
                5: 'cdrom',
                6: 'ramdisk'
            }
            return type_map.get(drive_type, 'unknown')
        except Exception:
            return 'unknown'
    
    def set_progress_callback(self, callback: Optional[Callable]):
        """Set callback for progress updates."""
        self._progress_callback = callback
    
    def set_status_callback(self, callback: Optional[Callable]):
        """Set callback for status messages."""
        self._status_callback = callback
    
    def _report_status(self, message: str):
        """Report status to callback."""
        if self._status_callback:
            self._status_callback(message)
    
    def _report_progress(self, count: int, current_path: str):
        """Report progress to callback."""
        if self._progress_callback:
            self._progress_callback(count, current_path)
    
    def _should_skip_path(self, path: Path, root: Path) -> bool:
        """Check if path should be skipped during indexing."""
        parts = path.parts
        # Skip hidden directories and excluded directories
        for part in parts:
            if part.startswith('.') or part in self._exclude_dirs:
                return True
        return False
    
    def _has_indexed_data(self, drive_path: str) -> bool:
        """Check if there's already indexed data for this drive."""
        stats = self.indexer.get_stats()
        return stats['total_files'] > 0
    
    def _index_drive(self, drive_path: str, force_full: bool = False) -> int:
        """Index a single drive.
        
        Args:
            drive_path: Path to the drive to index
            force_full: If True, always do a full scan
        
        Returns:
            Number of items indexed
        """
        self._report_status(f"Checking {drive_path}...")
        
        def progress_callback(count: int, current_path: str):
            if not self._stop_flag.is_set():
                self._report_progress(count, current_path)
        
        try:
            # Check if we already have data for this drive
            if not force_full and self._has_indexed_data(drive_path):
                self._report_status(f"Found existing index for {drive_path}, running incremental update...")
                stats = self.indexer.incremental_update(
                    drive_path,
                    progress_callback=lambda s: self._report_status(
                        f"Updating {drive_path}: +{s['added']} ~{s['updated']} -{s['removed']}"
                    )
                )
                self._indexed_drives.add(drive_path)
                total = stats['added'] + stats['updated']
                self._report_status(f"Incremental update complete: +{stats['added']} ~{stats['updated']} -{stats['removed']}")
                return total
            else:
                # No existing data, do full scan
                self._report_status(f"Indexing {drive_path} (full scan)...")
                count = self.indexer.scan_directory(
                    drive_path,
                    exclude_dirs=self._exclude_dirs,
                    progress_callback=progress_callback
                )
                self._indexed_drives.add(drive_path)
                return count
        except (OSError, PermissionError) as e:
            self._report_status(f"Error indexing {drive_path}: {e}")
            return 0
    
    def _initial_index_task(self):
        """Task to index all drives on startup."""
        self._is_indexing = True
        self._report_status("Detecting drives...")
        
        drives = self.get_drives()
        self._report_status(f"Found {len(drives)} drives")
        
        total_indexed = 0
        for drive in drives:
            if self._stop_flag.is_set():
                break
            
            # Skip network and removable drives for initial scan (can be slow)
            if drive.drive_type in ('network', 'removable'):
                self._report_status(f"Skipping {drive.name} ({drive.drive_type})")
                continue
            
            count = self._index_drive(drive.path)
            total_indexed += count
        
        self._is_indexing = False
        self._report_status(f"Initial scan complete: {total_indexed} items indexed")
    
    def _incremental_update_task(self):
        """Task to run periodic incremental updates."""
        while not self._stop_flag.is_set():
            # Wait for the update interval
            for _ in range(self.update_interval):
                if self._stop_flag.is_set():
                    return
                time.sleep(1)
            
            if self._stop_flag.is_set():
                return
            
            # Run incremental update for each indexed drive
            self._report_status("Running incremental update...")
            total_stats = {'added': 0, 'removed': 0, 'updated': 0}
            
            for drive_path in list(self._indexed_drives):
                if self._stop_flag.is_set():
                    break
                
                if os.path.exists(drive_path):
                    stats = self.indexer.incremental_update(
                        drive_path,
                        progress_callback=lambda s: self._report_status(
                            f"Updating {drive_path}: +{s['added']} ~{s['updated']} -{s['removed']}"
                        )
                    )
                    total_stats['added'] += stats['added']
                    total_stats['removed'] += stats['removed']
                    total_stats['updated'] += stats['updated']
            
            self._report_status(
                f"Update complete: +{total_stats['added']} ~{total_stats['updated']} -{total_stats['removed']}"
            )
    
    def start(self):
        """Start background indexing."""
        if self._index_thread and self._index_thread.is_alive():
            return
        
        self._stop_flag.clear()
        
        # Start initial indexing thread
        self._index_thread = threading.Thread(
            target=self._initial_index_task,
            daemon=True,
            name="InitialIndexer"
        )
        self._index_thread.start()
        
        # Start incremental update thread
        self._update_thread = threading.Thread(
            target=self._incremental_update_task,
            daemon=True,
            name="IncrementalUpdater"
        )
        self._update_thread.start()
    
    def stop(self):
        """Stop background indexing."""
        self._stop_flag.set()
        self.indexer.stop()
        
        if self._index_thread:
            self._index_thread.join(timeout=5)
        if self._update_thread:
            self._update_thread.join(timeout=5)
    
    def is_indexing(self) -> bool:
        """Check if initial indexing is in progress."""
        return self._is_indexing
    
    def get_indexed_drives(self) -> Set[str]:
        """Get set of indexed drive paths."""
        return self._indexed_drives.copy()
    
    def force_full_scan(self):
        """Force a full re-index of all drives."""
        self._report_status("Starting full re-index...")
        
        drives = self.get_drives()
        total_indexed = 0
        
        for drive in drives:
            if self._stop_flag.is_set():
                break
            
            if drive.drive_type in ('network', 'removable'):
                continue
            
            count = self._index_drive(drive.path, force_full=True)
            total_indexed += count
        
        self._report_status(f"Full re-index complete: {total_indexed} items")
