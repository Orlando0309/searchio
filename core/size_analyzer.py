# Size analyzer for disk usage visualization
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from threading import Thread
import platform

from config import IGNORED_DIRECTORIES, IGNORED_EXTENSIONS


@dataclass
class SizeNode:
    """Represents a file or directory with its size."""
    name: str
    path: str
    size: int  # in bytes
    is_directory: bool
    children: List['SizeNode'] = field(default_factory=list)
    parent: Optional['SizeNode'] = None
    file_count: int = 0  # for directories
    dir_count: int = 0  # for directories
    
    def add_child(self, child: 'SizeNode'):
        child.parent = self
        self.children.append(child)
        
    def get_size_percentage(self) -> float:
        """Get percentage of parent's size."""
        if self.parent and self.parent.size > 0:
            return (self.size / self.parent.size) * 100
        return 100.0


class SizeAnalyzer:
    """Analyzes disk usage for directories."""
    
    def __init__(self):
        self._stop_flag = False
        self._progress_callback: Optional[Callable[[int, str], None]] = None
        self._complete_callback: Optional[Callable[[SizeNode], None]] = None
        
    def set_progress_callback(self, callback: Callable[[int, str], None]):
        """Set callback for progress updates: callback(file_count, current_path)"""
        self._progress_callback = callback
        
    def set_complete_callback(self, callback: Callable[[SizeNode], None]):
        """Set callback for completion: callback(root_node)"""
        self._complete_callback = callback
    
    def stop(self):
        """Stop the analysis."""
        self._stop_flag = True
        
    def analyze_async(self, path: str):
        """Start async analysis of a directory."""
        self._stop_flag = False
        thread = Thread(target=self._analyze, args=(path,), daemon=True)
        thread.start()
        
    def _should_skip(self, path: Path) -> bool:
        """Check if path should be skipped."""
        name = path.name.lower()
        
        # Skip hidden files/directories (except .git for repo awareness)
        if name.startswith('.') and name not in {'.git', '.github'}:
            return True
            
        # Skip ignored directories
        if name in IGNORED_DIRECTORIES:
            return True
            
        # Skip ignored extensions for files
        if path.is_file() and path.suffix.lower() in IGNORED_EXTENSIONS:
            return True
            
        return False
    
    def _analyze(self, path: str) -> SizeNode:
        """Analyze directory recursively."""
        root_path = Path(path)
        
        if not root_path.exists():
            root_node = SizeNode(name=path, path=path, size=0, is_directory=True)
            if self._complete_callback:
                self._complete_callback(root_node)
            return root_node
            
        visited: set = set()
        root_node = self._scan_directory(root_path, 0, visited)
        
        if self._complete_callback:
            self._complete_callback(root_node)
        
        return root_node
    
    def _scan_directory(self, dir_path: Path, file_count: int = 0, visited: Optional[set] = None) -> SizeNode:
        """Recursively scan a directory and build size tree."""
        if self._stop_flag:
            return SizeNode(name=dir_path.name, path=str(dir_path), size=0, is_directory=True)
        
        # Initialize visited set only at the entry point (when None)
        # This ensures the same set is shared through all recursive calls
        _visited = visited if visited is not None else set()
        
        try:
            dir_path = dir_path.resolve()
        except (OSError, RuntimeError):
            return SizeNode(name=dir_path.name, path=str(dir_path), size=0, is_directory=True)
        
        # Prevent infinite recursion from junctions/symlinks
        try:
            real_path = str(dir_path.resolve())
            if real_path in _visited:
                return SizeNode(name=dir_path.name, path=str(dir_path), size=0, is_directory=True)
            _visited.add(real_path)
        except (OSError, RuntimeError):
            pass
        
        root_node = SizeNode(
            name=dir_path.name,
            path=str(dir_path),
            size=0,
            is_directory=True
        )
        
        try:
            entries = list(dir_path.iterdir())
        except (PermissionError, OSError):
            return root_node
        
        total_size = 0
        total_files = 0
        total_dirs = 0
        
        for entry in entries:
            if self._stop_flag:
                break
                
            if self._should_skip(entry):
                continue
            
            try:
                if entry.is_file():
                    try:
                        size = entry.stat(follow_symlinks=False).st_size
                        file_node = SizeNode(
                            name=entry.name,
                            path=str(entry),
                            size=size,
                            is_directory=False
                        )
                        root_node.add_child(file_node)
                        total_size += size
                        total_files += 1
                    except (OSError, PermissionError):
                        pass
                        
                elif entry.is_dir():
                    child_node = self._scan_directory(entry, file_count, visited)
                    root_node.add_child(child_node)
                    total_size += child_node.size
                    total_files += child_node.file_count
                    total_dirs += child_node.dir_count + 1
            except (OSError, PermissionError):
                continue
            
            # Report progress periodically
            if self._progress_callback and total_files % 100 == 0:
                self._progress_callback(file_count + total_files, str(entry))
        
        root_node.size = total_size
        root_node.file_count = total_files
        root_node.dir_count = total_dirs
        
        # Sort children by size (largest first)
        root_node.children.sort(key=lambda x: x.size, reverse=True)
        
        return root_node
    
    def analyze_sync(self, path: str) -> SizeNode:
        """Synchronous analysis for testing."""
        self._stop_flag = False
        return self._analyze(path)


def get_drives_for_analysis():
    """Get list of drives available for analysis."""
    drives = []
    system = platform.system()
    
    if system == "Windows":
        import ctypes
        from string import ascii_uppercase
        
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        
        for letter in ascii_uppercase:
            if bitmask & (1 << (ord(letter) - ord('A'))):
                drive_path = f"{letter}:\\"
                try:
                    import shutil
                    usage = shutil.disk_usage(drive_path)
                    drives.append({
                        'path': drive_path,
                        'name': f"{letter}:",
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free
                    })
                except (OSError, PermissionError):
                    pass
    else:
        # Linux/macOS - analyze home directory by default
        home = str(Path.home())
        try:
            import shutil
            usage = shutil.disk_usage(home)
            drives.append({
                'path': home,
                'name': 'Home',
                'total': usage.total,
                'used': usage.used,
                'free': usage.free
            })
        except (OSError, PermissionError):
            pass
            
        # Also check root
        try:
            usage = shutil.disk_usage('/')
            drives.append({
                'path': '/',
                'name': 'Root',
                'total': usage.total,
                'used': usage.used,
                'free': usage.free
            })
        except (OSError, PermissionError):
            pass
    
    return drives


def format_size(size: int) -> str:
    """Format size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
