# Configuration for Search.io
import os
import platform
from pathlib import Path

# Application settings
APP_NAME = "Searchio"
APP_VERSION = "1.0.0"

# Paths
CONFIG_DIR = Path.home() / ".searchio"
INDEX_DB_PATH = CONFIG_DIR / "index.db"
CACHE_DIR = CONFIG_DIR / "cache"

# Indexing settings
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size to index
IGNORED_EXTENSIONS = {
    ".pyc", ".pyo", ".dll", ".exe", ".so", ".dylib",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".mp3", ".mp4", ".avi", ".mkv", ".mov",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".git", ".svn", ".hg", "__pycache__", "node_modules"
}

# Directories to skip during indexing (system/cache directories)
IGNORED_DIRECTORIES = {
    # Version control
    ".git", ".svn", ".hg",
    # Cache directories
    "__pycache__", "node_modules", ".cache", "cache", "Cache",
    # IDE/Editor directories
    ".idea", ".vscode", ".tox", ".mypy_cache", ".pytest_cache",
    # Virtual environments
    "venv", ".venv", "env", ".env", "site-packages",
    # System directories (Windows)
    "Windows", "$Recycle.Bin", "$RECYCLE.BIN", "System Volume Information",
    # System directories (macOS)
    "Library", ".Trash", ".Spotlight", ".fseventsd",
    # System directories (Linux)
    "proc", "sys", "dev", "run", "tmp", "var/log", "var/cache",
    # Build/artifact directories
    "build", "dist", "target", "bin", "obj", "out",
    # Package directories
    "node_modules", "packages", "site-packages",
}



# Search settings
SEARCH_RESULTS_LIMIT = 100
FUZZY_MATCH_THRESHOLD = 0.6

# Performance settings
BATCH_SIZE = 100  # Files to process in one batch
INDEX_UPDATE_INTERVAL = 2.0  # Seconds between incremental updates

# Background indexing settings
BACKGROUND_INDEX_INTERVAL = 300  # 5 minutes in seconds
BACKGROUND_INDEX_ENABLED = True

# Full computer scan settings
# On Windows: scan all drive letters
# On Linux/Mac: scan from root
SCAN_ALL_DRIVES = True

# Paths to exclude from full computer scan
EXCLUDED_PATHS = {
    # Windows
    "C:/Windows",
    "C:/$Recycle.Bin",
    "C:/System Volume Information",
    # macOS
    "/System",
    "/Library",
    "/.Spotlight",
    "/.fseventsd",
    "/.Trash",
    # Linux
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/tmp",
    "/var/log",
    "/var/cache",
}

# Ensure config directory exists
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_all_drives():
    """Get all available drives/partitions on the system."""
    drives = []
    system = platform.system()
    
    if system == "Windows":
        # Check all drive letters A-Z
        import ctypes
        from string import ascii_uppercase
        
        # Get bitmask of available drives
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        
        for letter in ascii_uppercase:
            if bitmask & (1 << (ord(letter) - ord('A'))):
                drive_path = f"{letter}:\\"
                # Skip CD-ROM and network drives
                try:
                    import os
                    if os.path.exists(drive_path) and os.path.isdir(drive_path):
                        drives.append(drive_path)
                except (OSError, PermissionError):
                    pass
    else:
        # On Linux/macOS, start from root
        drives.append("/")
        
        # On macOS, also check /Volumes for mounted drives
        if system == "Darwin":
            volumes_path = Path("/Volumes")
            if volumes_path.exists():
                for volume in volumes_path.iterdir():
                    if volume.is_dir() and not volume.is_symlink():
                        drives.append(str(volume))
    
    return drives


def should_skip_path(path_str: str) -> bool:
    """Check if a path should be skipped during indexing."""
    path_lower = path_str.lower().replace("/", "\\")
    
    # Check excluded paths
    for excluded in EXCLUDED_PATHS:
        if path_lower.startswith(excluded.lower().replace("/", "\\")):
            return True
    
    # Check if any path component is in ignored directories
    path_obj = Path(path_str)
    for part in path_obj.parts:
        if part in IGNORED_DIRECTORIES:
            return True
        # Skip hidden directories (starting with .)
        if part.startswith('.') and part not in {'.git', '.github'}:
            return True
    
    return False
