# Tests for the database module
import os
import tempfile
from pathlib import Path

import pytest

from searchio.core.database import Database


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


class TestDatabase:
    """Tests for Database class."""
    
    def test_init_database(self, temp_db_path):
        """Test database initialization."""
        db = Database(db_path=temp_db_path)
        assert temp_db_path.exists()
    
    def test_add_file(self, temp_db_path):
        """Test adding a file record."""
        db = Database(db_path=temp_db_path)
        
        file_id = db.add_file({
            'path': '/test/file.txt',
            'name': 'file.txt',
            'extension': '.txt',
            'size': 100,
            'modified_time': 1234567890.0,
            'is_directory': False,
            'content_hash': 'abc123'
        })
        
        assert file_id is not None
    
    def test_get_file_by_path(self, temp_db_path):
        """Test retrieving a file by path."""
        db = Database(db_path=temp_db_path)
        
        db.add_file({
            'path': '/test/file.txt',
            'name': 'file.txt',
            'extension': '.txt',
            'size': 100,
            'modified_time': 1234567890.0,
            'is_directory': False
        })
        
        file_record = db.get_file_by_path('/test/file.txt')
        assert file_record is not None
        assert file_record['name'] == 'file.txt'
        assert file_record['extension'] == '.txt'
    
    def test_delete_file(self, temp_db_path):
        """Test deleting a file record."""
        db = Database(db_path=temp_db_path)
        
        db.add_file({
            'path': '/test/file.txt',
            'name': 'file.txt',
            'extension': '.txt',
            'size': 100,
            'modified_time': 1234567890.0,
            'is_directory': False
        })
        
        db.delete_file('/test/file.txt')
        
        file_record = db.get_file_by_path('/test/file.txt')
        assert file_record is None
    
    def test_search_by_name(self, temp_db_path):
        """Test searching files by name."""
        db = Database(db_path=temp_db_path)
        
        db.add_file({
            'path': '/test/file1.txt',
            'name': 'file1.txt',
            'extension': '.txt',
            'size': 100,
            'modified_time': 1234567890.0,
            'is_directory': False
        })
        db.add_file({
            'path': '/test/file2.txt',
            'name': 'file2.txt',
            'extension': '.txt',
            'size': 200,
            'modified_time': 1234567890.0,
            'is_directory': False
        })
        db.add_file({
            'path': '/test/other.py',
            'name': 'other.py',
            'extension': '.py',
            'size': 300,
            'modified_time': 1234567890.0,
            'is_directory': False
        })
        
        results = db.search_by_name('file')
        assert len(results) == 2
        
        results = db.search_by_name('other')
        assert len(results) == 1
    
    def test_add_trigrams(self, temp_db_path):
        """Test adding trigrams for a file."""
        db = Database(db_path=temp_db_path)
        
        file_id = db.add_file({
            'path': '/test/file.txt',
            'name': 'file.txt',
            'extension': '.txt',
            'size': 100,
            'modified_time': 1234567890.0,
            'is_directory': False
        })
        
        db.add_trigrams(file_id, ['fil', 'ile', 'txt'])
        
        results = db.search_by_trigrams(['fil', 'ile'])
        assert len(results) == 1
    
    def test_get_stats(self, temp_db_path):
        """Test getting database statistics."""
        db = Database(db_path=temp_db_path)
        
        db.add_file({
            'path': '/test/file.txt',
            'name': 'file.txt',
            'extension': '.txt',
            'size': 100,
            'modified_time': 1234567890.0,
            'is_directory': False
        })
        
        stats = db.get_stats()
        assert stats['total_files'] == 1
    
    def test_indexed_directories(self, temp_db_path):
        """Test tracking indexed directories."""
        db = Database(db_path=temp_db_path)
        
        db.add_indexed_directory('/test/path', file_count=10)
        
        dirs = db.get_indexed_directories()
        assert len(dirs) == 1
        assert dirs[0]['path'] == '/test/path'
        assert dirs[0]['file_count'] == 10
