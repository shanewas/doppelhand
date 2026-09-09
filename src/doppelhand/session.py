"""Remembers which display the last screenshot was of, and the space it was taken in.

A caller that captures one display and then clicks using another one's coordinates hits
the wrong pixel, and nothing in the reply says so. Recording the shot means later
commands land where the caller meant without repeating flags.

The whole monitor layout is recorded alongside. If a display has moved, been unplugged
or changed resolution since the shot, the note is worthless and the defaults are used
instead of a value that would put the pointer somewhere else entirely.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def state_dir() -> Path:
    base = os.environ.get("DOPPELHAND_HOME") or os.environ.get("LOCALAPPDATA")
    return Path(base or tempfile.gettempdir()) / "doppelhand"


def _state_file() -> Path:
    return state_dir() / "session.json"


def layout_of(monitors: list) -> list:
    return [[monitor.index, list(monitor.origin), list(monitor.size)]
            for monitor in monitors]


def remember(max_edge: int, monitor_index: int, layout: list) -> bool:
    """Note the last shot. False means the note could not be written, which costs the
    caller a flag on the next command and nothing else."""
    try:
        path = _state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"max_edge": int(max_edge),
                                    "monitor": int(monitor_index),
                                    "layout": layout}), encoding="utf-8")
    except OSError:
        return False
    return True


def recall(layout: list) -> tuple[int | None, int | None]:
    """The remembered view size and monitor, or a pair of Nones if the note cannot be
    trusted against the displays that are attached now."""
    try:
        noted = json.loads(_state_file().read_text(encoding="utf-8"))
        max_edge = noted["max_edge"]
        monitor = noted["monitor"]
        taken_on = noted["layout"]
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
    if taken_on != layout or not isinstance(max_edge, int) or max_edge <= 0:
        return None, None
    if not isinstance(monitor, int):
        return None, None
    return max_edge, monitor
