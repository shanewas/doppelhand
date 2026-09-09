"""Remembers the coordinate space of the last screenshot.

A caller that captures at one size and then clicks at another silently hits the wrong
pixel, and nothing in the reply says so. Recording the space a screenshot was taken in
means later commands land in it without the caller having to repeat a flag.

The display size is recorded alongside the view size, because the two together decide
the scale. If the display has changed since the shot, the note is worthless and the
default is used instead of a value that would put the pointer somewhere else entirely.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from doppelhand.executor import DEFAULT_MAX_EDGE


def state_dir() -> Path:
    base = os.environ.get("DOPPELHAND_HOME") or os.environ.get("LOCALAPPDATA")
    return Path(base or tempfile.gettempdir()) / "doppelhand"


def _state_file() -> Path:
    return state_dir() / "session.json"


def remember(max_edge: int, display: tuple[int, int]) -> bool:
    """Note the space of a screenshot. False means the note could not be written, which
    costs the caller a flag later and nothing else."""
    try:
        path = _state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"max_edge": int(max_edge), "display": list(display)}),
                        encoding="utf-8")
    except OSError:
        return False
    return True


def recall_max_edge(display: tuple[int, int], default: int = DEFAULT_MAX_EDGE) -> int:
    try:
        noted = json.loads(_state_file().read_text(encoding="utf-8"))
        max_edge = noted["max_edge"]
        taken_on = tuple(noted["display"])
    except (OSError, ValueError, KeyError, TypeError):
        return default
    if taken_on != tuple(display) or not isinstance(max_edge, int) or max_edge <= 0:
        return default
    return max_edge
