# Memory graph widget for WizTree-style file tree with size bars
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Dict
from dataclasses import dataclass

from ..core.size_analyzer import SizeNode, format_size


@dataclass
class TreeItem:
    """Represents a row in the memory graph tree."""
    node: SizeNode
    depth: int
    size_percent: float
    row_index: int


class MemoryGraphWidget(ttk.Frame):
    """WizTree-style memory graph with tree view and size bars."""
    
    # Dark theme colors
    _BG_COLOR = '#1a1a2e'
    _TREE_BG = '#16213e'
    _TEXT_COLOR = '#eaeaea'
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style='Dark.TFrame')
        
        # Treeview with columns for name, size, percent, and graph
        columns = ("name", "size", "percent", "files", "type", "graph")
        self.tree = ttk.Treeview(self, columns=columns, show="tree headings", selectmode="browse")
        
        # Configure headings
        self.tree.heading("#0", text="Name")
        self.tree.heading("name", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.heading("percent", text="%")
        self.tree.heading("files", text="Files")
        self.tree.heading("type", text="Type")
        self.tree.heading("graph", text="Size Bar")
        
        # Configure column widths
        self.tree.column("#0", width=250, minwidth=150)
        self.tree.column("name", width=0, stretch=False)
        self.tree.column("size", width=100, minwidth=80)
        self.tree.column("percent", width=60, minwidth=50)
        self.tree.column("files", width=70, minwidth=60)
        self.tree.column("type", width=80, minwidth=70)
        self.tree.column("graph", width=200, minwidth=150)
        
        # Scrollbars
        vscroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        hscroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Store node mapping
        self._node_map: Dict[str, SizeNode] = {}
        self._root_node: Optional[SizeNode] = None
        self._total_size: int = 0
        self._click_callback = None
        
        # Color palette for size bars (WizTree-style gradient)
        self._bar_colors = [
            '#e94560', '#0f3460', '#533483', '#16213e',
            '#e94560', '#ff6b6b', '#ffd93d', '#6bcb77',
        ]
        
        # Bind double-click for drill-down
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        
        # Style tags - dark theme friendly
        self.tree.tag_configure("directory", foreground="#48dbfb")
        self.tree.tag_configure("file", foreground="#eaeaea")
        self.tree.tag_configure("large", font=('Segoe UI', 9, 'bold'))
        self.tree.tag_configure("very_large", foreground='#e94560')
        
        # Configure ttk style for dark theme (ttk widgets require styles, not direct configure)
        style = ttk.Style()
        style.configure('Dark.Treeview', background=self._TREE_BG, foreground=self._TEXT_COLOR, fieldbackground=self._TREE_BG)
        style.configure('Dark.Treeview.Heading', background=self._TREE_BG, foreground=self._TEXT_COLOR)
        self.tree.configure(style='Dark.Treeview')
    
    def set_click_callback(self, callback):
        """Set callback for node selection: callback(node)"""
        self._click_callback = callback
    
    def load_node(self, root_node: SizeNode):
        """Load a size node and render the memory graph."""
        self._root_node = root_node
        self._total_size = root_node.size
        self._node_map.clear()
        self._populate_tree(root_node, "")
    
    def _get_bar_color(self, node: SizeNode, percent: float) -> str:
        """Get color for size bar based on percentage and type."""
        if percent > 10:
            return '#e94560'
        elif percent > 5:
            return '#ff6b6b'
        elif percent > 1:
            return '#ffd93d'
        elif node.is_directory:
            return '#48dbfb'
        else:
            return '#6bcb77'
    
    def _create_size_bar(self, percent: float, color: str) -> str:
        """Create a text-based size bar visualization."""
        bar_width = 30
        filled = int(bar_width * percent / 100)
        if filled == 0 and percent > 0:
            filled = 1
        empty = bar_width - filled
        bar = '█' * filled + '░' * empty
        return bar
    
    def _populate_tree(self, node: SizeNode, parent_iid: str):
        """Recursively populate the tree view."""
        if self._total_size > 0:
            percent = (node.size / self._total_size) * 100
        else:
            percent = 0.0
        
        if node.is_directory:
            icon = "📁"
            tags = ("directory",)
            if percent > 10:
                tags = tags + ("very_large",)
            elif percent > 5:
                tags = tags + ("large",)
            file_count = f"{node.file_count:,}"
            node_type = "Folder"
        else:
            icon = "📄"
            tags = ("file",)
            if percent > 5:
                tags = tags + ("large",)
            file_count = "1"
            node_type = node.name.split('.')[-1].upper() if '.' in node.name else "File"
        
        bar_color = self._get_bar_color(node, percent)
        size_bar = self._create_size_bar(percent, bar_color)
        
        iid = self.tree.insert(
            parent_iid, tk.END,
            text=f"{icon} {node.name}",
            values=(node.name, format_size(node.size), f"{percent:.1f}%",
                    file_count, node_type, size_bar),
            tags=tags
        )
        
        self._node_map[iid] = node
        
        if node.is_directory and node.children:
            sorted_children = sorted(node.children, key=lambda c: c.size, reverse=True)
            for child in sorted_children[:100]:
                self._populate_tree(child, iid)
    
    def _on_double_click(self, event):
        """Handle double-click for drill-down navigation."""
        selection = self.tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        node = self._node_map.get(item_id)
        
        if node and node.is_directory and node.children:
            if self.tree.item(item_id, "open"):
                self.tree.item(item_id, open=False)
            else:
                self.tree.item(item_id, open=True)
            
            if self._click_callback:
                self._click_callback(node)
    
    def _on_select(self, event):
        """Handle selection change."""
        selection = self.tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        node = self._node_map.get(item_id)
        
        if node and self._click_callback:
            self._click_callback(node)
    
    def get_selected_node(self) -> Optional[SizeNode]:
        """Get the currently selected node."""
        selection = self.tree.selection()
        if not selection:
            return None
        return self._node_map.get(selection[0])
    
    def clear(self):
        """Clear all items from the tree."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._node_map.clear()
        self._root_node = None
        self._total_size = 0


class MemoryGraphPanel(ttk.Frame):
    """Panel containing the memory graph widget with navigation and stats."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style='Dark.TFrame')
        
        # Top toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        self.back_btn = ttk.Button(toolbar, text='◀ Up', command=self._go_up, state=tk.DISABLED)
        self.back_btn.pack(side=tk.LEFT)
        
        self.path_var = tk.StringVar(value='Select a drive...')
        self.path_label = ttk.Label(toolbar, textvariable=self.path_var, font=('Segoe UI', 10))
        self.path_label.pack(side=tk.LEFT, padx=10)
        
        # Expand/collapse buttons
        ttk.Button(toolbar, text='Expand All', command=self._expand_all, width=10).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(toolbar, text='Collapse All', command=self._collapse_all, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        # Search filter for memory graph
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(toolbar, textvariable=self.filter_var, width=20)
        self.filter_entry.pack(side=tk.RIGHT, padx=(5, 5))
        self.filter_entry.bind("<KeyRelease>", self._on_filter)
        ttk.Label(toolbar, text="Filter:", font=('Segoe UI', 9)).pack(side=tk.RIGHT)
        
        self.refresh_btn = ttk.Button(toolbar, text='⟳', command=self._refresh, width=3)
        self.refresh_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Memory graph widget
        self.graph = MemoryGraphWidget(self)
        self.graph.pack(fill=tk.BOTH, expand=True)
        
        # Bottom stats bar
        stats_bar = ttk.Frame(self)
        stats_bar.pack(fill=tk.X, pady=(5, 0))
        
        self.total_var = tk.StringVar(value='Total: -')
        ttk.Label(stats_bar, textvariable=self.total_var, foreground='gray').pack(side=tk.LEFT)
        
        self.selected_var = tk.StringVar(value='Selected: -')
        ttk.Label(stats_bar, textvariable=self.selected_var, foreground='gray').pack(side=tk.RIGHT)
        
        self.graph.set_click_callback(self._on_node_select)
        
        # Navigation stack
        self._nav_stack: List[SizeNode] = []
    
    def _go_up(self):
        """Navigate up one level."""
        if len(self._nav_stack) > 1:
            self._nav_stack.pop()
            prev_node = self._nav_stack[-1]
            self.graph.load_node(prev_node)
            self._update_nav()
    
    def _expand_all(self):
        """Expand all items in the tree."""
        for item in self.graph.tree.get_children():
            self._expand_recursive(item)
    
    def _expand_recursive(self, item):
        """Expand an item and all its children."""
        self.graph.tree.item(item, open=True)
        for child in self.graph.tree.get_children(item):
            self._expand_recursive(child)
    
    def _collapse_all(self):
        """Collapse all items in the tree."""
        for item in self.graph.tree.get_children():
            self._collapse_recursive(item)
    
    def _collapse_recursive(self, item):
        """Collapse an item and all its children."""
        self.graph.tree.item(item, open=False)
        for child in self.graph.tree.get_children(item):
            self._collapse_recursive(child)
    
    def _on_filter(self, event=None):
        """Filter the tree view based on the filter text."""
        query = self.filter_var.get().lower()
        if not query:
            # Collapse all back to root level
            for item in self.graph.tree.get_children():
                self._collapse_recursive(item)
            self.selected_var.set('Selected: -')
            return
        
        match_count = 0
        first_match = None
        # Expand and show matching items
        for item_id, node in self.graph._node_map.items():
            if query in node.name.lower():
                match_count += 1
                if first_match is None:
                    first_match = item_id
                # Ensure parents are visible
                parent = self.graph.tree.parent(item_id)
                while parent:
                    self.graph.tree.item(parent, open=True)
                    parent = self.graph.tree.parent(parent)
        
        if first_match:
            self.graph.tree.selection_set(first_match)
            self.graph.tree.see(first_match)
            self.selected_var.set(f"Found {match_count} matches for '{self.filter_var.get()}'")
        else:
            self.selected_var.set(f"No matches for '{self.filter_var.get()}'")
    
    def _refresh(self):
        """Refresh the current view."""
        if self._nav_stack:
            current = self._nav_stack[-1]
            self.graph.load_node(current)
    
    def _on_node_select(self, node: SizeNode):
        """Handle node selection."""
        if node:
            self.selected_var.set(f"Selected: {node.name} - {format_size(node.size)}")
            
            if node.is_directory and node.children:
                for iid, stored_node in self.graph._node_map.items():
                    if stored_node is node:
                        self.graph.tree.item(iid, open=True)
                        break
    
    def _update_nav(self):
        """Update navigation controls."""
        if self._nav_stack:
            current = self._nav_stack[-1]
            self.path_var.set(current.path)
            self.total_var.set(f"Total: {format_size(current.size)}")
            self.back_btn.configure(state=tk.NORMAL if len(self._nav_stack) > 1 else tk.DISABLED)
    
    def load_drive(self, path: str, root_node: SizeNode):
        """Load a drive for visualization."""
        self._nav_stack = [root_node]
        self.graph.load_node(root_node)
        self._update_nav()
        self.selected_var.set('Selected: -')
