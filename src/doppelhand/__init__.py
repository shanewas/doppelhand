"""doppelhand — read the Windows screen, drive the mouse and keyboard."""

from doppelhand.errors import (
    ActionError,
    Aborted,
    DoppelhandError,
    Refused,
    StepLimit,
)

__version__ = "1.2.0"

__all__ = [
    "ActionError",
    "Aborted",
    "DoppelhandError",
    "Refused",
    "StepLimit",
    "__version__",
]
