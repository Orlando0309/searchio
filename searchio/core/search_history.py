"""Search history management for Searchio."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict

from ..config import CONFIG_DIR

logger = logging.getLogger(__name__)


@dataclass
class SearchEntry:
    """Represents a single search history entry."""
    query: str
    timestamp: float
    result_count: int
    search_type: str  # 'name', 'content', 'regex', 'glob'
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SearchEntry':
        return cls(**data)


class SearchHistory:
    """Manages search history with persistence."""
    
    MAX_HISTORY = 50  # Maximum number of entries to keep
    
    def __init__(self, history_file: Optional[Path] = None):
        self.history_file = history_file or CONFIG_DIR / "search_history.json"
        self._entries: List[SearchEntry] = []
        self._load()
    
    def _load(self):
        """Load history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._entries = [SearchEntry.from_dict(e) for e in data]
                logger.info(f"Loaded {len(self._entries)} search history entries")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load search history: {e}")
                self._entries = []
        else:
            self._entries = []
    
    def _save(self):
        """Save history to file."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump([e.to_dict() for e in self._entries], f, indent=2)
            logger.debug(f"Saved {len(self._entries)} search history entries")
        except IOError as e:
            logger.error(f"Failed to save search history: {e}")
    
    def add_entry(self, query: str, result_count: int, search_type: str = 'name'):
        """Add a search entry to history."""
        if not query.strip():
            return
        
        # Remove existing entry with same query to avoid duplicates
        self._entries = [e for e in self._entries if e.query != query]
        
        # Add new entry at the front
        entry = SearchEntry(
            query=query,
            timestamp=datetime.now().timestamp(),
            result_count=result_count,
            search_type=search_type
        )
        self._entries.insert(0, entry)
        
        # Trim to max size
        if len(self._entries) > self.MAX_HISTORY:
            self._entries = self._entries[:self.MAX_HISTORY]
        
        self._save()
        logger.debug(f"Added search history entry: {query}")
    
    def get_recent(self, limit: int = 10) -> List[SearchEntry]:
        """Get most recent search entries."""
        return self._entries[:limit]
    
    def get_all(self) -> List[SearchEntry]:
        """Get all search entries."""
        return self._entries.copy()
    
    def clear(self):
        """Clear all search history."""
        self._entries = []
        self._save()
        logger.info("Cleared search history")
    
    def remove_entry(self, query: str):
        """Remove a specific entry from history."""
        self._entries = [e for e in self._entries if e.query != query]
        self._save()
