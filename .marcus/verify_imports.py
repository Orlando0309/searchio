#!/usr/bin/env python
"""Quick verification that core modules import correctly."""
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import gui.treemap_widget
import core.indexer
print('Modules compiled successfully')
