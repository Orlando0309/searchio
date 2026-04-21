#!/usr/bin/env python3
"""Main entry point for Searchio desktop application."""

import logging
import sys
from pathlib import Path

from .config import CONFIG_DIR
from .gui.main_window import MainWindow


def setup_logging():
    """Configure application logging."""
    log_file = CONFIG_DIR / "searchio.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger("searchio")


def main():
    """Launch the Searchio desktop application."""
    logger = setup_logging()
    logger.info("Starting Searchio application")
    
    try:
        window = MainWindow()
        window.run()
    except Exception as e:
        logger.exception(f"Application error: {e}")
        raise
    finally:
        logger.info("Application shutdown")


if __name__ == "__main__":
    main()
