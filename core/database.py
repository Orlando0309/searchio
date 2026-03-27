# Database operations for file index
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import contextmanager

from ..config import INDEX_DB_PATH


class Database:
    """SQLite database for storing file index."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or INDEX_DB_PATH
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Files table - stores file metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    extension TEXT,
                    size INTEGER,
                    modified_time REAL,
                    indexed_time REAL,
                    is_directory INTEGER DEFAULT 0,
                    content_hash TEXT
                )
            """)
            
            # Trigrams index for fuzzy filename search
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trigrams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigram TEXT NOT NULL,
                    file_id INTEGER NOT NULL,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """)
            
            # Content index for text search
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    file_id INTEGER NOT NULL,
                    positions TEXT,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """)
            
            # Directories table for tracking indexed paths
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS indexed_directories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    last_scan_time REAL,
                    file_count INTEGER DEFAULT 0
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_name ON files(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trigrams_trigram ON trigrams(trigram)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_word ON content_index(word)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trigrams_file ON trigrams(file_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_file ON content_index(file_id)")
            
            conn.commit()
    
    def add_file(self, file_data: Dict[str, Any]) -> int:
        """Add or update a file record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO files (path, name, extension, size, modified_time, indexed_time, is_directory, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    name = excluded.name,
                    extension = excluded.extension,
                    size = excluded.size,
                    modified_time = excluded.modified_time,
                    indexed_time = excluded.indexed_time,
                    content_hash = excluded.content_hash
            """, (
                file_data['path'],
                file_data['name'],
                file_data.get('extension', ''),
                file_data.get('size', 0),
                file_data.get('modified_time', 0),
                datetime.now().timestamp(),
                1 if file_data.get('is_directory') else 0,
                file_data.get('content_hash', '')
            ))
            
            file_id = cursor.lastrowid
            conn.commit()
            return file_id
    
    def get_file_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """Get file record by path."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE path = ?", (path,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def delete_file(self, path: str):
        """Delete a file record and its associated index data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE path = ?", (path,))
            conn.commit()
    
    def add_trigrams(self, file_id: int, trigrams: List[str]):
        """Add trigrams for a file."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT INTO trigrams (trigram, file_id) VALUES (?, ?)",
                [(t, file_id) for t in set(trigrams)]
            )
            conn.commit()
    
    def add_content_words(self, file_id: int, words: Dict[str, List[int]]):
        """Add content words for a file."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT INTO content_index (word, file_id, positions) VALUES (?, ?, ?)",
                [(word, file_id, json.dumps(positions)) for word, positions in words.items()]
            )
            conn.commit()
    
    def search_by_name(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search files by name using LIKE."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM files 
                WHERE name LIKE ? 
                ORDER BY modified_time DESC
                LIMIT ?
            """, (f"%{query}%", limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def search_by_trigrams(self, trigrams: List[str], limit: int = 100) -> List[Dict[str, Any]]:
        """Search files by matching trigrams."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(trigrams))
            cursor.execute(f"""
                SELECT f.*, COUNT(t.id) as match_count
                FROM files f
                JOIN trigrams t ON f.id = t.file_id
                WHERE t.trigram IN ({placeholders})
                GROUP BY f.id
                ORDER BY match_count DESC
                LIMIT ?
            """, trigrams + [limit])
            return [dict(row) for row in cursor.fetchall()]
    
    def search_content(self, words: List[str], limit: int = 100) -> List[Dict[str, Any]]:
        """Search file contents by words."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(words))
            cursor.execute(f"""
                SELECT f.*, COUNT(c.id) as match_count
                FROM files f
                JOIN content_index c ON f.id = c.file_id
                WHERE c.word IN ({placeholders})
                GROUP BY f.id
                ORDER BY match_count DESC
                LIMIT ?
            """, words + [limit])
            return [dict(row) for row in cursor.fetchall()]
    
    def clear_file_index(self, file_id: int):
        """Clear all index data for a file."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trigrams WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM content_index WHERE file_id = ?", (file_id,))
            conn.commit()
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            stats = {}
            cursor.execute("SELECT COUNT(*) FROM files")
            stats['total_files'] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM trigrams")
            stats['total_trigrams'] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM content_index")
            stats['total_words'] = cursor.fetchone()[0]
            return stats
    
    def add_indexed_directory(self, path: str, file_count: int = 0):
        """Record an indexed directory."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO indexed_directories (path, last_scan_time, file_count)
                VALUES (?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    last_scan_time = excluded.last_scan_time,
                    file_count = excluded.file_count
            """, (path, datetime.now().timestamp(), file_count))
            conn.commit()
    
    def get_indexed_directories(self) -> List[Dict[str, Any]]:
        """Get all indexed directories."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM indexed_directories")
            return [dict(row) for row in cursor.fetchall()]
