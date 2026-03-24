#!/usr/bin/env python3
"""Main entry point for Searchio desktop application."""

import sys
from gui.main_window import MainWindow


def main():
    """Launch the Searchio desktop application."""
    window = MainWindow()
    window.run()


if __name__ == "__main__":
    main()
