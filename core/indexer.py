"""High-performance file indexer with incremental updates."""

import os
import re
import fnmatch
import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import threading


@dataclass
class FileInfo:
    """Represents indexed file/folder metadata."""
    path: str
    name: str
    extension: str
    size: int
    modified_time: float
    indexed_time: float
    parent_dir: str
    depth: int
    is_directory: bool = False
    content_hash: Optional[str] = None


class FileIndexer:
    """High-performance file indexer with incremental update support."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.expanduser("~/.searchio/index.db")
        self._ensure_db_dir()
        self.conn = self._init_database()
        self._lock = threading.Lock()
        self._stop_flag = threading.Event()
        
    def _ensure_db_dir(self):
        """Ensure database directory exists."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    
    def _init_database(self) -> sqlite3.Connection:
        """Initialize SQLite database with optimized schema."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                extension TEXT,
                size INTEGER,
                modified_time REAL,
                indexed_time REAL,
                parent_dir TEXT,
                depth INTEGER,
                is_directory INTEGER DEFAULT 0,
                content_hash TEXT
            )
        """)
        
        # Migration: Add is_directory column if it doesn't exist (for legacy databases)
        cursor = conn.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'is_directory' not in columns:
            conn.execute("ALTER TABLE files ADD COLUMN is_directory INTEGER DEFAULT 0")
            conn.commit()  # Commit migration before creating indexes
        
        # FTS table for fast name search
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts 
            USING fts5(name, content='files', content_rowid='rowid')
        """)
        
        # Indexes for common queries (create safely, handle missing column gracefully)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_extension ON files(extension)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_parent ON files(parent_dir)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_modified ON files(modified_time)")
        
        # Only create is_directory index if column exists
        cursor = conn.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'is_directory' in columns:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_is_directory ON files(is_directory)")
        
        conn.commit()
        return conn
    
    def compute_hash(self, file_path: str) -> str:
        """Compute quick hash of file for change detection."""
        try:
            stat = os.stat(file_path)
            return hashlib.md5(f"{file_path}:{stat.st_size}:{stat.st_mtime}".encode()).hexdigest()
        except OSError:
            return ""
    
    def scan_directory(self, root_path: str, max_depth: int = None, 
                       exclude_dirs: Set[str] = None,
                       progress_callback=None) -> int:
        """Scan directory and index all files and folders.
        
        Returns number of items indexed.
        """
        exclude_dirs = exclude_dirs or {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}
        root = Path(root_path).resolve()
        items_indexed = 0
        
        def should_skip(path: Path) -> bool:
            # Skip hidden files/dirs, common exclude dirs, and database files
            if any(part.startswith('.') or part in exclude_dirs for part in path.parts):
                return True
            # Skip database files to avoid indexing our own index (including WAL artifacts)
            suffix = path.suffix.lower()
            if suffix == '.db' or path.name.endswith('.db-wal') or path.name.endswith('.db-shm'):
                return True
            # Skip the indexer's own database file by exact path match
            if str(path) == self.db_path:
                return True
            return False
        
        for file_path in root.rglob('*'):
            if self._stop_flag.is_set():
                break
                
            if should_skip(file_path):
                continue
            
            # Skip directories - only index files
            if file_path.is_dir():
                continue
            
            try:
                rel_path = file_path.relative_to(root)
                stat = file_path.stat()
                is_dir = False
                
                file_info = FileInfo(
                    path=str(file_path),
                    name=file_path.name,
                    extension='' if is_dir else file_path.suffix.lower(),
                    size=0 if is_dir else stat.st_size,
                    modified_time=stat.st_mtime,
                    indexed_time=datetime.now().timestamp(),
                    parent_dir=str(file_path.parent),
                    depth=len(rel_path.parts) - 1,
                    is_directory=is_dir
                )
                
                self._index_file(file_info)
                items_indexed += 1
                
                if progress_callback and items_indexed % 100 == 0:
                    progress_callback(items_indexed, str(file_path))
                    
            except (OSError, PermissionError):
                continue
        
        self.conn.commit()
        return items_indexed
    
    def _index_file(self, info: FileInfo):
        """Insert or update a file/folder in the index."""
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO files 
                (path, name, extension, size, modified_time, indexed_time, parent_dir, depth, is_directory)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (info.path, info.name, info.extension, info.size, 
                  info.modified_time, info.indexed_time, info.parent_dir, info.depth,
                  1 if info.is_directory else 0))
    
    def incremental_update(self, root_path: str, progress_callback=None) -> Dict[str, int]:
        """Update index incrementally - only process changed files.
        
        Returns dict with 'added', 'removed', 'updated' counts.
        """
        stats = {'added': 0, 'removed': 0, 'updated': 0}
        root = Path(root_path).resolve()
        exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}
        
        # Get all currently indexed paths under root
        with self._lock:
            cursor = self.conn.execute(
                "SELECT path, modified_time FROM files WHERE path LIKE ?",
                (str(root) + '%',)
            )
            indexed = {row[0]: row[1] for row in cursor.fetchall()}
        
        def should_skip(path: Path) -> bool:
            # Skip hidden files/dirs, common exclude dirs, and database files
            if any(part.startswith('.') or part in exclude_dirs for part in path.parts):
                return True
            # Skip database files to avoid indexing our own index (including WAL artifacts)
            suffix = path.suffix.lower()
            if suffix == '.db' or path.name.endswith('.db-wal') or path.name.endswith('.db-shm'):
                return True
            # Skip the indexer's own database file by exact path match
            if str(path) == self.db_path:
                return True
            return False
        
        # Scan for new/modified files
        current_items = set()
        for file_path in root.rglob('*'):
            if self._stop_flag.is_set():
                break
            
            if should_skip(file_path):
                continue
            
            path_str = str(file_path)
            current_items.add(path_str)
            
            try:
                # Skip directories - only index files (consistent with scan_directory)
                if file_path.is_dir():
                    continue
                    
                stat = file_path.stat()
                mtime = stat.st_mtime
                is_dir = False
                
                if path_str not in indexed:
                    # New item
                    self._index_file(FileInfo(
                        path=path_str,
                        name=file_path.name,
                        extension='' if is_dir else file_path.suffix.lower(),
                        size=0 if is_dir else stat.st_size,
                        modified_time=mtime,
                        indexed_time=datetime.now().timestamp(),
                        parent_dir=str(file_path.parent),
                        depth=len(file_path.relative_to(root).parts) - 1,
                        is_directory=is_dir
                    ))
                    stats['added'] += 1
                elif indexed[path_str] < mtime:
                    # Modified item
                    self._index_file(FileInfo(
                        path=path_str,
                        name=file_path.name,
                        extension='' if is_dir else file_path.suffix.lower(),
                        size=0 if is_dir else stat.st_size,
                        modified_time=mtime,
                        indexed_time=datetime.now().timestamp(),
                        parent_dir=str(file_path.parent),
                        depth=len(file_path.relative_to(root).parts) - 1,
                        is_directory=is_dir
                    ))
                    stats['updated'] += 1
                    
                if progress_callback and (stats['added'] + stats['updated']) % 50 == 0:
                    progress_callback(stats)
                    
            except (OSError, PermissionError):
                continue
        
        # Remove items that no longer exist
        removed_paths = set(indexed.keys()) - current_items
        with self._lock:
            self.conn.executemany(
                "DELETE FROM files WHERE path = ?",
                [(p,) for p in removed_paths]
            )
            stats['removed'] = len(removed_paths)
        
        self.conn.commit()
        return stats
    
    def _is_glob_pattern(self, query: str) -> bool:
        """Check if query is a glob pattern like *.go"""
        return '*' in query or '?' in query or '[' in query
    
    def _convert_glob_to_regex(self, pattern: str) -> str:
        """Convert glob pattern to regex."""
        # Escape special regex chars except glob wildcards
        result = ''
        i = 0
        while i < len(pattern):
            c = pattern[i]
            if c == '*':
                result += '.*'
            elif c == '?':
                result += '.'
            elif c in '.^$+{}()|[]':
                result += '\\' + c
            else:
                result += c
            i += 1
        return result
    
    def search(self, query: str, limit: int = 100, 
               extension_filter: str = None) -> List[FileInfo]:
        """Search for files by name with glob/regex support."""
        with self._lock:
            results = []
            
            # Check if it's a glob pattern (e.g., *.go)
            if self._is_glob_pattern(query):
                # Convert glob to LIKE pattern for simple cases
                # *.go -> %.go
                like_pattern = query.replace('*', '%').replace('?', '_')
                if extension_filter:
                    cursor = self.conn.execute("""
                        SELECT path, name, extension, size, modified_time, indexed_time, parent_dir, depth, is_directory
                        FROM files 
                        WHERE name LIKE ? ESCAPE '\\' AND extension = ?
                        ORDER BY is_directory DESC, modified_time DESC
                        LIMIT ?
                    """, (like_pattern, extension_filter.lower(), limit))
                else:
                    cursor = self.conn.execute("""
                        SELECT path, name, extension, size, modified_time, indexed_time, parent_dir, depth, is_directory
                        FROM files 
                        WHERE name LIKE ? ESCAPE '\\'
                        ORDER BY is_directory DESC, modified_time DESC
                        LIMIT ?
                    """, (like_pattern, limit))
            else:
                # Regular substring search
                if extension_filter:
                    cursor = self.conn.execute("""
                        SELECT path, name, extension, size, modified_time, indexed_time, parent_dir, depth, is_directory
                        FROM files 
                        WHERE name LIKE ? AND extension = ?
                        ORDER BY is_directory DESC, modified_time DESC
                        LIMIT ?
                    """, (f'%{query}%', extension_filter.lower(), limit))
                else:
                    cursor = self.conn.execute("""
                        SELECT path, name, extension, size, modified_time, indexed_time, parent_dir, depth, is_directory
                        FROM files 
                        WHERE name LIKE ?
                        ORDER BY is_directory DESC, modified_time DESC
                        LIMIT ?
                    """, (f'%{query}%', limit))
            
            for row in cursor.fetchall():
                results.append(FileInfo(
                    path=row[0], name=row[1], extension=row[2],
                    size=row[3], modified_time=row[4], indexed_time=row[5],
                    parent_dir=row[6], depth=row[7], is_directory=bool(row[8])
                ))
            return results
    
    def search_regex(self, pattern: str, limit: int = 100) -> List[FileInfo]:
        """Search using regex pattern."""
        with self._lock:
            cursor = self.conn.execute("""
                SELECT path, name, extension, size, modified_time, indexed_time, parent_dir, depth, is_directory
                FROM files 
                ORDER BY is_directory DESC, modified_time DESC
            """)
            
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error:
                return []
            
            results = []
            for row in cursor.fetchall():
                name = row[1]
                if regex.search(name):
                    results.append(FileInfo(
                        path=row[0], name=row[1], extension=row[2],
                        size=row[3], modified_time=row[4], indexed_time=row[5],
                        parent_dir=row[6], depth=row[7], is_directory=bool(row[8])
                    ))
                    if len(results) >= limit:
                        break
            return results
    
    def search_by_content(self, query: str, limit: int = 100) -> List[FileInfo]:
        """Full-text search on file names using FTS."""
        with self._lock:
            cursor = self.conn.execute("""
                SELECT f.path, f.name, f.extension, f.size, f.modified_time, f.indexed_time, f.parent_dir, f.depth, f.is_directory
                FROM files f
                JOIN files_fts fts ON f.rowid = fts.rowid
                WHERE files_fts MATCH ?
                ORDER BY f.is_directory DESC, f.modified_time DESC
                LIMIT ?
            """, (query, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append(FileInfo(
                    path=row[0], name=row[1], extension=row[2],
                    size=row[3], modified_time=row[4], indexed_time=row[5],
                    parent_dir=row[6], depth=row[7], is_directory=bool(row[8])
                ))
            return results
    
    def get_stats(self) -> Dict:
        """Get index statistics."""
        with self._lock:
            cursor = self.conn.execute("SELECT COUNT(*) FROM files")
            total_files = cursor.fetchone()[0]
            
            cursor = self.conn.execute("SELECT COUNT(*) FROM files WHERE is_directory = 1")
            total_dirs = cursor.fetchone()[0]
            
            cursor = self.conn.execute("SELECT SUM(size) FROM files WHERE is_directory = 0")
            total_size = cursor.fetchone()[0] or 0
            
            cursor = self.conn.execute("""
                SELECT extension, COUNT(*) as cnt 
                FROM files 
                WHERE is_directory = 0
                GROUP BY extension 
                ORDER BY cnt DESC 
                LIMIT 10
            """)
            top_extensions = cursor.fetchall()
            
            return {
                'total_files': total_files,
                'total_directories': total_dirs,
                'total_size': total_size,
                'top_extensions': top_extensions
            }
    
    def stop(self):
        """Signal the indexer to stop current operation."""
        self._stop_flag.set()
    
    def reset_stop(self):
        """Reset stop flag for new operation."""
        self._stop_flag.clear()
    
    def close(self):
        """Close database connection."""
        self.conn.close()
