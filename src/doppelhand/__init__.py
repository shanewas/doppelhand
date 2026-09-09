"""doppelhand — read the Windows screen, drive the mouse and keyboard."""

from doppelhand.errors import (
    ActionError,
    Aborted,
    DoppelhandError,
    Refused,
    StepLimit,
)

__version__ = "1.3.1"

__all__ = [
    "ActionError",
    "Aborted",
    "DoppelhandError",
    "Refused",
    "StepLimit",
    "__version__",
]
