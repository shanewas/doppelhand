import json
import re

import pytest

from doppelhand import cli, executor as executor_module, session, skills
from fakes import FakeKeyboard, FakeScreen, three_monitors


@pytest.fixture(autouse=True)
def hermetic(monkeypatch, tmp_path):
    """No real screen, no real cursor, no writing into the user's app data.

    The fake screen carries the three-monitor layout that exposed the single-display
    assumption, so every CLI test runs against the harder arrangement.
    """
    monkeypatch.setattr(executor_module, "SETTLE_SECONDS", 0)
    monkeypatch.setenv("DOPPELHAND_HOME", str(tmp_path))
    screen, keyboard = FakeScreen(layout=three_monitors()), FakeKeyboard()
    monkeypatch.setattr("doppelhand.screen.grab", screen.grab)
    monkeypatch.setattr("doppelhand.screen.screen_size", screen.screen_size)
    monkeypatch.setattr("doppelhand.screen.monitors", screen.monitors)
    monkeypatch.setattr("doppelhand.screen.primary_monitor", screen.primary_monitor)
    monkeypatch.setattr("doppelhand.screen.virtual_monitor", screen.virtual_monitor)
    monkeypatch.setattr("doppelhand.inputs.cursor_position", lambda: keyboard.cursor)
    # The executor resolves these when it is built, so the CLI's own construction path
    # runs unchanged and still reaches the fakes.
    monkeypatch.setattr(executor_module, "_screen", screen)
    monkeypatch.setattr(executor_module, "_inputs", keyboard)
    keyboard.screen = screen
    return keyboard


@pytest.fixture
def invoke(capsys):
    def call(*argv):
        code = cli.main(list(argv))
        out = capsys.readouterr().out
        return code, json.loads(out)
    return call


def test_screen_reports_the_coordinate_space(invoke):
    code, payload = invoke("screen")
    assert code == 0 and payload["ok"]
    assert payload["view"] == [1280, 720]
    assert payload["display"] == [1920, 1080]


def test_a_click_is_scaled_from_view_space(invoke, hermetic):
    code, payload = invoke("click", "640,360")
    assert code == 0 and payload["action"] == "left_click"
    assert ("move", 960, 540) in hermetic.calls


def test_display_space_takes_coordinates_as_they_are(invoke, hermetic):
    invoke("click", "960,540", "--space", "display")
    assert ("move", 960, 540) in hermetic.calls


def test_shot_writes_a_png_and_names_its_space(invoke, tmp_path):
    target = tmp_path / "look.png"
    code, payload = invoke("shot", str(target))
    assert code == 0 and target.exists()
    assert payload["space"] == "view" and payload["image"] == [1280, 720]


def test_a_region_shot_says_not_to_click_from_it(invoke, tmp_path):
    _, payload = invoke("shot", str(tmp_path / "crop.png"), "--region", "0,0,640,360")
    assert payload["space"] == "region"
    assert "region" in payload


LAYOUT = [[1, [-1920, 0], [1920, 1080]], [2, [0, 0], [1920, 1080]],
          [3, [1920, 0], [1920, 1080]]]


def test_the_view_size_of_the_last_shot_is_reused(invoke, tmp_path):
    _, payload = invoke("shot", str(tmp_path / "big.png"), "--max-edge", "1568")
    assert payload["space_remembered"] is True
    assert session.recall(LAYOUT) == (1568, 2)
    _, payload = invoke("screen")
    assert payload["view"] == [1568, 882]


def test_a_region_shot_does_not_change_the_remembered_space(invoke, tmp_path):
    invoke("shot", str(tmp_path / "a.png"), "--max-edge", "1568")
    invoke("shot", str(tmp_path / "b.png"), "--region", "0,0,10,10", "--max-edge", "800")
    assert session.recall(LAYOUT) == (1568, 2)


def test_moving_a_display_throws_the_remembered_space_away(invoke, tmp_path):
    invoke("shot", str(tmp_path / "before.png"), "--max-edge", "1568")
    rearranged = [[1, [0, 0], [1920, 1080]], [2, [1920, 0], [1920, 1080]]]
    assert session.recall(rearranged) == (None, None)


def test_a_corrupt_note_falls_back_instead_of_crashing(invoke, tmp_path):
    session.state_dir().mkdir(parents=True, exist_ok=True)
    for junk in ("null", "42", "[]", '{"max_edge": null}', "not json at all"):
        (session.state_dir() / "session.json").write_text(junk, encoding="utf-8")
        assert session.recall(LAYOUT) == (None, None)
        code, payload = invoke("screen")
        assert code == 0 and payload["view"] == [1280, 720]


def test_a_screenshot_that_landed_is_reported_even_if_the_note_fails(invoke, tmp_path,
                                                                    monkeypatch):
    monkeypatch.setattr(session, "remember", lambda *_: False)
    code, payload = invoke("shot", str(tmp_path / "shot.png"))
    assert code == 0 and payload["ok"] and payload["space_remembered"] is False
    assert (tmp_path / "shot.png").exists()


def test_a_region_with_no_area_is_rejected():
    with pytest.raises(SystemExit) as caught:
        cli.main(["shot", "--region", "500,500,-100,-50"])
    assert caught.value.code == 2


def test_a_region_off_the_screen_is_refused(invoke, tmp_path):
    code, payload = invoke("shot", str(tmp_path / "x.png"), "--region", "9000,9000,10,10")
    assert code == 1 and "outside" in payload["error"]


