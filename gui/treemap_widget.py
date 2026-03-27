# Treemap visualization widget for disk/memory usage
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

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
    """Canvas-based treemap widget for visualizing disk/memory usage with zoom support."""
    
    # Dark theme color palette
    _BG_COLOR = '#1a1a2e'
    _HIGHLIGHT_COLOR = '#16213e'
    _BORDER_COLOR = '#0f3460'
    
    # WizTree-style color palette - high contrast visible colors
    _COLORS = [
        '#e94560', '#0f3460', '#533483', '#e94560',
        '#16213e', '#0f3460', '#533483', '#e94560',
        '#16213e', '#0f3460', '#533483', '#e94560',
    ]
    _FILE_COLORS = [
        '#e94560', '#ff6b6b', '#ff8888', '#ffaaaa',
        '#ffd93d', '#6bcb77', '#48dbfb', '#5f27cd',
    ]
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg=self._BG_COLOR, highlightthickness=2, highlightbackground=self._BORDER_COLOR)
        
        self._rects: List[TreemapRect] = []
        self._rect_items: Dict[int, int] = {}
        self._current_node: Optional[SizeNode] = None
        self._root_node: Optional[SizeNode] = None
        self._click_callback = None
        self._hover_callback = None
        self._tooltip = None
        
        # Zoom/upscale support
        self._zoom_level = 1.0
        self._zoom_min = 0.5
        self._zoom_max = 4.0
        self._pan_offset_x = 0
        self._pan_offset_y = 0
        self._is_dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        
        # Bind events
        self.bind('<Button-1>', self._on_click)
        self.bind('<Motion>', self._on_hover)
        self.bind('<Leave>', self._on_leave)
        self.bind('<MouseWheel>', self._on_mouse_wheel)
        self.bind('<Button-4>', self._on_mouse_wheel)  # Linux scroll up
        self.bind('<Button-5>', self._on_mouse_wheel)  # Linux scroll down
        self.bind('<ButtonPress-3>', self._on_right_press)
        self.bind('<B3-Motion>', self._on_right_drag)
        self.bind('<ButtonRelease-3>', self._on_right_release)
        self.bind('<Configure>', self._on_resize)
    
    def _squarify(self, children: List[SizeNode], width: int, height: int) -> List[List[SizeNode]]:
        """Squarified treemap algorithm - partition children into rows with optimal aspect ratios."""
        if not children:
            return []
        
        children = sorted(children, key=lambda c: c.size, reverse=True)
        
        rows = []
        remaining = list(children)
        total_size = sum(c.size for c in remaining)
        
        if total_size == 0:
            return [[c] for c in children]
        
        while remaining:
            row = []
            row_size = 0
            use_width = width >= height
            baseline = width if use_width else height
            perpendicular = height if use_width else width
            
            i = 0
            while i < len(remaining):
                child = remaining[i]
                new_row_size = row_size + child.size
                
                if new_row_size == 0:
                    i += 1
                    continue
                
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
                
                if row and worst_ratio > 2.0:
                    break
                
                row.append(child)
                row_size += child.size
                i += 1
            
            if row:
                rows.append(row)
                remaining = remaining[i:]
            else:
                rows.append([remaining[0]])
                remaining = remaining[1:]
        
        return rows
    
    def set_click_callback(self, callback):
        self._click_callback = callback
        
    def set_hover_callback(self, callback):
        self._hover_callback = callback
    
    def load_node(self, node: SizeNode):
        self._root_node = node
        self._current_node = node
        self._render_treemap()
    
    def drill_down(self, node: SizeNode):
        if node and node.is_directory and node.children:
            self._current_node = node
            self._render_treemap()
    
    def drill_up(self):
        if self._current_node and self._current_node.parent:
            self._current_node = self._current_node.parent
            self._render_treemap()
    
    def _render_treemap(self):
        self.delete('all')
        self._rects.clear()
        self._rect_items.clear()
        
        if not self._current_node:
            return
        
        self.update_idletasks()
        base_width = self.winfo_width()
        base_height = self.winfo_height()
        
        if base_width < 300 or base_height < 200:
            base_width = 800
            base_height = 500
        
        # Apply zoom scaling
        width = int(base_width * self._zoom_level)
        height = int(base_height * self._zoom_level)
        
        # Apply pan offset
        start_x = self._pan_offset_x
        start_y = self._pan_offset_y
        
        self._calculate_treemap(self._current_node, start_x, start_y, width, height, 0)
        
        for i, rect in enumerate(self._rects):
            item = self.create_rectangle(
                rect.x, rect.y,
                rect.x + rect.width,
                rect.y + rect.height,
                fill=rect.color,
                outline=self._BG_COLOR,
                width=1
            )
            self._rect_items[i] = item
            
            if rect.width > 25 and rect.height > 15:
                label = rect.node.name
                if len(label) > 18:
                    label = label[:15] + '...'
                hex_color = rect.color.lstrip('#')
                r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                text_color = '#1a1a2e' if brightness > 150 else '#ffffff'
                self.create_text(
                    rect.x + 4, rect.y + 4,
                    text=label, fill=text_color,
                    anchor='nw', font=('Segoe UI', 9, 'bold'), tags='label'
                )
                
                if rect.height > 35:
                    size_text = format_size(rect.node.size)
                    self.create_text(
                        rect.x + 4, rect.y + 20,
                        text=size_text, fill=text_color,
                        anchor='nw', font=('Segoe UI', 8), tags='size'
                    )
    
    def _calculate_treemap(self, node: SizeNode, x: int, y: int, width: int, height: int, depth: int):
        if not node or width < 10 or height < 10:
            return
        
        if not node.children:
            rect = TreemapRect(x=x, y=y, width=width, height=height, node=node,
                              color=self._get_color(node, depth), depth=depth)
            self._rects.append(rect)
            return
        
        children = sorted(node.children, key=lambda c: c.size, reverse=True)
        
        if not children:
            rect = TreemapRect(x=x, y=y, width=width, height=height, node=node,
                              color=self._get_color(node, depth), depth=depth)
            self._rects.append(rect)
            return
        
        total_size = sum(c.size for c in children)
        if total_size == 0:
            return
        
        rows = self._squarify(children, width, height)
        current_x, current_y = x, y
        remaining_w, remaining_h = width, height
        
        for row in rows:
            row_size = sum(c.size for c in row)
            if row_size == 0 or total_size == 0:
                continue
            
            if remaining_w >= remaining_h:
                row_height = int(remaining_h * row_size / total_size)
                row_width = remaining_w
                row_x = current_x
                for child in row:
                    child_width = int(row_width * child.size / row_size)
                    rect = TreemapRect(x=row_x, y=current_y, width=child_width, height=row_height,
                                      node=child, color=self._get_color(child, depth), depth=depth)
                    self._rects.append(rect)
                    
                    if child.is_directory and child.children and child_width > 30 and row_height > 30:
                        self._calculate_treemap(child, row_x + 1, current_y + 1,
                                               child_width - 2, row_height - 2, depth + 1)
                    row_x += child_width
                current_y += row_height
                remaining_h -= row_height
            else:
                row_width = int(remaining_w * row_size / total_size)
                row_height = remaining_h
                row_y = current_y
                for child in row:
                    child_height = int(row_height * child.size / row_size)
                    rect = TreemapRect(x=current_x, y=row_y, width=row_width, height=child_height,
                                      node=child, color=self._get_color(child, depth), depth=depth)
                    self._rects.append(rect)
                    
                    if child.is_directory and child.children and row_width > 30 and child_height > 30:
                        self._calculate_treemap(child, current_x + 1, row_y + 1,
                                               row_width - 2, child_height - 2, depth + 1)
                    row_y += child_height
                current_x += row_width
                remaining_w -= row_width
    
    def _get_color(self, node: SizeNode, depth: int) -> str:
        if node.is_directory:
            return self._COLORS[depth % len(self._COLORS)]
        else:
            if node.parent and node.parent.size > 0:
                size_ratio = node.size / node.parent.size
                color_idx = min(int(size_ratio * len(self._FILE_COLORS)), len(self._FILE_COLORS) - 1)
                return self._FILE_COLORS[color_idx]
            return self._FILE_COLORS[0]
    
    def _on_click(self, event):
        rect = self._find_rect_at(event.x, event.y)
        if rect and self._click_callback:
            if rect.node.is_directory and rect.node.children:
                self._click_callback(rect.node)
    
    def _on_hover(self, event):
        rect = self._find_rect_at(event.x, event.y)
        if rect:
            self._show_tooltip(rect, event.x, event.y)
            if self._hover_callback:
                self._hover_callback(rect.node, event.x, event.y)
    
    def _on_leave(self, event):
        self._hide_tooltip()
    
    def _find_rect_at(self, x: int, y: int) -> Optional[TreemapRect]:
        for rect in self._rects:
            if rect.x <= x <= rect.x + rect.width and rect.y <= y <= rect.y + rect.height:
                return rect
        return None
    
    def _show_tooltip(self, rect: TreemapRect, x: int, y: int):
        self._hide_tooltip()
        tooltip_text = f"{rect.node.name}\nSize: {format_size(rect.node.size)}\n"
        if rect.node.is_directory:
            tooltip_text += f"Files: {rect.node.file_count}\nDirs: {rect.node.dir_count}\n"
        tooltip_text += f"Path: {rect.node.path}"
        
        self._tooltip = tk.Toplevel(self)
        self._tooltip.configure(bg=self._HIGHLIGHT_COLOR, fg='white')
        self._tooltip.overrideredirect(True)
        
        label = tk.Label(self._tooltip, text=tooltip_text, bg=self._HIGHLIGHT_COLOR,
                        fg='white', justify='left', padx=8, pady=4, font=('Segoe UI', 9))
        label.pack()
        
        self.update_idletasks()
        tooltip_x = self.winfo_rootx() + x + 10
        tooltip_y = self.winfo_rooty() + y + 10
        self._tooltip.geometry(f'+{tooltip_x}+{tooltip_y}')
    
    def _hide_tooltip(self):
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None
    
    def _on_mouse_wheel(self, event):
        """Handle mouse wheel for zooming."""
        if event.num == 4 or event.delta > 0:
            self.zoom_in()
        elif event.num == 5 or event.delta < 0:
            self.zoom_out()
    
    def _on_right_press(self, event):
        """Start panning with right mouse button."""
        self._is_dragging = True
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self.configure(cursor='fleur')
    
    def _on_right_drag(self, event):
        """Pan the treemap view."""
        if self._is_dragging:
            dx = event.x - self._drag_start_x
            dy = event.y - self._drag_start_y
            self._pan_offset_x += dx
            self._pan_offset_y += dy
            self._drag_start_x = event.x
            self._drag_start_y = event.y
            self._render_treemap()
    
    def _on_right_release(self, event):
        """Stop panning."""
        self._is_dragging = False
        self.configure(cursor='')
    
    def _on_resize(self, event):
        """Handle window resize - reset pan on significant size changes."""
        if event.width > 0 and event.height > 0:
            self._render_treemap()
    
    def zoom_in(self, factor: float = 1.2):
        """Zoom in the treemap view."""
        new_zoom = min(self._zoom_level * factor, self._zoom_max)
        if new_zoom != self._zoom_level:
            self._zoom_level = new_zoom
            self._render_treemap()
    
    def zoom_out(self, factor: float = 1.2):
        """Zoom out the treemap view."""
        new_zoom = max(self._zoom_level / factor, self._zoom_min)
        if new_zoom != self._zoom_level:
            self._zoom_level = new_zoom
            self._render_treemap()
    
    def reset_view(self):
        """Reset zoom and pan to default."""
        self._zoom_level = 1.0
        self._pan_offset_x = 0
        self._pan_offset_y = 0
        self._render_treemap()
    
    def get_zoom_level(self) -> float:
        """Get current zoom level."""
        return self._zoom_level
    
    def get_current_path(self) -> Optional[str]:
        if self._current_node:
            return self._current_node.path
        return None


