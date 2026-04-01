# Main window for Search.io desktop application
import tkinter as tk
from tkinter import ttk, messagebox
from threading import Thread
from datetime import datetime
from pathlib import Path
import subprocess
import platform
import re

from core.indexer import FileIndexer
from core.background_indexer import BackgroundIndexer
from core.size_analyzer import SizeAnalyzer, SizeNode, get_drives_for_analysis, format_size
from core.search_history import SearchHistory
from gui.treemap_widget import TreemapPanel
from gui.memory_graph_widget import MemoryGraphPanel
from config import APP_NAME, APP_VERSION  # Root level config import


class MainWindow:
    """Main application window for Search.io using Tkinter."""
    
    def __init__(self):
        self.indexer = FileIndexer()
        self.bg_indexer = BackgroundIndexer(self.indexer, update_interval=300)  # 5 min updates
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("900x600")
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
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Notebook for tabs (Search and Memory/Disk Usage)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
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
        
        self.drives_var = tk.StringVar(value="Detecting drives...")
        self.drives_label = ttk.Label(status_frame, textvariable=self.drives_var, foreground="gray")
        self.drives_label.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Stats frame
        stats_frame = ttk.Frame(search_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.stats_var = tk.StringVar(value="0 files indexed")
        ttk.Label(stats_frame, textvariable=self.stats_var, foreground="gray").pack(side=tk.LEFT)
        
        # Search frame - live search on typing
        search_input_frame = ttk.Frame(search_frame)
        search_input_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(search_input_frame, text="Search:").pack(side=tk.LEFT)
        self.search_input = ttk.Entry(search_input_frame, width=50)
        self.search_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # History button
        self.history_btn = ttk.Button(search_input_frame, text="🕐", width=3, command=self._show_history)
        self.history_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Content search toggle
        self.content_search_cb = ttk.Checkbutton(search_input_frame, text="Content", variable=self._content_search_var)
        self.content_search_cb.pack(side=tk.LEFT, padx=(10, 0))
        
        # Hint label for search patterns
        hint_label = ttk.Label(search_input_frame, text="(use *.ext for glob, or /regex/ for regex)", foreground="gray")
        hint_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Results treeview with icons
        columns = ("type", "name", "path", "size", "modified")
        self.results_tree = ttk.Treeview(search_frame, columns=columns, show="tree headings", selectmode="browse")
        
        # Configure column headings
        self.results_tree.heading("type", text="")
        self.results_tree.heading("name", text="Name")
        self.results_tree.heading("path", text="Path")
        self.results_tree.heading("size", text="Size")
        self.results_tree.heading("modified", text="Modified")
        
        # Configure column widths
        self.results_tree.column("type", width=30, minwidth=30, stretch=False)
        self.results_tree.column("name", width=200, minwidth=100)
        self.results_tree.column("path", width=350, minwidth=200)
        self.results_tree.column("size", width=80, minwidth=60)
        self.results_tree.column("modified", width=140, minwidth=100)
        
        # Configure tags for styling
        self.results_tree.tag_configure("directory", foreground="#008080", font=('Segoe UI', 9, 'bold'))
        self.results_tree.tag_configure("file", foreground="#333333")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind double-click to open file location
        self.results_tree.bind("<Double-1>", self._on_double_click)
        
        # Store full paths for items (for reveal functionality)
        self._item_paths = {}
        
        # Memory/Disk Usage tab
        usage_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(usage_frame, text="Memory/Disk Usage")
        
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
        # Remove FocusOut - use click-outside detection instead
        
        # Bind click on main window to close history popup
        self.root.bind("<Button-1>", self._on_root_click)
        
        # Populate drives on tab change
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
    
    def _start_background_indexing(self):
        """Start the background indexer."""
        # Set up callbacks
        self.bg_indexer.set_status_callback(self._on_status_update)
        self.bg_indexer.set_progress_callback(self._on_progress_update)
        
        # Start indexing
        self.bg_indexer.start()
        self.progress.start()
        
        # Update drives info
        drives = self.bg_indexer.get_drives()
        drive_names = [d.name for d in drives if d.drive_type == 'fixed']
        self.drives_var.set(f"Drives: {', '.join(drive_names)}")
        
        # Populate drive combo for treemap
        self._populate_drive_combo()
        
        # Schedule periodic stats update
        self._update_stats()
    
    def _on_status_update(self, message: str):
        """Handle status updates from background indexer."""
        self.root.after(0, lambda: self.status_var.set(message))
    
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
        
        # Schedule new search after 200ms debounce
        self._search_after_id = self.root.after(200, self._do_search)
    
    def _is_regex_pattern(self, query: str) -> bool:
        """Check if query is a regex pattern enclosed in slashes."""
        return query.startswith('/') and query.endswith('/') and len(query) > 2
    
    def _do_search(self):
        """Execute the search and display results."""
        self._search_after_id = None
        
        query = self.search_input.get().strip()
        if not query:
            self._clear_results()
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
        
        self._display_results(results, query)
        self.status_var.set(f"Found {len(results)} results")
        
        # Save to history
        search_type = 'content' if self._content_search_var.get() else 'regex' if self._is_regex_pattern(query) else 'glob' if self.indexer._is_glob_pattern(query) else 'name'
        self.search_history.add_entry(query, len(results), search_type)
    
    def _clear_results(self):
        """Clear all results from the tree."""
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self._item_paths.clear()
    
    def _get_file_icon(self, is_directory: bool, extension: str = "") -> str:
        """Get icon character for file type."""
        if is_directory:
            return "📁"
        
        icon_map = {
            '.py': '🐍', '.go': '🔷', '.js': '📜', '.ts': '📘',
            '.html': '🌐', '.css': '🎨', '.json': '📋', '.md': '📝',
            '.txt': '📄', '.pdf': '📕', '.zip': '🗜️', '.jpg': '🖼️',
            '.png': '🖼️', '.gif': '🖼️', '.mp3': '🎵', '.mp4': '🎬',
            '.exe': '⚙️', '.sh': '💻', '.bat': '💻', '.rs': '🦀',
            '.java': '☕', '.c': '🔧', '.cpp': '🔧', '.h': '📄',
            '.xml': '📋', '.yaml': '📋', '.yml': '📋', '.toml': '📋',
            '.sql': '🗃️', '.db': '🗃️',
        }
        
        return icon_map.get(extension.lower(), '📄')
    
    def _display_results(self, results, query: str):
        """Display search results in the tree with icons."""
        self._clear_results()
        
        for file_info in results:
            icon = self._get_file_icon(file_info.is_directory, file_info.extension)
            
            if file_info.is_directory:
                size_str = "-"
            else:
                size_str = self._format_size(file_info.size)
            
            modified_str = datetime.fromtimestamp(file_info.modified_time).strftime("%Y-%m-%d %H:%M")
            
            tag = "directory" if file_info.is_directory else "file"
            
            item_id = self.results_tree.insert("", tk.END, values=(
                icon,
                file_info.name,
                file_info.parent_dir,
                size_str,
                modified_str
            ), tags=(tag,))
            
            self._item_paths[item_id] = file_info.path
    
    def _format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def _on_double_click(self, event):
        """Open file location when double-clicking a result."""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        full_path = self._item_paths.get(item_id)
        
        if not full_path:
            return
        
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
        if selected_tab == "Memory/Disk Usage":
            self._populate_drive_combo()
    
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
        
        # Create history list
        history_frame = ttk.Frame(self._history_popup, relief="solid", borderwidth=1)
        history_frame.pack(fill=tk.BOTH, expand=True)
        
        entries = self.search_history.get_recent(10)
        if not entries:
            ttk.Label(history_frame, text="No recent searches", foreground="gray").pack(padx=10, pady=10)
        else:
            for entry in entries:
                btn = ttk.Button(
                    history_frame,
                    text=f"{entry.query} ({entry.result_count} results)",
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
    
    def close(self):
        """Clean up resources."""
        self.bg_indexer.stop()
        self.indexer.close()
        self.size_analyzer.stop()
        if self._history_popup and self._history_popup.winfo_exists():
            self._history_popup.destroy()
