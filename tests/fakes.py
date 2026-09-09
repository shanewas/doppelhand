"""Stand-ins for the screen and the input driver, so tests never move a real cursor."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

from PIL import Image


class FakeScreen:
    def __init__(self, size=(1920, 1080)):
        self.size = size
        self.grabs = []

    def screen_size(self):
        return self.size

    def grab(self, region=None):
        self.grabs.append(region)
        width, height = self.size if region is None else (region[2], region[3])
        return Image.new("RGB", (width, height), "white")


class FakeKeyboard:
    def __init__(self):
        self.calls = []
        self.abort = False
        self.cursor = (0, 0)

    def abort_requested(self):
        return self.abort

    def cursor_position(self):
        return self.cursor

    def move(self, x, y):
        self.cursor = (x, y)
        self.calls.append(("move", x, y))

    def click(self, button="left", count=1):
        self.calls.append(("click", button, count))

    def mouse_down(self, button="left"):
        self.calls.append(("mouse_down", button))

    def mouse_up(self, button="left"):
        self.calls.append(("mouse_up", button))

    def drag(self, start, end, button="left"):
        self.calls.append(("drag", start, end, button))

    def scroll(self, direction, amount):
        self.calls.append(("scroll", direction, amount))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def press(self, combo, repeat=1):
        self.calls.append(("press", combo, repeat))

    def hold(self, combo, duration):
        self.calls.append(("hold", combo, duration))

    @contextlib.contextmanager
    def modifiers_held(self, text):
        self.calls.append(("modifiers_down", text))
        try:
            yield
        finally:
            self.calls.append(("modifiers_up", text))


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name, params=None, block_id="toolu_1", toolset_name="computer"):
    return SimpleNamespace(type="tool_use", name=name, id=block_id,
                           input=params or {}, toolset_name=toolset_name)


def response(content, stop_reason="end_turn", stop_details=None):
    return SimpleNamespace(content=content, stop_reason=stop_reason,
                           stop_details=stop_details)


class FakeClient:
    """Replays a scripted list of responses and records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # The agent keeps appending to the same list, so freeze what this call saw.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self.responses:
            raise AssertionError("the agent asked for more turns than the test scripted")
        return self.responses.pop(0)
