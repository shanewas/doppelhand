import http.client
import json
import threading

import pytest

from doppelhand import executor as executor_module, serve as serve_module
from doppelhand.cli import ACTIONS
from doppelhand.serve import TOKEN_HEADER, Server, to_argv
from fakes import FakeKeyboard, FakeScreen, three_monitors

TOKEN = "test-token"


@pytest.fixture
def running(monkeypatch, tmp_path):
    monkeypatch.setattr(executor_module, "SETTLE_SECONDS", 0)
    monkeypatch.setenv("DOPPELHAND_HOME", str(tmp_path))
    screen, keyboard = FakeScreen(layout=three_monitors()), FakeKeyboard()
    monkeypatch.setattr("doppelhand.screen.grab", screen.grab)
    monkeypatch.setattr("doppelhand.screen.monitors", screen.monitors)
    monkeypatch.setattr("doppelhand.screen.primary_monitor", screen.primary_monitor)
    monkeypatch.setattr("doppelhand.screen.virtual_monitor", screen.virtual_monitor)
    monkeypatch.setattr("doppelhand.inputs.cursor_position", lambda: keyboard.cursor)
    monkeypatch.setattr(executor_module, "_screen", screen)
    monkeypatch.setattr(executor_module, "_inputs", keyboard)

    server = Server(0, TOKEN, quiet=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], keyboard, server
    server.shutdown()
    server.server_close()


def call(port, path, method="GET", headers=None, host=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    sent = {TOKEN_HEADER: TOKEN, "Host": host or f"127.0.0.1:{port}"}
    sent.update(headers or {})
    connection.request(method, path, headers=sent)
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def test_a_request_without_the_secret_is_turned_away(running):
    port, _, _server = running
    status, payload = call(port, "/health", headers={TOKEN_HEADER: ""})
    assert status == 401 and payload["ok"] is False


def test_a_wrong_secret_is_turned_away(running):
    port, _, _server = running
    status, _ = call(port, "/health", headers={TOKEN_HEADER: "nearly-right"})
    assert status == 401


def test_a_request_for_another_host_is_turned_away(running):
    """This is what stops a web page from reaching the server by name."""
    port, _, _server = running
    status, payload = call(port, "/health", host="doppelhand.attacker.test")
    assert status == 403 and "loopback" in payload["error"]


def test_browser_requests_are_turned_away(running):
    port, _, _server = running
    assert call(port, "/health", headers={"Origin": "https://example.test"})[0] == 403
    assert call(port, "/health", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403


def test_health_answers_when_everything_is_right(running):
    port, _, _server = running
    status, payload = call(port, "/health")
    assert status == 200 and payload["ok"] is True


def test_reading_the_screen_needs_no_side_effects(running):
    port, _, _server = running
    status, payload = call(port, "/screen")
    assert status == 200
    assert [m["monitor"] for m in payload["monitors"]] == [1, 2, 3]


def test_an_action_that_moves_the_pointer_refuses_GET(running):
    port, keyboard, _server = running
    status, payload = call(port, "/click?at=640,360")
    assert status == 405 and "POST" in payload["error"]
    assert keyboard.calls == []


def test_a_click_over_http_reaches_the_driver(running):
    port, keyboard, _server = running
    status, payload = call(port, "/click?at=640,360", method="POST")
    assert status == 200 and payload["action"] == "left_click"
    assert ("move", 960, 540) in keyboard.calls


def test_flags_and_options_survive_the_query_string(running):
    port, keyboard, _server = running
    call(port, "/click?at=10,10&button=right&modifiers=ctrl", method="POST")
    assert ("click", "right", 1) in keyboard.calls
    assert ("modifiers_down", "ctrl") in keyboard.calls


def test_a_click_off_the_screen_is_refused_here_too(running):
    port, keyboard, _server = running
    status, payload = call(port, "/click?at=99999,99999", method="POST")
    assert status == 400 and "outside" in payload["error"]
    assert keyboard.calls == []


def test_a_bad_argument_comes_back_as_a_usage_error(running):
    port, _, _server = running
    status, payload = call(port, "/click?at=notacoord", method="POST")
    assert status == 400 and "usage" in payload


def test_an_unknown_action_lists_the_real_ones(running):
    port, _, _server = running
    status, payload = call(port, "/frobnicate", method="POST")
    assert status == 404 and "click" in payload["actions"]


def test_shot_writes_a_file_through_the_server(running, tmp_path):
    port, _, _server = running
    target = tmp_path / "served.jpg"
    status, payload = call(port, f"/shot?out={target}&fast=1")
    assert status == 200 and target.exists()
    assert payload["path"] == str(target)


def test_query_strings_become_command_lines():
    assert to_argv("click", {"at": ["640,360"]}) == ["click", "640,360"]
    assert to_argv("drag", {"start": ["0,0"], "end": ["5,5"]}) == ["drag", "0,0", "5,5"]
    assert to_argv("shot", {"fast": ["1"]}) == ["shot", "--fast"]
    assert to_argv("shot", {"fast": ["0"]}) == ["shot"]
    assert to_argv("key", {"combo": ["ctrl+s"], "repeat": ["3"]}) == [
        "key", "ctrl+s", "--repeat", "3"]


def test_an_unexpected_failure_still_answers_in_json(running, monkeypatch):
    """A dropped connection would leave a caller unable to tell a crash from a hang."""
    port, _, _server = running
    monkeypatch.setitem(ACTIONS, "cursor",
                        lambda *_: (_ for _ in ()).throw(ValueError("boom")))
    status, payload = call(port, "/cursor")
    assert status == 500 and payload["ok"] is False
    assert "ValueError" in payload["error"]


def test_stopping_waits_for_the_action_in_flight(running):
    """Releasing the capture objects while an action is part way through them crashes in
    native code, so stop has to queue behind whatever holds the lock."""
    port, _, server = running
    answered = {}

    server.busy.acquire()  # stand in for an action that is mid-capture
    stopper = threading.Thread(
        target=lambda: answered.update(status=call(port, "/stop", method="POST")[0]),
        daemon=True)
    stopper.start()
    stopper.join(timeout=1.0)
    assert stopper.is_alive() and not answered, "stop jumped the queue"

    server.busy.release()
    stopper.join(timeout=10)
    assert answered.get("status") == 200


def test_every_action_knows_its_positional_arguments():
    """A missing entry would silently turn a positional into an unknown flag."""
    assert set(serve_module.POSITIONALS) == set(ACTIONS)
