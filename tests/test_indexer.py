# Tests for the file indexer
import os
import tempfile
import pytest
from pathlib import Path

from searchio.core.indexer import FileIndexer


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        Path(tmpdir, "test1.txt").write_text("hello world")
        Path(tmpdir, "test2.py").write_text("print('hello')")
        Path(tmpdir, "subdir").mkdir()
        Path(tmpdir, "subdir", "test3.md").write_text("# markdown")
        yield tmpdir


@pytest.fixture
def indexer(temp_dir):
    """Create an indexer with a temp database."""
    db_path = os.path.join(temp_dir, "test_index.db")
    idx = FileIndexer(db_path)
    yield idx
    idx.close()


def test_scan_directory(indexer, temp_dir):
    """Test scanning a directory."""
    count = indexer.scan_directory(temp_dir)
    assert count == 3  # test1.txt, test2.py, subdir/test3.md


def test_search_by_name(indexer, temp_dir):
    """Test searching for files by name."""
    indexer.scan_directory(temp_dir)
    results = indexer.search("test")
    assert len(results) == 3
    names = [r.name for r in results]
    assert "test1.txt" in names
    assert "test2.py" in names
    assert "test3.md" in names


def test_search_with_extension_filter(indexer, temp_dir):
    """Test searching with extension filter."""
    indexer.scan_directory(temp_dir)
    results = indexer.search("test", extension_filter=".py")
    assert len(results) == 1
    assert results[0].name == "test2.py"


def test_incremental_update(indexer, temp_dir):
    """Test incremental updates."""
    indexer.scan_directory(temp_dir)
    
    # Add a new file
    Path(temp_dir, "new_file.txt").write_text("new content")
    
    stats = indexer.incremental_update(temp_dir)
    assert stats['added'] == 1
    assert stats['updated'] == 0
    assert stats['removed'] == 0


def test_get_stats(indexer, temp_dir):
    """Test getting index statistics."""
    indexer.scan_directory(temp_dir)
    stats = indexer.get_stats()
    assert stats['total_files'] == 3
    assert stats['total_size'] > 0


def test_stop_indexing(indexer, temp_dir):
    """Test stopping an indexing operation."""
    indexer.stop()
    # The stop flag should prevent further indexing
    assert indexer._stop_flag.is_set()
    indexer.reset_stop()
    assert not indexer._stop_flag.is_set()
