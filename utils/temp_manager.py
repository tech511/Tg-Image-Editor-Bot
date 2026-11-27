"""Temporary file handling. Every session owns one folder: <TEMP_DIR>/<user>_<session>."""
import logging
import os
import shutil
import time

import config

log = logging.getLogger(__name__)


def _root() -> str:
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    return os.path.abspath(config.TEMP_DIR)


def create_session_dir(user_id: int, session_id: str) -> str:
    path = os.path.join(_root(), f"{user_id}_{session_id}")
    os.makedirs(path, exist_ok=True)
    return path


def remove_dir(path: str) -> None:
    """Safe to call many times, never raises."""
    shutil.rmtree(path, ignore_errors=True)


def cleanup_all() -> None:
    """Wipe everything (startup / shutdown)."""
    shutil.rmtree(_root(), ignore_errors=True)
    os.makedirs(_root(), exist_ok=True)


def cleanup_abandoned(active_dirs: set, max_age_sec: int) -> None:
    """Delete folders that no live session owns and that are old enough."""
    root = _root()
    now = time.time()
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if path in active_dirs or not os.path.isdir(path):
            continue
        try:
            if now - os.path.getmtime(path) > max_age_sec:
                remove_dir(path)
                log.info("Removed abandoned temp folder %s", name)
        except OSError:
            pass
