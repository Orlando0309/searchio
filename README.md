# SearchIO

A fast, modern desktop file search application with visual disk usage analysis.

## Features

- **Fast File Search**: Quickly locate files across your system with an efficient indexing engine
- **Incremental Updates**: Index stays current with minimal overhead through smart incremental updates
- **Visual Disk Analysis**: Interactive treemap visualization showing disk usage by file/folder
- **Memory Usage Graph**: Real-time monitoring of application memory consumption
- **Background Indexing**: Non-blocking indexer runs in the background without impacting system performance
- **Size Analysis**: Detailed file size analysis to identify space-consuming files

## Project Structure

```
searchio/
├── core/                      # Core backend modules
│   ├── __init__.py
│   ├── background_indexer.py  # Background indexing service
│   ├── database.py            # SQLite database layer
│   ├── indexer.py             # Main indexing engine
│   └── size_analyzer.py       # File size analysis utilities
├── gui/                       # Graphical user interface
│   ├── __init__.py
│   ├── main_window.py         # Main application window
│   ├── memory_graph_widget.py # Memory usage visualization
│   └── treemap_widget.py      # Disk usage treemap
├── tests/                     # Test suite
├── pyproject.toml             # Project configuration
└── README.md
```

## Requirements

- Python 3.10 or higher
- uv (recommended package manager)

## Installation

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/searchio.git
cd searchio

# Install with uv
uv sync

# Install development dependencies
uv sync --dev
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/yourusername/searchio.git
cd searchio

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install the package
pip install -e .
```

## Usage

### Running the Application

```bash
# Using uv
uv run searchio

# Or directly after installation
searchio
```

### Running Tests

```bash
# Using uv (recommended)
uv run pytest

# Or
uv test
```

### Building the Package

```bash
# Build wheel and sdist
uv build
```

## Architecture

### Core Module

The `core` module handles all backend operations:

- **Indexer**: Scans directories and builds a searchable index of files
- **Background Indexer**: Manages asynchronous indexing without blocking the UI
- **Database**: SQLite-based storage for index data with efficient queries
- **Size Analyzer**: Computes and caches file/folder sizes for visualization

### GUI Module

The `gui` module provides the user interface:

- **Main Window**: Primary application window with search and navigation
- **Treemap Widget**: Visual representation of disk usage using nested rectangles
- **Memory Graph Widget**: Real-time graph showing application memory consumption

## Development

### Code Style

This project follows standard Python conventions. See `CONVENTIONS.md` for detailed guidelines.

### Adding Features

1. Create a new branch for your feature
2. Implement changes with appropriate tests
3. Run the test suite: `uv run pytest`
4. Submit a pull request

### Testing

All tests are located in the `tests/` directory. Run them with:

```bash
uv run pytest tests/ -v
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
