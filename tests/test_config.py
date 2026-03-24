# Tests for configuration
import os
from pathlib import Path

from searchio.config import (
    APP_NAME,
    APP_VERSION,
    CONFIG_DIR,
    INDEX_DB_PATH,
    MAX_FILE_SIZE,
    IGNORED_EXTENSIONS,
    IGNORED_DIRECTORIES,
    SEARCH_RESULTS_LIMIT,
)


def test_app_settings():
    """Test application settings."""
    assert APP_NAME == "Searchio"
    assert APP_VERSION == "1.0.0"


def test_paths():
    """Test path configuration."""
    assert CONFIG_DIR.name == ".searchio"
    assert INDEX_DB_PATH.name == "index.db"


def test_ignored_extensions():
    """Test ignored extensions set."""
    assert ".pyc" in IGNORED_EXTENSIONS
    assert ".exe" in IGNORED_EXTENSIONS
    assert ".txt" not in IGNORED_EXTENSIONS


def test_ignored_directories():
    """Test ignored directories set."""
    assert ".git" in IGNORED_DIRECTORIES
    assert "node_modules" in IGNORED_DIRECTORIES
    assert "src" not in IGNORED_DIRECTORIES


def test_config_directory_created():
    """Test that config directory is created."""
    assert CONFIG_DIR.exists()
