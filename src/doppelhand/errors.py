class DoppelhandError(Exception):
    pass


class ActionError(DoppelhandError):
    """A computer action could not be carried out."""


class Aborted(DoppelhandError):
    """The operator asked for the run to stop."""


class UsageError(DoppelhandError):
    """The command line itself was wrong, before any action was attempted."""

    def __init__(self, message: str, usage: str = ""):
        self.usage = usage
        super().__init__(message)


class StepLimit(DoppelhandError):
    """The run used its whole step budget without finishing."""


class Refused(DoppelhandError):
    """The model declined the request."""

    def __init__(self, category: str | None, explanation: str | None):
        self.category = category
        self.explanation = explanation
        super().__init__(f"model refused the request ({category}): {explanation}")
