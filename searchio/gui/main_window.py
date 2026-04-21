# Main window for Search.io desktop application
import tkinter as tk
from tkinter import ttk, messagebox
from threading import Thread
from datetime import datetime
from pathlib import Path
import subprocess
import platform
import re
import os
from typing import Optional

from ..core.indexer import FileIndexer
from ..core.background_indexer import BackgroundIndexer
from ..core.size_analyzer import SizeAnalyzer, SizeNode, get_drives_for_analysis, format_size
from ..core.search_history import SearchHistory
from .treemap_widget import TreemapPanel
from .memory_graph_widget import MemoryGraphPanel
from ..config import APP_NAME, APP_VERSION


class MainWindow:
    """Main application window for Search.io using Tkinter."""
    
    def __init__(self):
        self.indexer = FileIndexer()
        self.bg_indexer = BackgroundIndexer(self.indexer, update_interval=300)  # 5 min updates
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self._load_geometry()
        self.root.minsize(600, 400)
        
        self._search_after_id = None
        self._content_search_var = tk.BooleanVar(value=False)
        self.size_analyzer = SizeAnalyzer()
        self.search_history = SearchHistory()
        self.treemap_panel = None
        self.memory_graph_panel = None
        self._history_popup = None
        
        self._setup_styles()
        self._setup_ui()
        self._connect_signals()
        
        # Start background indexing automatically
        self.root.after(100, self._start_background_indexing)
    
    def _setup_styles(self):
        """Configure ttk styles for the application."""
        style = ttk.Style()
        style.configure("Match.Treeview", rowheight=25)
        style.configure("Directory.Treeview", foreground="#008080")
        style.configure("File.Treeview", foreground="#333333")
    
    def _setup_ui(self):
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Export Results...", command=self._export_results)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit, accelerator="Alt+F4")
        
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Clear Search", command=self._clear_search, accelerator="Esc")
        view_menu.add_separator()
        view_menu.add_command(label="Focus Search", command=self.search_input.focus_set, accelerator="Ctrl+K")
        view_menu.add_command(label="Copy Path", command=self._copy_selected_path, accelerator="Ctrl+C")
        view_menu.add_separator()
        self._dark_mode_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(label="Dark Mode", variable=self._dark_mode_var, command=self._toggle_dark_mode)
        view_menu.add_separator()
        view_menu.add_command(label="Settings...", command=self._show_settings)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Notebook for tabs (Search and Memory/Disk Usage)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self._restore_active_tab()
        
        # Search tab
        search_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(search_frame, text="Search")
        
        # Status frame (replaces directory selection)
        status_frame = ttk.LabelFrame(search_frame, text="Indexing Status", padding="5")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_var = tk.StringVar(value="Starting...")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, font=('Segoe UI', 10))
        self.status_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.progress = ttk.Progressbar(status_frame, mode='indeterminate', length=200)
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        
        self.stop_btn = ttk.Button(status_frame, text="⏹", width=3, command=self._stop_indexing)
        self.stop_btn.pack(side=tk.LEFT, padx=(10, 0))
        self._add_tooltip(self.stop_btn, "Stop background indexing")
        self.stop_btn.configure(state=tk.DISABLED)
        
        self.drives_var = tk.StringVar(value="Detecting drives...")
        self.drives_label = ttk.Label(status_frame, textvariable=self.drives_var, foreground="gray")
        self.drives_label.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Stats frame
        stats_frame = ttk.Frame(search_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.stats_var = tk.StringVar(value="0 files indexed")
        ttk.Label(stats_frame, textvariable=self.stats_var, foreground="gray").pack(side=tk.LEFT)
        
        self.results_count_var = tk.StringVar(value="")
        ttk.Label(stats_frame, textvariable=self.results_count_var, foreground="gray").pack(side=tk.RIGHT)
        
        # Search frame - live search on typing
        search_input_frame = ttk.Frame(search_frame)
        search_input_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(search_input_frame, text="Search:").pack(side=tk.LEFT)
        self.search_input = ttk.Entry(search_input_frame, width=50)
        self.search_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # History button
        self.history_btn = ttk.Button(search_input_frame, text="🕐", width=3, command=self._show_history)
        self.history_btn.pack(side=tk.LEFT, padx=(5, 0))
        self._add_tooltip(self.history_btn, "Search history (click or focus search)")
        
        # Explicit search button
        self.search_btn = ttk.Button(search_input_frame, text="🔍", width=3, command=self._do_search)
        self.search_btn.pack(side=tk.LEFT, padx=(5, 0))
        self._add_tooltip(self.search_btn, "Run search now")
        
        # Clear button
        self.clear_btn = ttk.Button(search_input_frame, text="✕", width=3, command=self._clear_search)
        self.clear_btn.pack(side=tk.LEFT, padx=(5, 0))
        self._add_tooltip(self.clear_btn, "Clear search and results (Esc)")
        
        # Content search toggle
        self.content_search_cb = ttk.Checkbutton(search_input_frame, text="Content", variable=self._content_search_var)
        self.content_search_cb.pack(side=tk.LEFT, padx=(10, 0))
        
        # File type filter
        self.file_type_var = tk.StringVar(value="All")
        self.file_type_combo = ttk.Combobox(search_input_frame, textvariable=self.file_type_var,
                                             values=["All", "Files", "Directories"], state="readonly", width=10)
        self.file_type_combo.pack(side=tk.LEFT, padx=(10, 0))
        self.file_type_combo.bind("<<ComboboxSelected>>", lambda e: self._do_search())
        
        # Hint label for search patterns
        hint_label = ttk.Label(search_input_frame, text="(use *.ext for glob, or /regex/ for regex)", foreground="gray")
        hint_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Results frame with optional preview pane
        self.results_paned = ttk.PanedWindow(search_frame, orient=tk.HORIZONTAL)
        self.results_paned.pack(fill=tk.BOTH, expand=True)
        
        results_frame = ttk.Frame(self.results_paned)
        self.results_paned.add(results_frame, weight=3)
        
        # Results treeview with icons
        columns = ("type", "name", "path", "size", "modified")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="tree headings", selectmode="browse")
        
        # Configure column headings with sort commands
        self.results_tree.heading("type", text="")
        self.results_tree.heading("name", text="Name", command=lambda: self._sort_results("name"))
        self.results_tree.heading("path", text="Path", command=lambda: self._sort_results("path"))
        self.results_tree.heading("size", text="Size", command=lambda: self._sort_results("size"))
        self.results_tree.heading("modified", text="Modified", command=lambda: self._sort_results("modified"))
        
        # Sort state
        self._sort_column = None
        self._sort_reverse = False
        self._last_results = []
        
        # Configure column widths
        self.results_tree.column("type", width=30, minwidth=30, stretch=False)
        self.results_tree.column("name", width=200, minwidth=100)
        self.results_tree.column("path", width=350, minwidth=200)
        self.results_tree.column("size", width=80, minwidth=60)
        self.results_tree.column("modified", width=140, minwidth=100)
        
        # Configure tags for styling
        self.results_tree.tag_configure("directory", foreground="#006666", font=('Segoe UI', 9, 'bold'))
        self.results_tree.tag_configure("file", foreground="#333333")
        self.results_tree.tag_configure("evenrow", background="#f8f9fa")
        self.results_tree.tag_configure("oddrow", background="#ffffff")
        self.results_tree.tag_configure("selected", background="#cce5ff")
        self.results_tree.tag_configure("match", foreground="#d9534f", font=('Segoe UI', 9, 'bold'))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind double-click to open file location
        self.results_tree.bind("<Double-1>", self._on_double_click)
        # Bind right-click for context menu
        self.results_tree.bind("<Button-3>", self._show_context_menu)
        # Bind selection change to update preview
        self.results_tree.bind("<<TreeviewSelect>>", lambda e: self._load_preview())
        
        # Store full paths for items (for reveal functionality)
        self._item_paths = {}
        self._context_menu = None
        
        # Preview pane (right side)
        self.preview_frame = ttk.LabelFrame(self.results_paned, text="Preview", padding="5")
        self.preview_text = tk.Text(self.preview_frame, wrap=tk.WORD, state=tk.DISABLED, 
                                     font=('Consolas', 9), height=10, bg='#f8f9fa')
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        preview_scroll = ttk.Scrollbar(self.preview_frame, command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_scroll.set)
        preview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Empty state label (shown when no results)
        self.empty_state_var = tk.StringVar(value="Type to search across indexed files")
        self.empty_state_label = ttk.Label(search_frame, textvariable=self.empty_state_var, 
                                           font=('Segoe UI', 11), foreground="gray", justify=tk.CENTER)
        self.empty_state_label.pack(pady=40)
        
        # Raise empty state above results_paned when visible
        self.empty_state_label.lift()
        
        # Preview toggle button
        self.preview_visible = tk.BooleanVar(value=False)
        self.preview_btn = ttk.Button(search_input_frame, text="👁", width=3, 
                                     command=self._toggle_preview)
        self.preview_btn.pack(side=tk.LEFT, padx=(5, 0))
        self._add_tooltip(self.preview_btn, "Toggle preview pane")
        
        # Status bar at bottom of search tab
        status_bar = ttk.Frame(search_frame, relief=tk.SUNKEN, padding="2")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))
        
        self.status_bar_var = tk.StringVar(value="Ready")
        ttk.Label(status_bar, textvariable=self.status_bar_var, font=('Segoe UI', 8), foreground="gray").pack(side=tk.LEFT)
        
        self.shortcuts_hint = ttk.Label(status_bar, text="Ctrl+K: Search | Esc: Clear | Ctrl+P: Preview | Ctrl+C: Copy | ▲▼: Navigate", 
                                        font=('Segoe UI', 8), foreground="gray")
        self.shortcuts_hint.pack(side=tk.RIGHT)
        
        # Memory/Disk Usage tab
        usage_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(usage_frame, text="Memory/Disk Usage")
        
        # Favorites / Quick Access tab
        favorites_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(favorites_frame, text="Favorites")
        self._setup_favorites_tab(favorites_frame)
        
        # Drive selection
        drive_frame = ttk.LabelFrame(usage_frame, text="Select Drive", padding="5")
        drive_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.drive_var = tk.StringVar(value="Select a drive...")
        self.drive_combo = ttk.Combobox(drive_frame, textvariable=self.drive_var, state="readonly", width=40)
        self.drive_combo.pack(side=tk.LEFT, padx=(0, 10))
        
        self.analyze_btn = ttk.Button(drive_frame, text="Analyze", command=self._analyze_drive)
        self.analyze_btn.pack(side=tk.LEFT)
        
        # Paned window for treemap and memory graph
        self.usage_paned = ttk.PanedWindow(usage_frame, orient=tk.VERTICAL)
        self.usage_paned.pack(fill=tk.BOTH, expand=True)
        
        # Treemap panel (top)
        self.treemap_panel = TreemapPanel(self.usage_paned)
        self.usage_paned.add(self.treemap_panel, weight=1)
        
        # Memory graph panel (bottom)
        self.memory_graph_panel = MemoryGraphPanel(self.usage_paned)
        self.usage_paned.add(self.memory_graph_panel, weight=1)
    
    def _connect_signals(self):
        # Live search on key release with debounce
        self.search_input.bind("<KeyRelease>", self._on_search_typing)
        self.search_input.bind("<Return>", lambda e: self._do_search())
        
        # Show history on focus
        self.search_input.bind("<FocusIn>", lambda e: self._show_history())
        
        # Global keyboard shortcuts
        self.root.bind("<Control-k>", lambda e: self.search_input.focus_set())
        self.root.bind("<Escape>", self._on_escape)
        self.root.bind("<Control-p>", lambda e: self._toggle_preview())
        self.results_tree.bind("<Control-c>", lambda e: self._copy_selected_path())
        self.results_tree.bind("<Control-o>", lambda e: self._open_file(self._get_selected_path() or ""))
        self.results_tree.bind("<Control-r>", lambda e: self._reveal_in_explorer(self._get_selected_path() or ""))
        self.results_tree.bind("<Return>", lambda e: self._on_double_click(None))
        
        # Keyboard navigation: Down arrow from search input moves to results
        self.search_input.bind("<Down>", lambda e: self._focus_first_result())
        self.results_tree.bind("<Up>", self._on_tree_up_arrow)
        
        # Bind click on main window to close history popup
        self.root.bind("<Button-1>", self._on_root_click)
        
        # Populate drives on tab change and save active tab
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
    
    def _start_background_indexing(self):
        """Start the background indexer."""
        # Set up callbacks
        self.bg_indexer.set_status_callback(self._on_status_update)
        self.bg_indexer.set_progress_callback(self._on_progress_update)
        
        # Start indexing
        self.bg_indexer.start()
        self.progress.start()
        self.stop_btn.configure(state=tk.NORMAL)
        
        # Update drives info
        drives = self.bg_indexer.get_drives()
        drive_names = [d.name for d in drives if d.drive_type == 'fixed']
        self.drives_var.set(f"Drives: {', '.join(drive_names)}")
        
        # Populate drive combo for treemap
        self._populate_drive_combo()
        
        # Schedule periodic stats update
        self._update_stats()
    
    def _stop_indexing(self):
        """Stop the background indexer."""
        self.bg_indexer.stop()
        self.progress.stop()
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_var.set("Indexing stopped")
        self.status_bar_var.set("Indexing stopped by user")
    
    def _on_status_update(self, message: str):
        """Handle status updates from background indexer."""
        self.root.after(0, lambda: self.status_var.set(message))
        self.root.after(0, lambda: self.status_bar_var.set(message))
    
    def _on_progress_update(self, count: int, current_path: str):
        """Handle progress updates from background indexer."""
        # Update stats periodically
        self.root.after(0, lambda: self.stats_var.set(f"Indexing... {count} items"))
    
    def _update_stats(self):
        """Update index statistics periodically."""
        if not self.bg_indexer.is_indexing():
            stats = self.indexer.get_stats()
            total = stats['total_files'] + stats['total_directories']
            self.stats_var.set(f"{total:,} items indexed ({stats['total_directories']:,} folders, {stats['total_files']:,} files)")
        
        # Schedule next update
        self.root.after(5000, self._update_stats)
    
    def _on_search_typing(self, event):
        """Handle live search with debounce."""
        # Cancel any pending search
        if self._search_after_id:
            self.root.after_cancel(self._search_after_id)
        
        # Schedule new search after debounce (default 200ms, configurable)
        debounce_ms = getattr(self, '_debounce_ms', 200)
        self._search_after_id = self.root.after(debounce_ms, self._do_search)
    
    def _is_regex_pattern(self, query: str) -> bool:
        """Check if query is a regex pattern enclosed in slashes."""
        return query.startswith('/') and query.endswith('/') and len(query) > 2
    
    def _do_search(self):
        """Execute the search and display results."""
        self._search_after_id = None
        
        query = self.search_input.get().strip()
        self._last_query = query
        if not query:
            self._clear_search()
            return
        
        # Determine search type
        if self._content_search_var.get():
            # Search in file contents
            results = self.indexer.search_by_content(query)
        elif self._is_regex_pattern(query):
            regex_pattern = query[1:-1]
            results = self.indexer.search_regex(regex_pattern)
        elif self.indexer._is_glob_pattern(query):
            results = self.indexer.search(query)
        else:
            results = self.indexer.search(query)
        
        # Apply file type filter
        filter_type = self.file_type_var.get()
        if filter_type == "Files":
            results = [r for r in results if not r.is_directory]
        elif filter_type == "Directories":
            results = [r for r in results if r.is_directory]
        
        self._display_results(results, query)
        self.status_var.set(f"Found {len(results)} results")
        self.results_count_var.set(f"{len(results)} results")
        self.status_bar_var.set(f"Search complete — {len(results)} results")
        self.root.title(f"{APP_NAME} v{APP_VERSION} — {len(results)} results for '{query}'")
        
        # Save to history
        search_type = 'content' if self._content_search_var.get() else 'regex' if self._is_regex_pattern(query) else 'glob' if self.indexer._is_glob_pattern(query) else 'name'
        self.search_history.add_entry(query, len(results), search_type)
        
        # Update favorites list
        self._update_favorites_list()
    
    def _clear_results(self):
        """Clear all results from the tree."""
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self._item_paths.clear()
        self.results_count_var.set("")
        self._last_results = []
        self._sort_column = None
        self._sort_reverse = False
        # Reset headings
        for col, text in (("name", "Name"), ("path", "Path"), ("size", "Size"), ("modified", "Modified")):
            self.results_tree.heading(col, text=text)
    
    def _get_file_icon(self, is_directory: bool, extension: str = "") -> str:
        """Get icon character for file type."""
        if is_directory:
            return "📁"
        
        icon_map = {
            '.py': '🐍', '.go': '🔷', '.js': '📜', '.ts': '📘',
            '.html': '🌐', '.css': '🎨', '.json': '📋', '.md': '📝',
            '.txt': '📄', '.pdf': '📕', '.zip': '🗜️', '.rar': '🗜️', '.7z': '🗜️',
            '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️', '.bmp': '🖼️', '.svg': '🖼️', '.webp': '🖼️',
            '.mp3': '🎵', '.wav': '🎵', '.flac': '🎵', '.aac': '🎵', '.ogg': '🎵',
            '.mp4': '🎬', '.avi': '🎬', '.mkv': '🎬', '.mov': '🎬', '.wmv': '🎬',
            '.exe': '⚙️', '.dll': '⚙️', '.so': '⚙️', '.dylib': '⚙️',
            '.sh': '💻', '.bat': '💻', '.cmd': '💻', '.ps1': '💻',
            '.rs': '🦀', '.java': '☕', '.c': '🔧', '.cpp': '🔧', '.h': '📄', '.hpp': '📄',
            '.xml': '📋', '.yaml': '📋', '.yml': '📋', '.toml': '📋', '.ini': '📋', '.cfg': '📋',
            '.sql': '🗃️', '.db': '🗃️', '.sqlite': '🗃️', '.sqlite3': '🗃️',
            '.doc': '📝', '.docx': '📝', '.xls': '📊', '.xlsx': '📊', '.ppt': '📊', '.pptx': '📊',
            '.csv': '📊', '.tsv': '📊',
        }
        
        return icon_map.get(extension.lower(), '📄')
    
    def _sort_results(self, column: str):
        """Sort results by the given column."""
        if not self._last_results:
            return
        
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        
        def sort_key(file_info):
            if column == "name":
                return file_info.name.lower()
            elif column == "path":
                return file_info.parent_dir.lower()
            elif column == "size":
                return file_info.size
            elif column == "modified":
                return file_info.modified_time
            return file_info.name.lower()
        
        self._last_results.sort(key=sort_key, reverse=self._sort_reverse)
        self._display_results(self._last_results, None)
        
        # Update heading indicators
        for col in ("name", "path", "size", "modified"):
            text = {"name": "Name", "path": "Path", "size": "Size", "modified": "Modified"}[col]
            if col == self._sort_column:
                text += " ▼" if self._sort_reverse else " ▲"
            self.results_tree.heading(col, text=text)
    
    def _highlight_match(self, text: str, query: str) -> str:
        """Highlight the query match in text for display."""
        if not query or len(query) < 2:
            return text
        # Simple case-insensitive highlight
        lower_text = text.lower()
        lower_query = query.lower()
        if lower_query in lower_text:
            start = lower_text.index(lower_query)
            end = start + len(query)
            return text[:start] + text[start:end] + text[end:]
        return text
    
    def _display_results(self, results, query: str):
        """Display search results in the tree with icons."""
        if query is not None:
            self._last_results = list(results)
            self._last_query = query
        else:
            results = self._last_results
            query = getattr(self, '_last_query', '')
        
        self._clear_results()
        
        if not results and query is not None:
            self.empty_state_var.set(f'No results found for "{query}"')
            self.empty_state_label.pack(pady=40)
            self.empty_state_label.lift()
            return
        else:
            self.empty_state_label.pack_forget()
        
        for i, file_info in enumerate(results):
            icon = self._get_file_icon(file_info.is_directory, file_info.extension)
            
            if file_info.is_directory:
                size_str = "-"
            else:
                size_str = self._format_size(file_info.size)
            
            modified_str = datetime.fromtimestamp(file_info.modified_time).strftime("%Y-%m-%d %H:%M")
            
            tag = "directory" if file_info.is_directory else "file"
            
            row_tag = "evenrow" if i % 2 == 0 else "oddrow"
            item_id = self.results_tree.insert("", tk.END, values=(
                icon,
                file_info.name,
                file_info.parent_dir,
                size_str,
                modified_str
            ), tags=(tag, row_tag))
            
            self._item_paths[item_id] = file_info.path
    
    def _format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def _focus_first_result(self):
        """Move focus to the first result in the tree."""
        children = self.results_tree.get_children()
        if children:
            self.results_tree.focus_set()
            self.results_tree.selection_set(children[0])
            self.results_tree.focus(children[0])
            self.results_tree.see(children[0])
        return "break"
    
    def _on_tree_up_arrow(self, event):
        """Move focus back to search input when pressing Up at the top of the tree."""
        selection = self.results_tree.selection()
        if selection:
            index = self.results_tree.index(selection[0])
            if index == 0:
                self.search_input.focus_set()
                return "break"
        return None
    
    def _get_selected_path(self) -> Optional[str]:
        """Get the full path of the currently selected result."""
        selection = self.results_tree.selection()
        if not selection:
            return None
        return self._item_paths.get(selection[0])
    
    def _on_double_click(self, event):
        """Open file location when double-clicking a result."""
        full_path = self._get_selected_path()
        if not full_path:
            return
        self._reveal_in_explorer(full_path)
    
    def _toggle_preview(self):
        """Toggle the preview pane visibility."""
        if self.preview_visible.get():
            self.results_paned.forget(self.preview_frame)
            self.preview_visible.set(False)
        else:
            self.results_paned.add(self.preview_frame, weight=1)
            self.preview_visible.set(True)
            # Load preview for current selection
            self._load_preview()
    
    def _load_preview(self):
        """Load preview for the selected file."""
        if not self.preview_visible.get():
            return
        full_path = self._get_selected_path()
        if not full_path:
            self.preview_text.configure(state=tk.NORMAL)
            self.preview_text.delete('1.0', tk.END)
            self.preview_text.insert('1.0', "Select a file to preview its contents.")
            self.preview_text.configure(state=tk.DISABLED)
            return
        
        path = Path(full_path)
        if path.is_dir():
            self.preview_text.configure(state=tk.NORMAL)
            self.preview_text.delete('1.0', tk.END)
            self.preview_text.insert('1.0', f"Directory: {path}\n\n(Cannot preview directories)")
            self.preview_text.configure(state=tk.DISABLED)
            return
        
        # Try to read file preview
        try:
            size = path.stat().st_size
            if size > 100 * 1024:
                self.preview_text.configure(state=tk.NORMAL)
                self.preview_text.delete('1.0', tk.END)
                self.preview_text.insert('1.0', f"File too large to preview ({self._format_size(size)}).\n\nMax preview size: 100 KB")
                self.preview_text.configure(state=tk.DISABLED)
                return
            
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(5000)
            
            self.preview_text.configure(state=tk.NORMAL)
            self.preview_text.delete('1.0', tk.END)
            self.preview_text.insert('1.0', content)
            if len(content) >= 5000:
                self.preview_text.insert(tk.END, "\n\n... (preview truncated)")
            self.preview_text.configure(state=tk.DISABLED)
        except Exception as e:
            self.preview_text.configure(state=tk.NORMAL)
            self.preview_text.delete('1.0', tk.END)
            self.preview_text.insert('1.0', f"Cannot preview file:\n{e}")
            self.preview_text.configure(state=tk.DISABLED)
    
    def _reveal_in_explorer(self, full_path: str):
        """Reveal the given path in the system file manager."""
        path = Path(full_path)
        try:
            if platform.system() == 'Windows':
                subprocess.run(['explorer', '/select,', str(path)], check=False)
            elif platform.system() == 'Darwin':
                subprocess.run(['open', '-R', str(path)], check=False)
            else:
                subprocess.run(['xdg-open', str(path.parent)], check=False)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file location: {e}")
    
    def _open_file(self, full_path: str):
        """Open the given file with the default application."""
        path = Path(full_path)
        try:
            if platform.system() == 'Windows':
                os.startfile(str(path))
            elif platform.system() == 'Darwin':
                subprocess.run(['open', str(path)], check=False)
            else:
                subprocess.run(['xdg-open', str(path)], check=False)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file: {e}")
    
    def _copy_selected_path(self):
        """Copy the selected result's path to the clipboard."""
        full_path = self._get_selected_path()
        if full_path:
            self.root.clipboard_clear()
            self.root.clipboard_append(full_path)
            self.status_var.set("Path copied to clipboard")
            self.status_bar_var.set("Path copied to clipboard")
    
    def _copy_selected_filename(self):
        """Copy the selected result's filename to the clipboard."""
        full_path = self._get_selected_path()
        if full_path:
            filename = Path(full_path).name
            self.root.clipboard_clear()
            self.root.clipboard_append(filename)
            self.status_var.set(f"Filename copied: {filename}")
            self.status_bar_var.set("Filename copied to clipboard")
    
    def _search_in_directory(self, full_path: str):
        """Filter current results to only show items in the selected item's directory."""
        path = Path(full_path)
        directory = str(path.parent if path.is_file() else path)
        if not self._last_results:
            return
        filtered = [r for r in self._last_results if str(r.parent_dir).startswith(directory) or str(r.path).startswith(directory)]
        self._display_results(filtered, None)
        self.status_var.set(f"Filtered to {len(filtered)} results in {directory}")
        self.results_count_var.set(f"{len(filtered)} filtered")
        self.status_bar_var.set(f"Filtered by directory: {directory}")
    
    def _show_context_menu(self, event):
        """Show right-click context menu for search results."""
        # Select the row under the cursor
        row_id = self.results_tree.identify_row(event.y)
        if row_id:
            self.results_tree.selection_set(row_id)
        
        full_path = self._get_selected_path()
        if not full_path:
            return
        
        if self._context_menu:
            self._context_menu.destroy()
        
        self._context_menu = tk.Menu(self.root, tearoff=0)
        self._context_menu.add_command(label="Open File", command=lambda: self._open_file(full_path), accelerator="Ctrl+O")
        self._context_menu.add_command(label="Reveal in Explorer", command=lambda: self._reveal_in_explorer(full_path), accelerator="Ctrl+R")
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Copy Path", command=self._copy_selected_path, accelerator="Ctrl+C")
        self._context_menu.add_command(label="Copy Filename", command=self._copy_selected_filename)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Search in this directory", command=lambda: self._search_in_directory(full_path))
        
        self._context_menu.post(event.x_root, event.y_root)
    
    def _populate_drive_combo(self):
        """Populate the drive combo box with available drives."""
        drives = get_drives_for_analysis()
        drive_list = [d['name'] for d in drives]
        self.drive_combo['values'] = drive_list
        if drive_list:
            self.drive_var.set(drive_list[0])
    
    def _on_tab_changed(self, event):
        """Handle tab change event."""
        selected_tab = self.notebook.tab(self.notebook.select(), "text")
        self._save_active_tab(selected_tab)
        if selected_tab == "Memory/Disk Usage":
            self._populate_drive_combo()
    
    def _save_active_tab(self, tab_name: str):
        """Save the currently active tab to config."""
        from ..config import CONFIG_DIR
        try:
            tab_file = CONFIG_DIR / "active_tab.txt"
            with open(tab_file, 'w') as f:
                f.write(tab_name)
        except Exception:
            pass
    
    def _restore_active_tab(self):
        """Restore the last active tab from config."""
        from ..config import CONFIG_DIR
        try:
            tab_file = CONFIG_DIR / "active_tab.txt"
            if tab_file.exists():
                with open(tab_file, 'r') as f:
                    tab_name = f.read().strip()
                for i in range(self.notebook.index('end')):
                    if self.notebook.tab(i, "text") == tab_name:
                        self.notebook.select(i)
                        break
        except Exception:
            pass
    
    def _analyze_drive(self):
        """Start analysis of selected drive."""
        drive_name = self.drive_var.get()
        if not drive_name or drive_name == "Select a drive...":
            messagebox.showwarning("Warning", "Please select a drive first.")
            return
        
        # Find drive path
        drives = get_drives_for_analysis()
        drive_path = None
        for d in drives:
            if d['name'] == drive_name:
                drive_path = d['path']
                break
        
        if not drive_path:
            messagebox.showerror("Error", "Could not find drive path.")
            return
        
        # Disable button during analysis
        self.analyze_btn.configure(state=tk.DISABLED)
        self.status_var.set(f"Analyzing {drive_name}...")
        self.progress.start()
        
        # Set up callbacks for size analyzer
        self.size_analyzer.set_progress_callback(self._on_size_progress)
        self.size_analyzer.set_complete_callback(lambda node: self._on_size_complete(node, drive_name))
        
        # Start async analysis
        self.size_analyzer.analyze_async(drive_path)
    
    def _on_size_progress(self, count: int, current_path: str):
        """Handle size analysis progress updates."""
        self.root.after(0, lambda: self.stats_var.set(f"Scanning... {count} items"))
    
    def _on_size_complete(self, root_node: "SizeNode", drive_name: str):
        """Handle size analysis completion."""
        self.root.after(0, lambda: self._display_treemap(root_node, drive_name))
    
    def _display_treemap(self, root_node: "SizeNode", drive_name: str):
        """Display treemap and memory graph visualizations."""
        self.progress.stop()
        self.analyze_btn.configure(state=tk.NORMAL)
        self.status_var.set(f"Analysis complete: {drive_name}")
        
        if self.treemap_panel:
            self.treemap_panel.load_drive(root_node.path, root_node)
        
        if self.memory_graph_panel:
            self.memory_graph_panel.load_drive(root_node.path, root_node)
    
    def _add_tooltip(self, widget, text: str):
        """Add a simple tooltip to a widget."""
        tooltip = None
        
        def on_enter(event):
            nonlocal tooltip
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            tooltip = tk.Toplevel(widget)
            tooltip.overrideredirect(True)
            tooltip.geometry(f"+{x}+{y}")
            tooltip.attributes('-topmost', True)
            label = ttk.Label(tooltip, text=text, background="#ffffe0", foreground="#333333",
                              relief=tk.SOLID, borderwidth=1, padding=(4, 2), font=('Segoe UI', 8))
            label.pack()
        
        def on_leave(event):
            nonlocal tooltip
            if tooltip:
                tooltip.destroy()
                tooltip = None
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    
    def _export_results(self):
        """Export current search results to a text file."""
        if not self._last_results:
            messagebox.showinfo("Export", "No results to export.")
            return
        
        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Search Results"
        )
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("Name\tPath\tSize\tModified\tType\n")
                for r in self._last_results:
                    size_str = "-" if r.is_directory else self._format_size(r.size)
                    modified_str = datetime.fromtimestamp(r.modified_time).strftime("%Y-%m-%d %H:%M")
                    f.write(f"{r.name}\t{r.parent_dir}\t{size_str}\t{modified_str}\t{'Directory' if r.is_directory else 'File'}\n")
            self.status_var.set(f"Exported {len(self._last_results)} results to {Path(file_path).name}")
            self.status_bar_var.set(f"Exported to {Path(file_path).name}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {e}")
    
    def _show_shortcuts(self):
        """Show keyboard shortcuts help dialog."""
        shortcuts = (
            "Keyboard Shortcuts\n\n"
            "Global:\n"
            "  Ctrl+K     Focus search box\n"
            "  Ctrl+P     Toggle preview pane\n"
            "  Esc        Clear search / close popup\n"
            "  Alt+F4     Exit application\n\n"
            "Search Results:\n"
            "  ▲ / ▼      Navigate results\n"
            "  Enter      Open selected file\n"
            "  Ctrl+O     Open file\n"
            "  Ctrl+R     Reveal in Explorer\n"
            "  Ctrl+C     Copy full path\n\n"
            "Treemap (Disk Usage tab):\n"
            "  Ctrl++     Zoom in\n"
            "  Ctrl+-     Zoom out\n"
            "  Ctrl+0     Reset view\n"
            "  Right-drag Pan view\n"
            "  Scroll     Zoom in/out"
        )
        messagebox.showinfo("Keyboard Shortcuts", shortcuts)
    
    def _show_settings(self):
        """Show settings dialog for user preferences."""
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.geometry("400x300")
        settings_win.transient(self.root)
        settings_win.grab_set()
        
        # Search settings
        search_frame = ttk.LabelFrame(settings_win, text="Search", padding="10")
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        self._debounce_var = tk.IntVar(value=200)
        ttk.Label(search_frame, text="Search debounce (ms):").pack(anchor=tk.W)
        ttk.Spinbox(search_frame, from_=50, to=1000, increment=50, textvariable=self._debounce_var, width=10).pack(anchor=tk.W, pady=(0, 5))
        
        self._results_limit_var = tk.IntVar(value=100)
        ttk.Label(search_frame, text="Max results:").pack(anchor=tk.W)
        ttk.Spinbox(search_frame, from_=10, to=1000, increment=10, textvariable=self._results_limit_var, width=10).pack(anchor=tk.W)
        
        # Indexing settings
        index_frame = ttk.LabelFrame(settings_win, text="Indexing", padding="10")
        index_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self._auto_index_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(index_frame, text="Enable background indexing", variable=self._auto_index_var).pack(anchor=tk.W)
        
        self._index_interval_var = tk.IntVar(value=300)
        ttk.Label(index_frame, text="Index interval (seconds):").pack(anchor=tk.W, pady=(5, 0))
        ttk.Spinbox(index_frame, from_=60, to=3600, increment=60, textvariable=self._index_interval_var, width=10).pack(anchor=tk.W)
        
        # Buttons
        btn_frame = ttk.Frame(settings_win)
        btn_frame.pack(fill=tk.X, padx=10, pady=(10, 10))
        ttk.Button(btn_frame, text="Save", command=lambda: self._save_settings(settings_win)).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=settings_win.destroy).pack(side=tk.RIGHT)
    
    def _save_settings(self, window):
        """Save settings and close dialog."""
        # Apply debounce
        self._debounce_ms = self._debounce_var.get()
        # Apply auto-indexing
        if self._auto_index_var.get():
            if not self.bg_indexer.is_indexing():
                self.bg_indexer.start()
        else:
            self.bg_indexer.stop()
        window.destroy()
        self.status_var.set("Settings saved")
        self.status_bar_var.set("Settings saved")
    
    def _toggle_dark_mode(self):
        """Toggle dark mode for the search tab."""
        if self._dark_mode_var.get():
            self.root.configure(bg='#1a1a2e')
            # Update treeview style for dark mode
            style = ttk.Style()
            style.configure('Custom.Treeview', background='#16213e', foreground='#eaeaea', fieldbackground='#16213e')
            style.configure('Custom.Treeview.Heading', background='#0f3460', foreground='#eaeaea')
            self.results_tree.configure(style='Custom.Treeview')
        else:
            self.root.configure(bg='')
            style = ttk.Style()
            style.configure('Custom.Treeview', background='', foreground='', fieldbackground='')
            style.configure('Custom.Treeview.Heading', background='', foreground='')
            self.results_tree.configure(style='')
    
    def _setup_favorites_tab(self, parent):
        """Setup the favorites/quick access tab."""
        ttk.Label(parent, text="Quick Access Locations", font=('Segoe UI', 12, 'bold')).pack(anchor=tk.W, pady=(0, 10))
        
        # Common locations
        common_paths = [
            ("Desktop", Path.home() / "Desktop"),
            ("Documents", Path.home() / "Documents"),
            ("Downloads", Path.home() / "Downloads"),
            ("Home", Path.home()),
            ("Project Root", Path.cwd()),
        ]
        
        for name, path in common_paths:
            if path.exists():
                btn = ttk.Button(parent, text=f"📁 {name}", 
                                command=lambda p=str(path): self._search_path(p),
                                width=30)
                btn.pack(anchor=tk.W, pady=2)
        
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        ttk.Label(parent, text="Recent Searches", font=('Segoe UI', 12, 'bold')).pack(anchor=tk.W, pady=(0, 10))
        self._favorites_list = tk.Listbox(parent, height=10, font=('Segoe UI', 10))
        self._favorites_list.pack(fill=tk.BOTH, expand=True)
        self._favorites_list.bind("<Double-1>", lambda e: self._on_favorite_select())
        self._update_favorites_list()
    
    def _update_favorites_list(self):
        """Update the favorites list with recent searches."""
        if hasattr(self, '_favorites_list'):
            self._favorites_list.delete(0, tk.END)
            for entry in self.search_history.get_recent(20):
                self._favorites_list.insert(tk.END, f"{entry.query} ({entry.result_count} results)")
    
    def _on_favorite_select(self):
        """Handle selection from favorites list."""
        selection = self._favorites_list.curselection()
        if selection:
            text = self._favorites_list.get(selection[0])
            query = text.split(" (")[0]
            self.notebook.select(0)  # Switch to search tab
            self.search_input.delete(0, tk.END)
            self.search_input.insert(0, query)
            self._do_search()
    
    def _search_path(self, path: str):
        """Search for items in a specific path."""
        self.notebook.select(0)  # Switch to search tab
        self.search_input.delete(0, tk.END)
        self.search_input.insert(0, path)
        self._do_search()
    
    def _show_about(self):
        """Show the About dialog."""
        messagebox.showinfo(
            "About",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "A fast desktop file search application.\n"
            "Features: instant search, content search, regex/glob patterns,\n"
            "disk usage visualization with treemap and file tree."
        )
    
    def run(self):
        """Start the main event loop."""
        self.root.mainloop()
    
    def _show_history(self):
        """Show search history popup."""
        if self._history_popup and self._history_popup.winfo_exists():
            return  # Already open, don't recreate
        
        # Create popup window
        self._history_popup = tk.Toplevel(self.root)
        self._history_popup.title("Search History")
        self._history_popup.overrideredirect(True)
        self._history_popup.attributes('-topmost', True)
        
        # Position below search input
        x = self.search_input.winfo_rootx()
        y = self.search_input.winfo_rooty() + self.search_input.winfo_height() + 2
        self._history_popup.geometry(f"+{x}+{y}")
        
        # Bind click on popup to mark it as active (prevent closing)
        self._history_popup.bind("<Button-1>", lambda e: self._popup_clicked())
        self._history_popup.bind("<Escape>", lambda e: self._hide_history())
        
        # Create history list
        history_frame = ttk.Frame(self._history_popup, relief="solid", borderwidth=1)
        history_frame.pack(fill=tk.BOTH, expand=True)
        
        from datetime import datetime
        entries = self.search_history.get_recent(10)
        if not entries:
            ttk.Label(history_frame, text="No recent searches", foreground="gray").pack(padx=10, pady=10)
        else:
            type_icons = {'name': '🔍', 'content': '📝', 'regex': '🔤', 'glob': '🌐'}
            for entry in entries:
                icon = type_icons.get(entry.search_type, '🔍')
                # Relative time
                age = datetime.now().timestamp() - entry.timestamp
                if age < 60:
                    time_str = "just now"
                elif age < 3600:
                    time_str = f"{int(age/60)}m ago"
                elif age < 86400:
                    time_str = f"{int(age/3600)}h ago"
                else:
                    time_str = f"{int(age/86400)}d ago"
                btn = ttk.Button(
                    history_frame,
                    text=f"{icon} {entry.query}  ({entry.result_count} results)  ·  {time_str}",
                    command=lambda q=entry.query: self._select_history_item(q),
                    width=50
                )
                btn.pack(fill=tk.X, padx=5, pady=2)
        
        # Clear history button
        if entries:
            clear_btn = ttk.Button(
                history_frame,
                text="Clear History",
                command=self._clear_history,
                width=50
            )
            clear_btn.pack(fill=tk.X, padx=5, pady=5)
    
    def _popup_clicked(self):
        """Mark popup as recently clicked to prevent immediate close."""
        self._popup_active = True
        self.root.after(200, lambda: setattr(self, '_popup_active', False))
    
    def _clear_search(self):
        """Clear search input and results."""
        self.search_input.delete(0, tk.END)
        self._clear_results()
        self.status_var.set("Ready")
        self.status_bar_var.set("Ready")
        self.empty_state_var.set("Type to search across indexed files")
        self.empty_state_label.pack(pady=40)
        self.empty_state_label.lift()
        self.search_input.focus_set()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
    
    def _on_escape(self, event=None):
        """Handle Escape key: close history popup or clear search results."""
        if self._history_popup and self._history_popup.winfo_exists():
            self._hide_history()
            return "break"
        if self.search_input.get().strip():
            self._clear_search()
            return "break"
        return None

    def _on_root_click(self, event):
        """Handle clicks on main window - close history popup if clicking outside."""
        if self._history_popup and self._history_popup.winfo_exists():
            # Check if click is outside the popup
            if not getattr(self, '_popup_active', False):
                self._hide_history()
    
    def _hide_history(self):
        """Hide search history popup."""
        if self._history_popup and self._history_popup.winfo_exists():
            popup = self._history_popup
            self._history_popup = None
            popup.destroy()
    
    def _select_history_item(self, query: str):
        """Select a history item and execute search."""
        self.search_input.delete(0, tk.END)
        self.search_input.insert(0, query)
        self._hide_history()
        self._do_search()
        self.search_input.focus_set()  # Return focus to search input
    
    def _clear_history(self):
        """Clear search history."""
        self.search_history.clear()
        self._hide_history()  # Close popup after clearing
    
    def _load_geometry(self):
        """Load and apply saved window geometry."""
        from ..config import CONFIG_DIR
        geometry_file = CONFIG_DIR / "window_geometry.txt"
        if geometry_file.exists():
            try:
                with open(geometry_file, 'r') as f:
                    geometry = f.read().strip()
                    if geometry:
                        self.root.geometry(geometry)
                        return
            except Exception:
                pass
        self.root.geometry("900x600")
    
    def _save_geometry(self):
        """Save current window geometry."""
        from ..config import CONFIG_DIR
        try:
            geometry = self.root.geometry()
            geometry_file = CONFIG_DIR / "window_geometry.txt"
            with open(geometry_file, 'w') as f:
                f.write(geometry)
        except Exception:
            pass
    
    def close(self):
        """Clean up resources."""
        self._save_geometry()
        self.bg_indexer.stop()
        self.indexer.close()
        self.size_analyzer.stop()
        if self._history_popup and self._history_popup.winfo_exists():
            self._history_popup.destroy()
