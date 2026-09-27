"""Shared helper for debug log files.

These used to live at fixed, predictable /tmp paths (e.g. /tmp/aisubs_debug.log)
opened in append mode. On a shared multi-user machine an attacker can pre-plant
a symlink at that exact path, and our append would then follow it into any
file the victim user can write (CWE-59). Logs now live under a private
per-user directory and are opened with O_NOFOLLOW so a symlink planted at the
path is refused instead of followed.
"""

import os

_DEFAULT_DIR = os.path.expanduser("~/.local/share/vlc-ai-subs/logs")


def _log_dir() -> str:
    return os.environ.get("VSCL_AISUBS_LOG_DIR") or _DEFAULT_DIR


def debug_log_path(name: str) -> str:
    """Return the path a named debug log lives at (its directory is created)."""
    d = _log_dir()
    os.makedirs(d, exist_ok=True, mode=0o700)
    return os.path.join(d, name)


def append_debug_log(name: str, text: str) -> None:
    """Append text to a named debug log; silently refuses to follow a symlink."""
    path = debug_log_path(name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        return
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