def test_the_reported_repeat_is_the_one_that_ran(invoke, hermetic):
    _, payload = invoke("key", "Down", "--repeat", "5000")
    assert payload["repeat"] == 100
    assert ("press", "Down", 100) in hermetic.calls


def test_a_backwards_scroll_amount_is_refused(invoke):
    code, payload = invoke("scroll", "down", "-5")
    assert code == 1 and "1 or more" in payload["error"]


def test_cursor_is_reported_in_both_spaces(invoke, hermetic):
    hermetic.cursor = (960, 540)
    _, payload = invoke("cursor")
    assert payload["view"] == [640, 360] and payload["display"] == [960, 540]
    assert payload["pointer_on_monitor"] == 2


def test_cursor_says_when_the_pointer_is_on_another_display(invoke, hermetic):
    hermetic.cursor = (-900, 300)  # on the left-hand monitor
    _, payload = invoke("cursor")
    assert payload["monitor"] == 2 and payload["pointer_on_monitor"] == 1
    assert payload["view"][0] < 0  # off the left edge of the view being worked in


def test_drag_scroll_type_and_key_reach_the_driver(invoke, hermetic):
    invoke("drag", "0,0", "640,360")
    invoke("scroll", "down", "5")
    invoke("type", "hello")
    invoke("key", "ctrl+s")
    kinds = [call[0] for call in hermetic.calls]
    assert {"drag", "scroll", "type_text", "press"} <= set(kinds)


def test_a_bad_coordinate_is_rejected_by_the_parser():
    with pytest.raises(SystemExit) as caught:
        cli.main(["click", "middle-of-the-screen"])
    assert caught.value.code == 2


def test_an_unknown_key_comes_back_as_a_failure(invoke):
    code, payload = invoke("key", "hyper+q")
    assert code == 1 and payload["ok"] is False
    assert "modifier" in payload["error"]


def test_only_the_left_button_double_clicks(invoke):
    code, payload = invoke("click", "1,1", "--button", "right", "--count", "2")
    assert code == 1 and payload["ok"] is False


def test_a_click_off_the_screen_is_refused_instead_of_landing_in_a_corner(invoke,
                                                                          hermetic):
    code, payload = invoke("click", "99999,99999")
    assert code == 1 and payload["ok"] is False
    assert "outside" in payload["error"]
    assert hermetic.calls == []


def test_a_usage_error_is_still_json(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["click", "notacoord"])
    assert caught.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and "usage" in payload


def test_an_unknown_monitor_is_refused(invoke):
    code, payload = invoke("shot", "--monitor", "9")
    assert code == 1 and "no monitor 9" in payload["error"]


def test_a_bad_monitor_on_a_run_is_reported_not_raised(capsys):
    assert cli.main(["run", "do something", "--monitor", "9", "-y"]) == 1
    assert "no monitor 9" in capsys.readouterr().err


def test_screen_lists_every_display(invoke):
    _, payload = invoke("screen")
    assert [m["monitor"] for m in payload["monitors"]] == [1, 2, 3]
    assert payload["monitor"] == 2  # the primary one, in the middle
    assert [m["origin"] for m in payload["monitors"]][0] == [-1920, 0]


def test_a_click_on_another_display_uses_that_display_origin(invoke, hermetic):
    invoke("click", "640,360", "--monitor", "3")
    assert ("move", 2880, 540) in hermetic.calls


def test_the_display_of_the_last_shot_is_reused(invoke, tmp_path, hermetic):
    invoke("shot", str(tmp_path / "left.png"), "--monitor", "1")
    _, payload = invoke("screen")
    assert payload["monitor"] == 1
    invoke("click", "0,0")
    assert ("move", -1920, 0) in hermetic.calls


def test_every_display_at_once_is_one_wide_view(invoke, tmp_path):
    _, payload = invoke("shot", str(tmp_path / "all.png"), "--monitor", "all")
    assert payload["display"] == [5760, 1080]
    assert payload["monitor"] == 0


def test_the_pointer_is_drawn_unless_it_is_turned_off(invoke, tmp_path, hermetic):
    _, payload = invoke("shot", str(tmp_path / "with.png"))
    assert payload["cursor_drawn"] is True
    assert hermetic.screen.grabs[-1][1] is True

    _, payload = invoke("shot", str(tmp_path / "without.png"), "--no-cursor")
    assert payload["cursor_drawn"] is False
    assert hermetic.screen.grabs[-1][1] is False


def test_the_skill_can_be_printed(capsys):
    assert cli.main(["install-skill", "--print"]) == 0
    assert capsys.readouterr().out.startswith("---\nname: doppelhand")


def test_the_skill_installs_once_and_refuses_to_clobber(invoke, tmp_path):
    dest = tmp_path / "skills" / "doppelhand"
    code, payload = invoke("install-skill", "--dest", str(dest))
    assert code == 0 and (dest / "SKILL.md").exists()

    code, payload = invoke("install-skill", "--dest", str(dest))
    assert code == 1 and "--force" in payload["error"]

    assert invoke("install-skill", "--dest", str(dest), "--force")[0] == 0


def test_every_command_the_skill_teaches_actually_exists():
    """The skill is documentation an agent follows literally, so a command that drifts
    out of the parser becomes an agent running something that does not exist."""
    subcommands = set(cli.build_parser()._subparsers._group_actions[0].choices)
    taught = set(re.findall(r"`?doppelhand ([a-z-]+)", skills.skill_text()))
    assert taught - subcommands == set()


def test_the_skill_ships_inside_the_package():
    assert skills.skill_source().is_file()
    assert "coordinates" in skills.skill_text().lower()
