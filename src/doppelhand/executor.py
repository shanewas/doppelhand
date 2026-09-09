"""Carries out the actions of Claude's computer toolset on this machine."""

from __future__ import annotations

import base64
import io
import time

from PIL import Image

from doppelhand import inputs as _inputs
from doppelhand import screen as _screen
from doppelhand.errors import ActionError, Aborted

#: Long edge of the screenshots sent to the model. 1280 keeps a desktop legible at a
#: fraction of the image-token cost of a native-resolution capture.
DEFAULT_MAX_EDGE = 1280

#: Time given to the screen to repaint after an action that changes it.
SETTLE_SECONDS = 0.2

MAX_DURATION = 300
OK = [{"type": "text", "text": "OK"}]

_CLICKS = {
    "left_click": ("left", 1),
    "right_click": ("right", 1),
    "middle_click": ("middle", 1),
    "double_click": ("left", 2),
    "triple_click": ("left", 3),
}


class Executor:
    """Maps toolset members onto real input, and screenshot pixels onto real pixels.

    Claude answers in the pixel space of the screenshot it was sent, which is smaller
    than the display, so every incoming coordinate is scaled back up before use.
    """

    def __init__(self, max_edge: int = DEFAULT_MAX_EDGE, screen=_screen, keyboard=_inputs):
        self.screen = screen
        self.keyboard = keyboard
        self.max_edge = max_edge
        self.screen_size = screen.screen_size()
        width, height = self.screen_size
        self.scale = min(1.0, max_edge / max(width, height))
        self.view_size = (round(width * self.scale), round(height * self.scale))

    def to_physical(self, x: float, y: float) -> tuple[int, int]:
        width, height = self.screen_size
        return (min(width - 1, max(0, round(x / self.scale))),
                min(height - 1, max(0, round(y / self.scale))))

    def to_view(self, x: float, y: float) -> tuple[int, int]:
        return round(x * self.scale), round(y * self.scale)

    def screenshot(self) -> dict:
        return _image_block(fit(self.screen.grab(), self.max_edge))

    def dispatch(self, name: str, params: dict | None = None) -> list[dict]:
        """Run one toolset member and return the blocks for its tool result."""
        if self.keyboard.abort_requested():
            raise Aborted("Escape was held down")
        params = params or {}
        handler = getattr(self, f"_do_{name}", None)
        if handler is None:
            raise ActionError(f"unsupported computer action: {name}")
        return handler(params)

    def _point(self, params: dict, key: str = "coordinate") -> tuple[int, int] | None:
        value = params.get(key)
        if value is None:
            return None
        if len(value) != 2:
            raise ActionError(f"{key} needs two numbers, got {value!r}")
        return self.to_physical(value[0], value[1])

    def _do_screenshot(self, params: dict) -> list[dict]:
        return [self.screenshot()]

    def _do_zoom(self, params: dict) -> list[dict]:
        region = params.get("region")
        if not region or len(region) != 4:
            raise ActionError("zoom needs a region of [x0, y0, x1, y1]")
        left, top = self.to_physical(region[0], region[1])
        right, bottom = self.to_physical(region[2], region[3])
        left, right = sorted((left, right))
        top, bottom = sorted((top, bottom))
        crop = self.screen.grab((left, top, max(1, right - left), max(1, bottom - top)))
        return [_image_block(fit(crop, self.max_edge))]

    def _do_left_click(self, params: dict) -> list[dict]:
        return self._click("left_click", params)

    def _do_right_click(self, params: dict) -> list[dict]:
        return self._click("right_click", params)

    def _do_middle_click(self, params: dict) -> list[dict]:
        return self._click("middle_click", params)

    def _do_double_click(self, params: dict) -> list[dict]:
        return self._click("double_click", params)

    def _do_triple_click(self, params: dict) -> list[dict]:
        return self._click("triple_click", params)

    def _click(self, action: str, params: dict) -> list[dict]:
        button, count = _CLICKS[action]
        point = self._point(params)
        if point:
            self.keyboard.move(*point)
        with self.keyboard.modifiers_held(params.get("text")):
            self.keyboard.click(button, count)
        return self._settled()

    def _do_left_click_drag(self, params: dict) -> list[dict]:
        start = self._point(params, "start_coordinate")
        end = self._point(params)
        if start is None or end is None:
            raise ActionError("left_click_drag needs start_coordinate and coordinate")
        with self.keyboard.modifiers_held(params.get("text")):
            self.keyboard.drag(start, end)
        return self._settled()

    def _do_mouse_move(self, params: dict) -> list[dict]:
        point = self._point(params)
        if point is None:
            raise ActionError("mouse_move needs a coordinate")
        self.keyboard.move(*point)
        return OK

    def _do_left_mouse_down(self, params: dict) -> list[dict]:
        # The toolset presses at the current position, but honour a coordinate if one
        # arrives rather than pressing wherever the cursor happened to be left.
        point = self._point(params)
        if point:
            self.keyboard.move(*point)
        self.keyboard.mouse_down("left")
        return OK

    def _do_left_mouse_up(self, params: dict) -> list[dict]:
        point = self._point(params)
        if point:
            self.keyboard.move(*point)
        self.keyboard.mouse_up("left")
        return self._settled()

    def _do_cursor_position(self, params: dict) -> list[dict]:
        x, y = self.to_view(*self.keyboard.cursor_position())
        return [{"type": "text", "text": f"X={x}, Y={y}"}]

    def _do_scroll(self, params: dict) -> list[dict]:
        direction = params.get("scroll_direction")
        if not direction:
            raise ActionError("scroll needs a scroll_direction")
        point = self._point(params)
        if point:
            self.keyboard.move(*point)
        with self.keyboard.modifiers_held(params.get("text")):
            self.keyboard.scroll(direction, _whole(params, "scroll_amount", 1))
        return self._settled()

    def _do_type(self, params: dict) -> list[dict]:
        text = params.get("text")
        if text is None:
            raise ActionError("type needs text")
        self.keyboard.type_text(text)
        return self._settled()

    def _do_key(self, params: dict) -> list[dict]:
        combo = params.get("text")
        if not combo:
            raise ActionError("key needs text naming the key or combination")
        self.keyboard.press(combo, repeat=min(100, max(1, _whole(params, "repeat", 1))))
        return self._settled()

    def _do_hold_key(self, params: dict) -> list[dict]:
        combo = params.get("text")
        if not combo:
            raise ActionError("hold_key needs text naming the key or combination")
        self.keyboard.hold(combo, _duration(params))
        return self._settled()

    def _do_wait(self, params: dict) -> list[dict]:
        time.sleep(_duration(params))
        return OK

    def _settled(self) -> list[dict]:
        time.sleep(SETTLE_SECONDS)
        return OK


def _whole(params: dict, key: str, default: int) -> int:
    """Read a whole number. A malformed one has to come back to the model as a tool
    error, not escape dispatch as a ValueError and end the run."""
    value = params.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ActionError(f"{key} must be a whole number, got {value!r}") from None


def _duration(params: dict) -> float:
    try:
        seconds = float(params.get("duration", 0))
    except (TypeError, ValueError):
        raise ActionError(f"duration must be a number, got {params.get('duration')!r}") from None
    if not 0 <= seconds <= MAX_DURATION:
        raise ActionError(f"duration must be between 0 and {MAX_DURATION} seconds")
    return seconds


def fit(image: Image.Image, max_edge: int) -> Image.Image:
    scale = min(1.0, max_edge / max(image.size))
    if scale == 1.0:
        return image
    return image.resize((round(image.width * scale), round(image.height * scale)),
                        Image.LANCZOS)


def _image_block(image: Image.Image) -> dict:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
        },
    }
