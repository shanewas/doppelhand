import json
import re

import pytest

from doppelhand import cli, executor as executor_module, session, skills
from doppelhand.executor import Executor
from fakes import FakeKeyboard, FakeScreen


@pytest.fixture(autouse=True)
def hermetic(monkeypatch, tmp_path):
    """No real screen, no real cursor, no writing into the user's app data."""
    monkeypatch.setattr(executor_module, "SETTLE_SECONDS", 0)
    monkeypatch.setenv("DOPPELHAND_HOME", str(tmp_path))
    screen, keyboard = FakeScreen(), FakeKeyboard()
    monkeypatch.setattr("doppelhand.screen.grab", screen.grab)
    monkeypatch.setattr("doppelhand.screen.screen_size", screen.screen_size)
    monkeypatch.setattr("doppelhand.inputs.cursor_position", lambda: keyboard.cursor)

    built = {}

    def executor_for(args):
        max_edge = (max(screen.size) if getattr(args, "space", "view") == "display"
                    else args.max_edge or session.recall_max_edge(screen.size))
        built["executor"] = Executor(max_edge=max_edge, screen=screen, keyboard=keyboard)
        return built["executor"]

    monkeypatch.setattr(cli, "_executor", executor_for)
    return keyboard


def run(*argv) -> tuple[int, dict]:
    code = cli.main(list(argv))
    return code, code


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


def test_the_view_size_of_the_last_shot_is_reused(invoke, tmp_path):
    _, payload = invoke("shot", str(tmp_path / "big.png"), "--max-edge", "1568")
    assert payload["space_remembered"] is True
    assert session.recall_max_edge((1920, 1080)) == 1568
    _, payload = invoke("screen")
    assert payload["view"] == [1568, 882]


def test_a_region_shot_does_not_change_the_remembered_space(invoke, tmp_path):
    invoke("shot", str(tmp_path / "a.png"), "--max-edge", "1568")
    invoke("shot", str(tmp_path / "b.png"), "--region", "0,0,10,10", "--max-edge", "800")
    assert session.recall_max_edge((1920, 1080)) == 1568


def test_a_resolution_change_throws_the_remembered_space_away(invoke, tmp_path):
    invoke("shot", str(tmp_path / "before.png"), "--max-edge", "1568")
    assert session.recall_max_edge((1280, 800)) == executor_module.DEFAULT_MAX_EDGE


def test_a_corrupt_note_falls_back_instead_of_crashing(invoke, tmp_path):
    (session.state_dir()).mkdir(parents=True, exist_ok=True)
    for junk in ("null", "42", "[]", "not json at all"):
        (session.state_dir() / "session.json").write_text(junk, encoding="utf-8")
        assert session.recall_max_edge((1920, 1080)) == executor_module.DEFAULT_MAX_EDGE
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
