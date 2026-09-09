import base64
import io

import pytest
from PIL import Image

from doppelhand import executor as executor_module
from doppelhand.errors import ActionError, Aborted
from doppelhand.executor import Executor
from fakes import FakeKeyboard, FakeScreen


@pytest.fixture(autouse=True)
def no_settle(monkeypatch):
    monkeypatch.setattr(executor_module, "SETTLE_SECONDS", 0)


@pytest.fixture
def parts():
    screen, keyboard = FakeScreen(), FakeKeyboard()
    return Executor(max_edge=1280, screen=screen, keyboard=keyboard), screen, keyboard


def test_view_is_scaled_down_to_max_edge(parts):
    ex, _, _ = parts
    assert ex.view_size == (1280, 720)
    assert ex.scale == pytest.approx(1280 / 1920)


def test_a_click_lands_on_the_matching_physical_pixel(parts):
    ex, _, keyboard = parts
    ex.dispatch("left_click", {"coordinate": [640, 360]})
    assert ("move", 960, 540) in keyboard.calls
    assert ("click", "left", 1) in keyboard.calls


def test_coordinates_never_leave_the_screen(parts):
    ex, _, _ = parts
    assert ex.to_physical(5000, 5000) == (1919, 1079)
    assert ex.to_physical(-40, -40) == (0, 0)


def test_screenshot_is_a_png_of_the_view_size(parts):
    ex, _, _ = parts
    block = ex.dispatch("screenshot")[0]
    assert block["source"]["media_type"] == "image/png"
    image = Image.open(io.BytesIO(base64.b64decode(block["source"]["data"])))
    assert image.size == (1280, 720)


def test_zoom_grabs_the_region_in_physical_pixels(parts):
    ex, screen, _ = parts
    ex.dispatch("zoom", {"region": [0, 0, 640, 360]})
    assert screen.grabs[-1] == (0, 0, 960, 540)


def test_modifiers_wrap_the_click(parts):
    ex, _, keyboard = parts
    ex.dispatch("left_click", {"coordinate": [10, 10], "text": "ctrl"})
    order = [call[0] for call in keyboard.calls]
    assert order.index("modifiers_down") < order.index("click") < order.index("modifiers_up")


def test_double_and_triple_click_carry_their_count(parts):
    ex, _, keyboard = parts
    ex.dispatch("double_click", {})
    ex.dispatch("triple_click", {})
    assert ("click", "left", 2) in keyboard.calls
    assert ("click", "left", 3) in keyboard.calls


def test_drag_uses_both_coordinates(parts):
    ex, _, keyboard = parts
    ex.dispatch("left_click_drag", {"start_coordinate": [0, 0], "coordinate": [640, 360]})
    assert ("drag", (0, 0), (960, 540), "left") in keyboard.calls


def test_drag_without_a_start_is_rejected(parts):
    ex, _, _ = parts
    with pytest.raises(ActionError):
        ex.dispatch("left_click_drag", {"coordinate": [1, 1]})


def test_cursor_position_is_reported_in_view_pixels(parts):
    ex, _, keyboard = parts
    keyboard.cursor = (960, 540)
    assert ex.dispatch("cursor_position")[0]["text"] == "X=640, Y=360"


def test_key_repeat_is_capped(parts):
    ex, _, keyboard = parts
    ex.dispatch("key", {"text": "Down", "repeat": 5000})
    assert ("press", "Down", 100) in keyboard.calls


def test_wait_and_hold_reject_a_silly_duration(parts):
    ex, _, _ = parts
    with pytest.raises(ActionError):
        ex.dispatch("wait", {"duration": 4000})
    with pytest.raises(ActionError):
        ex.dispatch("hold_key", {"text": "shift", "duration": -1})


def test_a_malformed_number_is_a_tool_error_not_a_crash(parts):
    ex, _, _ = parts
    with pytest.raises(ActionError):
        ex.dispatch("scroll", {"scroll_direction": "down", "scroll_amount": "lots"})
    with pytest.raises(ActionError):
        ex.dispatch("key", {"text": "Down", "repeat": "many"})


def test_button_down_honours_a_coordinate_when_one_is_sent(parts):
    ex, _, keyboard = parts
    ex.dispatch("left_mouse_down", {"coordinate": [640, 360]})
    assert keyboard.calls == [("move", 960, 540), ("mouse_down", "left")]


def test_unknown_action_is_an_action_error(parts):
    ex, _, _ = parts
    with pytest.raises(ActionError):
        ex.dispatch("lick_screen", {})


def test_escape_held_down_stops_everything(parts):
    ex, _, keyboard = parts
    keyboard.abort = True
    with pytest.raises(Aborted):
        ex.dispatch("left_click", {"coordinate": [1, 1]})
    assert keyboard.calls == []


def test_fit_never_enlarges():
    small = Image.new("RGB", (400, 300))
    assert executor_module.fit(small, 1280) is small
