#!/usr/bin/env python3
"""Quick import verification for TreemapWidget"""
import sys
from pathlib import Path
project_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, project_root)
print(f'CWD: {Path.cwd()}')
print(f'Project root added: {project_root}')
print(f'sys.path[0]: {sys.path[0]}')
from gui.treemap_widget import TreemapWidget
print('Import OK')
print(f'TreemapWidget class: {TreemapWidget}')
