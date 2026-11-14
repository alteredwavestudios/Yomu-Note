"""Local error logs that help explain unexpected failures.

An *exception* is Python's way of reporting a problem.
A *traceback* shows which functions were running when
that problem happened, much like a trail of breadcrumbs.

These logs stay on this computer. Nothing is uploaded.
Do not log document contents, OCR text, or passwords.
The log can include paths to files, so treat it as private.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys


def log_folder() -> Path:
    """Choose a writable log folder for each operating system."""
    if sys.platform == 'win32':
        parent = Path(os.environ.get('LOCALAPPDATA',
                      str(Path.home() / 'AppData' / 'Local')))
        return parent / 'Yomu Note' / 'Logs'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Logs' / 'Yomu Note'
    parent = Path(os.environ.get('XDG_STATE_HOME',
                  str(Path.home() / '.local' / 'state')))
    return parent / 'yomu-note' / 'logs'


def get_logger() -> logging.Logger:
    """Create one size-limited file logger for the application."""
    logger = logging.getLogger('yomunote')
    logger.setLevel(logging.WARNING)
    if logger.handlers:
        return logger
    try:
        directory = log_folder()
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / 'errors.log',
            maxBytes=2 * 1024 * 1024,
            backupCount=2,
            encoding='utf-8',
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
    except OSError:
        # Logging must never prevent the editor from starting.
        logger.addHandler(logging.NullHandler())
    return logger


logger = get_logger()
