# Treemap visualization widget for disk/memory usage
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import random

from core.size_analyzer import SizeNode, format_size


@dataclass
class TreemapRect:
    """Represents a rectangle in the treemap."""
    x: int
    y: int
    width: int
    height: int
    node: SizeNode
    color: str
    depth: int


class TreemapWidget(tk.Canvas):
    """Canvas-based treemap widget for visualizing disk/memory usage."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg='#2a2a2a', highlightthickness=2, highlightbackground='#4a4a4a')
        self._canvas_bg = '#2a2a2a'
        
        self._rects: List[TreemapRect] = []
        self._rect_items: Dict[int, int] = {}  # canvas item id -> rect index
        self._current_node: Optional[SizeNode] = None
        self._root_node: Optional[SizeNode] = None
        self._click_callback = None
        self._hover_callback = None
        
        # WizTree-style color palette - high contrast visible colors
        self._colors = [
            '#FF0000', '#00FF00', '#0000FF', '#FFFF00',
            '#FF00FF', '#00FFFF', '#FF8800', '#8800FF',
            '#00FF88', '#FF0088', '#88FF00', '#0088FF',
        ]
        self._file_colors = [
            '#FF0000', '#FF4444', '#FF8888', '#FFBBBB',
            '#FFFF88', '#88FF88', '#88FFFF', '#8888FF',
        ]
        
        # Helper method for squarified layout
        self._squarify_cache = None
    
    def _squarify(self, children: List[SizeNode], width: int, height: int) -> List[List[SizeNode]]:
        """Squarified treemap algorithm - partition children into rows with optimal aspect ratios."""
        if not children:
            return []
        
        # Sort by size descending for better packing
        children = sorted(children, key=lambda c: c.size, reverse=True)
        
        rows = []
        remaining = list(children)
        total_size = sum(c.size for c in remaining)
        
        if total_size == 0:
            return [[c] for c in children]
        
        while remaining:
            row = []
            row_size = 0
            
            # Determine orientation based on remaining space
            use_width = width >= height
            baseline = width if use_width else height
            perpendicular = height if use_width else width
            
            # Find optimal row using squarified algorithm
            i = 0
            while i < len(remaining):
                child = remaining[i]
                new_row_size = row_size + child.size
                
                if new_row_size == 0:
                    i += 1
                    continue
                
                # Calculate aspect ratio for current row
                if use_width:
                    row_height = new_row_size * perpendicular / total_size
                    worst_ratio = max(
                        (baseline * baseline * row_size) / (row_size * perpendicular * perpendicular) if row_size > 0 else float('inf'),
                        (baseline * baseline * child.size) / (child.size * perpendicular * perpendicular)
                    )
                else:
                    row_width = new_row_size * perpendicular / total_size
                    worst_ratio = max(
                        (baseline * baseline * row_size) / (row_size * perpendicular * perpendicular) if row_size > 0 else float('inf'),
                        (baseline * baseline * child.size) / (child.size * perpendicular * perpendicular)
                    )
                
                # Stop if adding this child worsens the aspect ratio
                if row and worst_ratio > 2.0:
                    break
                
                row.append(child)
                row_size += child.size
                i += 1
            
            if row:
                rows.append(row)
                remaining = remaining[i:]
            else:
                # Fallback: take one child
                rows.append([remaining[0]])
                remaining = remaining[1:]
        
        return rows
        
        # Bind events
        self.bind('<Button-1>', self._on_click)
        self.bind('<Motion>', self._on_hover)
        self.bind('<Leave>', self._on_leave)
        
        # Tooltip
        self._tooltip = None
        
    def set_click_callback(self, callback):
        """Set callback for node selection: callback(node)"""
        self._click_callback = callback
        
    def set_hover_callback(self, callback):
        """Set callback for hover: callback(node, x, y)"""
        self._hover_callback = callback
    
    def load_node(self, node: SizeNode):
        """Load a size node and render the treemap."""
        self._root_node = node
        self._current_node = node
        self._render_treemap()
    
    def drill_down(self, node: SizeNode):
        """Drill down into a child node."""
        if node and node.is_directory and node.children:
            self._current_node = node
            self._render_treemap()
    
    def drill_up(self):
        """Go up one level in the hierarchy."""
        if self._current_node and self._current_node.parent:
            self._current_node = self._current_node.parent
            self._render_treemap()
    
    def _render_treemap(self):
        """Render the treemap visualization."""
        self.delete('all')
        self._rects.clear()
        self._rect_items.clear()
        
        if not self._current_node:
            return
        
        # Force layout update to get actual widget size
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        
        # Ensure minimum size for rendering - force adequate canvas size
        if width < 300 or height < 200:
            width = 800
            height = 500
        
        # Debug: print canvas size
        print(f"Treemap canvas size: {width}x{height}")
        
        # Calculate treemap layout
        self._calculate_treemap(self._current_node, 0, 0, width, height, 0)
        
        # Force canvas redraw and bring to front
        self.update()
        self.tag_raise('all')
        
        # Draw rectangles
        for i, rect in enumerate(self._rects):
            item = self.create_rectangle(
                rect.x, rect.y,
                rect.x + rect.width,
                rect.y + rect.height,
                fill=rect.color,
                outline='#000000',
                width=1
            )
            print(f"Drew rect: {rect.node.name} at ({rect.x},{rect.y}) {rect.width}x{rect.height} color={rect.color}")
            self._rect_items[i] = item
            
            # Add text label for any visible rectangle
            if rect.width > 25 and rect.height > 15:
                label = rect.node.name
                if len(label) > 18:
                    label = label[:15] + '...'
                # Detect brightness from hex color to choose text color
                hex_color = rect.color.lstrip('#')
                r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                text_color = '#000000' if brightness > 150 else '#ffffff'
                self.create_text(
                    rect.x + 4,
                    rect.y + 4,
                    text=label,
                    fill=text_color,
                    anchor='nw',
                    font=('Segoe UI', 9, 'bold'),
                    tags='label'
                )
                
                # Size label
                if rect.height > 35:
                    size_text = format_size(rect.node.size)
                    self.create_text(
                        rect.x + 4,
                        rect.y + 20,
                        text=size_text,
                        fill=text_color,
                        anchor='nw',
                        font=('Segoe UI', 8),
                        tags='size'
                    )
    
    def _squarify(self, children: List[SizeNode], width: int, height: int) -> List[List[SizeNode]]:
        """Simple squarify algorithm - partition children into rows."""
        if not children:
            return []
        
        rows = []
        current_row = []
        row_size = 0
        
        for child in children:
            current_row.append(child)
            row_size += child.size
            
            # Check if adding more children would worsen aspect ratio
            if len(current_row) > 1:
                prev_aspect = self._row_aspect_ratio(current_row[:-1], width, height)
                curr_aspect = self._row_aspect_ratio(current_row, width, height)
                if curr_aspect > prev_aspect and prev_aspect > 0:
                    rows.append(current_row[:-1])
                    current_row = [child]
                    row_size = child.size
        
        if current_row:
            rows.append(current_row)
        
        return rows
    
    def _row_aspect_ratio(self, row: List[SizeNode], width: int, height: int) -> float:
        """Calculate aspect ratio for a row."""
        if not row:
            return 0
        total_size = sum(c.size for c in row)
        if total_size == 0:
            return 0
        min_size = min(c.size for c in row)
        max_size = max(c.size for c in row)
        return (max_size * len(row) ** 2) / (total_size ** 2) if total_size > 0 else 0
    
    def _calculate_treemap(self, node: SizeNode, x: int, y: int, width: int, height: int, depth: int):
        """Recursively calculate treemap layout using squarified algorithm."""
        if not node or width < 10 or height < 10:
            return
        
        # For leaf nodes or nodes without children, draw the node itself
        if not node.children:
            rect = TreemapRect(
                x=x,
                y=y,
                width=width,
                height=height,
                node=node,
                color=self._get_color(node, depth),
                depth=depth
            )
            self._rects.append(rect)
            return
        
        # Sort children by size (largest first)
        children = sorted(node.children, key=lambda c: c.size, reverse=True)
        
        if not children:
            # No children - draw this node as a leaf
            rect = TreemapRect(
                x=x,
                y=y,
                width=width,
                height=height,
                node=node,
                color=self._get_color(node, depth),
                depth=depth
            )
            self._rects.append(rect)
            return
        
        total_size = sum(c.size for c in children)
        if total_size == 0:
            return
        
        # Squarified treemap: partition children into rows
        rows = self._squarify(children, width, height)
        
        # Layout each row and recurse into children
        current_x, current_y = x, y
        remaining_w, remaining_h = width, height
        
        for row in rows:
            row_size = sum(c.size for c in row)
            
            # Skip rows with zero size to avoid division by zero
            if row_size == 0 or total_size == 0:
                continue
            
            # Determine row orientation based on remaining space
            if remaining_w >= remaining_h:
                # Horizontal layout - rows stack vertically
                row_height = int(remaining_h * row_size / total_size)
                row_width = remaining_w
                
                # Layout items in this row horizontally
                row_x = current_x
                for child in row:
                    child_width = int(row_width * child.size / row_size)
                    rect = TreemapRect(
                        x=row_x,
                        y=current_y,
                        width=child_width,
                        height=row_height,
                        node=child,
                        color=self._get_color(child, depth),
                        depth=depth
                    )
                    self._rects.append(rect)
                    
                    # Recurse into directory children
                    if child.is_directory and child.children and child_width > 30 and row_height > 30:
                        self._calculate_treemap(
                            child,
                            row_x + 1,
                            current_y + 1,
                            child_width - 2,
                            row_height - 2,
                            depth + 1
                        )
                    
                    row_x += child_width
                
                current_y += row_height
                remaining_h -= row_height
            else:
                # Vertical layout - rows stack horizontally
                row_width = int(remaining_w * row_size / total_size)
                row_height = remaining_h
                
                # Layout items in this row vertically
                row_y = current_y
                for child in row:
                    child_height = int(row_height * child.size / row_size)
                    rect = TreemapRect(
                        x=current_x,
                        y=row_y,
                        width=row_width,
                        height=child_height,
                        node=child,
                        color=self._get_color(child, depth),
                        depth=depth
                    )
                    self._rects.append(rect)
                    
                    # Recurse into directory children
                    if child.is_directory and child.children and row_width > 30 and child_height > 30:
                        self._calculate_treemap(
                            child,
                            current_x + 1,
                            row_y + 1,
                            row_width - 2,
                            child_height - 2,
                            depth + 1
                        )
                    
                    row_y += child_height
                
                current_x += row_width
                remaining_w -= row_width
    
    def _get_color(self, node: SizeNode, depth: int) -> str:
        """Get color for a node based on depth and type - WizTree style."""
        if node.is_directory:
            # Directories use depth-based color from main palette
            return self._colors[depth % len(self._colors)]
        else:
            # Files use heat-map style based on relative size
            if node.parent and node.parent.size > 0:
                size_ratio = node.size / node.parent.size
                # Map size ratio to color index (larger files = warmer colors)
                color_idx = min(int(size_ratio * len(self._file_colors)), len(self._file_colors) - 1)
                return self._file_colors[color_idx]
            return self._file_colors[0]
    
    def _on_click(self, event):
        """Handle click event for drill-down navigation."""
        rect = self._find_rect_at(event.x, event.y)
        if rect and self._click_callback:
            if rect.node.is_directory and rect.node.children:
                self._click_callback(rect.node)
    
    def _on_hover(self, event):
        """Handle hover event for tooltip."""
        rect = self._find_rect_at(event.x, event.y)
        if rect:
            self._show_tooltip(rect, event.x, event.y)
            if self._hover_callback:
                self._hover_callback(rect.node, event.x, event.y)
    
    def _on_leave(self, event):
        """Hide tooltip on leave."""
        self._hide_tooltip()
    
    def _find_rect_at(self, x: int, y: int) -> Optional[TreemapRect]:
        """Find the rectangle at given coordinates."""
        for rect in self._rects:
            if (rect.x <= x <= rect.x + rect.width and
                rect.y <= y <= rect.y + rect.height):
                return rect
        return None
    
    def _show_tooltip(self, rect: TreemapRect, x: int, y: int):
        """Show tooltip with node information."""
        self._hide_tooltip()
        
        tooltip_text = f"{rect.node.name}\n"
        tooltip_text += f"Size: {format_size(rect.node.size)}\n"
        if rect.node.is_directory:
            tooltip_text += f"Files: {rect.node.file_count}\n"
            tooltip_text += f"Dirs: {rect.node.dir_count}\n"
        tooltip_text += f"Path: {rect.node.path}"
        
        self._tooltip = tk.Toplevel(self)
        self._tooltip.configure(bg='#333333', fg='white')
        self._tooltip.overrideredirect(True)
        
        label = tk.Label(
            self._tooltip,
            text=tooltip_text,
            bg='#333333',
            fg='white',
            justify='left',
            padx=8,
            pady=4,
            font=('Segoe UI', 9)
        )
        label.pack()
        
        # Position tooltip near cursor
        self.update_idletasks()
        tooltip_x = self.winfo_rootx() + x + 10
        tooltip_y = self.winfo_rooty() + y + 10
        self._tooltip.geometry(f'+{tooltip_x}+{tooltip_y}')
    
    def _hide_tooltip(self):
        """Hide the tooltip."""
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None
    
    def get_current_path(self) -> Optional[str]:
        """Get the current displayed path."""
        if self._current_node:
            return self._current_node.path
        return None


class TreemapPanel(ttk.Frame):
    """Panel containing the treemap widget with navigation controls."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        # Navigation toolbar
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.back_btn = ttk.Button(nav_frame, text='◀ Up', command=self._go_up, state=tk.DISABLED)
        self.back_btn.pack(side=tk.LEFT)
        
        self.path_var = tk.StringVar(value='Select a drive...')
        self.path_label = ttk.Label(nav_frame, textvariable=self.path_var)
        self.path_label.pack(side=tk.LEFT, padx=10)
        
        # Treemap canvas
        self.treemap = TreemapWidget(self, width=800, height=400)
        self.treemap.pack(fill=tk.BOTH, expand=True)
        
        # Stats bar
        stats_frame = ttk.Frame(self)
        stats_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.size_var = tk.StringVar(value='Total: -')
        ttk.Label(stats_frame, textvariable=self.size_var, foreground='gray').pack(side=tk.LEFT)
        
        self.treemap.set_click_callback(self._on_node_click)
    
    def _go_up(self):
        """Navigate up one level."""
        self.treemap.drill_up()
        self._update_nav()
    
    def _on_node_click(self, node: SizeNode):
        """Handle node click for drill-down."""
        if node.is_directory:
            self.treemap.drill_down(node)
            self._update_nav()
    
    def _update_nav(self):
        """Update navigation controls."""
        if self.treemap._current_node:
            self.path_var.set(self.treemap._current_node.path)
            self.back_btn.configure(state=tk.NORMAL if self.treemap._current_node.parent else tk.DISABLED)
    
    def load_drive(self, path: str, root_node: SizeNode):
        """Load a drive for visualization."""
        self.treemap.load_node(root_node)
        self._update_nav()
        self.size_var.set(f"Total: {format_size(root_node.size)}")
