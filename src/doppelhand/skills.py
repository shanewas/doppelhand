"""Installs the portable skill document into whichever agent harness asked for it."""

from __future__ import annotations

import shutil
from pathlib import Path

from doppelhand.errors import DoppelhandError

SKILL_NAME = "doppelhand"

#: Where each harness looks for skills. Verified against installed layouts rather than
#: taken from documentation, so a harness missing here needs --dest, not a guess.
TARGETS = {
    "claude-code": Path.home() / ".claude" / "skills",
    "opencode": Path.home() / ".config" / "opencode" / "skills",
    "agy": Path.home() / ".gemini" / "config" / "skills",
    "agy-workspace": Path(".agents") / "skills",
}


def skill_source() -> Path:
    return Path(__file__).parent / "skill" / "SKILL.md"


def skill_text() -> str:
    return skill_source().read_text(encoding="utf-8")


def install(target: str | None = None, dest: Path | str | None = None,
            force: bool = False) -> Path:
    """Copy SKILL.md into a harness's skill directory and return where it landed."""
    if dest is not None:
        directory = Path(dest)
    elif target in TARGETS:
        directory = TARGETS[target] / SKILL_NAME
    else:
        known = ", ".join(sorted(TARGETS))
        raise DoppelhandError(f"unknown harness {target!r}. Known: {known}. "
                              f"For anything else pass --dest with a directory.")

    path = directory / "SKILL.md"
    if path.exists() and not force:
        raise DoppelhandError(f"{path} already exists. Pass --force to replace it.")
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(skill_source(), path)
    return path
