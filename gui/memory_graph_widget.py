# Memory graph widget for WizTree-style file tree with size bars
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Dict
from dataclasses import dataclass

from core.size_analyzer import SizeNode, format_size


@dataclass
class TreeItem:
    """Represents a row in the memory graph tree."""
    node: SizeNode
    depth: int
    size_percent: float
    row_index: int


class MemoryGraphWidget(ttk.Frame):
    """WizTree-style memory graph with tree view and size bars."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
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
        self.tree.column("name", width=0, stretch=False)  # Hidden, use #0 instead
        self.tree.column("size", width=100, minwidth=80)
        self.tree.column("percent", width=60, minwidth=50)
        self.tree.column("files", width=70, minwidth=60)
        self.tree.column("type", width=80, minwidth=70)
        self.tree.column("graph", width=200, minwidth=150)
        
        # Scrollbars
        vspinner = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        hspinner = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vspinner.set, xscrollcommand=hspinner.set)
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        vspinner.grid(row=0, column=1, sticky="ns")
        hspinner.grid(row=1, column=0, sticky="ew")
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Store node mapping
        self._node_map: Dict[str, SizeNode] = {}
        self._root_node: Optional[SizeNode] = None
        self._total_size: int = 0
        self._click_callback = None
        
        # Color palette for size bars (WizTree-style gradient)
        self._bar_colors = [
            '#2d5a87', '#3d7a97', '#4d9aa7', '#5dbab7',
            '#6ddac7', '#7dfad7', '#8dfae7', '#9dfaf7',
            '#e74c3c', '#e67e22', '#f1c40f', '#2ecc71'
        ]
        
        # Bind double-click for drill-down
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        
        # Style tags
        self.tree.tag_configure("directory", foreground="#008080")
        self.tree.tag_configure("file", foreground="#333333")
        self.tree.tag_configure("large", font=('Segoe UI', 9, 'bold'))
        self.tree.tag_configure("very_large", foreground='#e74c3c')
    
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
            return '#e74c3c'  # Red for very large
        elif percent > 5:
            return '#e67e22'  # Orange for large
        elif percent > 1:
            return '#f1c40f'  # Yellow for medium
        elif node.is_directory:
            return '#3498db'  # Blue for directories
        else:
            return '#2ecc71'  # Green for files
    
    def _create_size_bar(self, percent: float, color: str) -> str:
        """Create a text-based size bar visualization."""
        bar_width = 30
        filled = int(bar_width * percent / 100)
        if filled == 0 and percent > 0:
            filled = 1
        empty = bar_width - filled
        # Use block characters for visual bar
        bar = '█' * filled + '░' * empty
        return bar
    
    def _populate_tree(self, node: SizeNode, parent_iid: str):
        """Recursively populate the tree view."""
        # Calculate percentage
        if self._total_size > 0:
            percent = (node.size / self._total_size) * 100
        else:
            percent = 0.0
        
        # Determine icon and tags
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
        
        # Get bar color and create size bar visualization
        bar_color = self._get_bar_color(node, percent)
        size_bar = self._create_size_bar(percent, bar_color)
        
        # Insert item
        iid = self.tree.insert(
            parent_iid,
            tk.END,
            text=f"{icon} {node.name}",
            values=(
                node.name,
                format_size(node.size),
                f"{percent:.1f}%",
                file_count,
                node_type,
                size_bar
            ),
            tags=tags
        )
        
        # Store node mapping
        self._node_map[iid] = node
        
        # Recurse into children (sorted by size, largest first)
        if node.is_directory and node.children:
            sorted_children = sorted(node.children, key=lambda c: c.size, reverse=True)
            # Only expand top 100 children to avoid UI lag
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
            # Toggle expand/collapse
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
        
        # Top toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        self.back_btn = ttk.Button(toolbar, text='◀ Up', command=self._go_up, state=tk.DISABLED)
        self.back_btn.pack(side=tk.LEFT)
        
        self.path_var = tk.StringVar(value='Select a drive...')
        self.path_label = ttk.Label(toolbar, textvariable=self.path_var, font=('Segoe UI', 10))
        self.path_label.pack(side=tk.LEFT, padx=10)
        
        self.refresh_btn = ttk.Button(toolbar, text='⟳', command=self._refresh, width=3)
        self.refresh_btn.pack(side=tk.RIGHT)
        
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
    
    def _refresh(self):
        """Refresh the current view."""
        if self._nav_stack:
            current = self._nav_stack[-1]
            self.graph.load_node(current)
    
    def _on_node_select(self, node: SizeNode):
        """Handle node selection."""
        if node:
            self.selected_var.set(f"Selected: {node.name} - {format_size(node.size)}")
            
            # Auto-expand large directories on double-click
            if node.is_directory and node.children:
                # Find the item in tree and expand it
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