class TreemapPanel(ttk.Frame):
    """Panel containing the treemap widget with navigation controls."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style='Dark.TFrame')
        
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.back_btn = ttk.Button(nav_frame, text='◀ Up', command=self._go_up, state=tk.DISABLED)
        self.back_btn.pack(side=tk.LEFT)
        
        self.path_var = tk.StringVar(value='Select a drive...')
        self.path_label = ttk.Label(nav_frame, textvariable=self.path_var)
        self.path_label.pack(side=tk.LEFT, padx=10)
        
        self.treemap = TreemapWidget(self, width=800, height=400)
        self.treemap.pack(fill=tk.BOTH, expand=True)
        
        stats_frame = ttk.Frame(self)
        stats_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.size_var = tk.StringVar(value='Total: -')
        ttk.Label(stats_frame, textvariable=self.size_var, foreground='gray').pack(side=tk.LEFT)
        
        self.treemap.set_click_callback(self._on_node_click)
    
    def _go_up(self):
        self.treemap.drill_up()
        self._update_nav()
    
    def _on_node_click(self, node: SizeNode):
        if node.is_directory:
            self.treemap.drill_down(node)
            self._update_nav()
    
    def _update_nav(self):
        if self.treemap._current_node:
            self.path_var.set(self.treemap._current_node.path)
            self.back_btn.configure(state=tk.NORMAL if self.treemap._current_node.parent else tk.DISABLED)
    
    def load_drive(self, path: str, root_node: SizeNode):
        self.treemap.load_node(root_node)
        self._update_nav()
        self.size_var.set(f"Total: {format_size(root_node.size)}")
