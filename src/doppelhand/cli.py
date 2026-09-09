"""Command line entry point.

Two audiences share it. The action commands print one JSON object each and are meant to
be driven by another agent, which supplies the judgement between them. `run` is the
standalone path, where doppelhand asks Claude what to do next itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from doppelhand import __version__, session, skills
from doppelhand.errors import Aborted, DoppelhandError, Refused, StepLimit
from doppelhand.executor import DEFAULT_MAX_EDGE, Executor, fit

SPACES = ("view", "display")


def _use_utf8() -> None:
    """Model output and window titles routinely contain characters the default Windows
    console encoding cannot represent, and printing one would end the run."""
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def coordinate(text: str) -> tuple[int, int]:
    try:
        x, y = (part.strip() for part in text.split(","))
        return int(x), int(y)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected X,Y but got {text!r}") from None


class JsonParser(argparse.ArgumentParser):
    """Reports usage errors the same way every other failure is reported, so a caller
    parsing stdout never has to fall back to reading argparse's prose."""

    def error(self, message: str):
        print(json.dumps({"ok": False, "error": message,
                          "usage": self.format_usage().strip()}))
        raise SystemExit(2)


def monitor_choice(text: str) -> int | str:
    wanted = text.strip().lower()
    if wanted in ("all", "primary"):
        return wanted
    try:
        number = int(wanted)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a monitor number, 'primary' or 'all', got {text!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError("monitors are numbered from 1")
    return number


def region(text: str) -> tuple[int, int, int, int]:
    try:
        left, top, width, height = (int(part.strip()) for part in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected X,Y,W,H but got {text!r}") from None
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError(f"region has no area: {width}x{height}")
    return left, top, width, height


def build_parser() -> argparse.ArgumentParser:
    parser = JsonParser(
        prog="doppelhand",
        description="Read the Windows screen, drive the mouse and keyboard.",
    )
    parser.add_argument("--version", action="version", version=f"doppelhand {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    def action(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--space", choices=SPACES, default="view",
                         help="coordinate space of the arguments (default: view)")
        sub.add_argument("--max-edge", type=int, default=None,
                         help="long edge of the view space (default: the last shot's)")
        sub.add_argument("--monitor", type=monitor_choice, default=None,
                         help="which display: a number, 'primary' or 'all'")
        return sub

    shot = action("shot", "capture the screen to a PNG")
    shot.add_argument("out", nargs="?", default=None, help="where to write the PNG")
    shot.add_argument("--region", type=region, default=None,
                      help="capture X,Y,W,H instead of the whole display")
    shot.add_argument("--no-cursor", dest="cursor", action="store_false",
                      help="leave the mouse pointer out of the capture")

    action("screen", "report the coordinate space without capturing")
    action("cursor", "report where the pointer is")

    click = action("click", "click at a point")
    click.add_argument("at", type=coordinate)
    click.add_argument("--button", choices=("left", "right", "middle"), default="left")
    click.add_argument("--count", type=int, default=1, help="2 double clicks, 3 selects a line")
    click.add_argument("--modifiers", default=None, help="keys to hold, e.g. ctrl+shift")

    move = action("move", "move the pointer without clicking")
    move.add_argument("at", type=coordinate)

    drag = action("drag", "press, drag and release")
    drag.add_argument("start", type=coordinate)
    drag.add_argument("end", type=coordinate)
    drag.add_argument("--modifiers", default=None)

    scroll = action("scroll", "scroll the surface under the pointer")
    scroll.add_argument("direction", choices=("up", "down", "left", "right"))
    scroll.add_argument("amount", nargs="?", type=int, default=3)
    scroll.add_argument("--at", type=coordinate, default=None)
    scroll.add_argument("--modifiers", default=None)

    type_text = action("type", "type literal text at the keyboard focus")
    type_text.add_argument("text")

    key = action("key", "press a key or combination, e.g. ctrl+s")
    key.add_argument("combo")
    key.add_argument("--repeat", type=int, default=1)

    hold = action("hold", "hold a key down")
    hold.add_argument("combo")
    hold.add_argument("seconds", type=float)

    wait = action("wait", "pause and let the screen settle")
    wait.add_argument("seconds", type=float)

    run = commands.add_parser("run", help="carry out a whole task with Claude driving")
    run.add_argument("task", help="what to do, in plain language")
    run.add_argument("--model", default=None, help="Claude model to drive the run")
    run.add_argument("--max-steps", type=int, default=30, help="model turns before giving up")
    run.add_argument("--max-edge", type=int, default=DEFAULT_MAX_EDGE,
                     help="long edge of the screenshots sent to the model")
    run.add_argument("--monitor", type=monitor_choice, default=None,
                     help="which display: a number, 'primary' or 'all'")
    run.add_argument("-y", "--yes", action="store_true", help="skip the confirmation")
    run.add_argument("-q", "--quiet", action="store_true", help="only print the final answer")

    install = commands.add_parser("install-skill",
                                  help="install the agent skill into a harness")
    install.add_argument("target", nargs="?", choices=sorted(skills.TARGETS), default=None)
    install.add_argument("--dest", default=None, help="install into this directory instead")
    install.add_argument("--print", dest="show", action="store_true",
                         help="write the skill to stdout instead of installing it")
    install.add_argument("--force", action="store_true", help="replace an existing skill")
    return parser


def _executor(args) -> Executor:
    """Build the executor whose view space the arguments are written in.

    `--space display` is the same thing with the scale pinned to 1, so there is one
    coordinate path rather than two.
    """
    from doppelhand import screen

    attached = screen.monitors()
    noted_edge, noted_monitor = session.recall(session.layout_of(attached))
    wanted = getattr(args, "monitor", None)
    if wanted is None:
        wanted = noted_monitor
    monitor = _pick_monitor(attached, wanted)

    if getattr(args, "space", "view") == "display":
        max_edge = max(monitor.size)
    else:
        max_edge = args.max_edge or noted_edge or DEFAULT_MAX_EDGE
    return Executor(max_edge=max_edge, monitor=monitor,
                    cursor=getattr(args, "cursor", True))


def _pick_monitor(attached: list, wanted):
    from doppelhand import screen

    if wanted in ("all", 0):
        return screen.virtual_monitor()
    if wanted in (None, "primary"):
        return next((m for m in attached if m.primary), attached[0])
    for monitor in attached:
        if monitor.index == wanted:
            return monitor
    raise DoppelhandError(f"there is no monitor {wanted}; "
                          f"attached: {[m.index for m in attached]}")


def _space(executor: Executor, args) -> dict:
    return {
        "monitor": executor.monitor.index,
        "view": list(executor.view_size),
        "display": list(executor.screen_size),
        "scale": round(executor.scale, 6),
        "space": getattr(args, "space", "view"),
    }


def cmd_shot(args, executor: Executor) -> dict:
    from doppelhand import screen

    out = Path(args.out or (session.state_dir() / "shot.png"))
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.region:
        image = fit(screen.grab(executor.crop_box(*args.region), executor.cursor),
                    executor.max_edge)
    else:
        image = executor.capture()
    image.save(out)

    payload = {"path": str(out), **_space(executor, args)}
    if args.region:
        # A crop has its own origin, so points read off it are not screen points.
        payload["region"] = list(args.region)
        payload["space"] = "region"
        payload["note"] = "read this image, do not take click coordinates from it"
    else:
        # The PNG is already on disk, so a failure to note the space cannot make this
        # a failed capture. It costs the caller a flag on the next command.
        payload["space_remembered"] = session.remember(
            executor.max_edge, executor.monitor.index,
            session.layout_of(screen.monitors()))
    payload["image"] = list(image.size)
    payload["cursor_drawn"] = executor.cursor
    return payload


def cmd_screen(args, executor: Executor) -> dict:
    from doppelhand import screen

    return {"monitors": [m.describe() for m in screen.monitors()],
            **_space(executor, args)}


def cmd_cursor(args, executor: Executor) -> dict:
    from doppelhand import inputs, screen

    x, y = inputs.cursor_position()
    on = next((m.index for m in screen.monitors()
               if m.origin[0] <= x < m.origin[0] + m.size[0]
               and m.origin[1] <= y < m.origin[1] + m.size[1]), None)
    return {"view": list(executor.to_view(x, y)), "display": [x, y],
            "monitor": executor.monitor.index, "pointer_on_monitor": on,
            "scale": round(executor.scale, 6)}


def cmd_click(args, executor: Executor) -> dict:
    if args.count == 1:
        member = f"{args.button}_click"
    elif args.count in (2, 3):
        if args.button != "left":
            raise DoppelhandError("only the left button has a double or triple click")
        member = "double_click" if args.count == 2 else "triple_click"
    else:
        raise DoppelhandError(f"count must be 1, 2 or 3, got {args.count}")
    executor.dispatch(member, {"coordinate": list(args.at), "text": args.modifiers})
    return {"action": member, "at": list(args.at)}


def cmd_move(args, executor: Executor) -> dict:
    executor.dispatch("mouse_move", {"coordinate": list(args.at)})
    return {"action": "mouse_move", "at": list(args.at)}


def cmd_drag(args, executor: Executor) -> dict:
    executor.dispatch("left_click_drag", {"start_coordinate": list(args.start),
                                          "coordinate": list(args.end),
                                          "text": args.modifiers})
    return {"action": "left_click_drag", "from": list(args.start), "to": list(args.end)}


def cmd_scroll(args, executor: Executor) -> dict:
    if args.amount < 1:
        # A negative amount reverses the wheel, which would contradict the direction
        # this command reports back.
        raise DoppelhandError(f"amount must be 1 or more, got {args.amount}")
    params = {"scroll_direction": args.direction, "scroll_amount": args.amount,
              "text": args.modifiers}
    if args.at:
        params["coordinate"] = list(args.at)
    executor.dispatch("scroll", params)
    return {"action": "scroll", "direction": args.direction, "amount": args.amount}


def cmd_type(args, executor: Executor) -> dict:
    executor.dispatch("type", {"text": args.text})
    return {"action": "type", "characters": len(args.text)}


def cmd_key(args, executor: Executor) -> dict:
    repeat = min(100, max(1, args.repeat))  # the toolset's own ceiling
    executor.dispatch("key", {"text": args.combo, "repeat": repeat})
    return {"action": "key", "combo": args.combo, "repeat": repeat}


def cmd_hold(args, executor: Executor) -> dict:
    executor.dispatch("hold_key", {"text": args.combo, "duration": args.seconds})
    return {"action": "hold_key", "combo": args.combo, "seconds": args.seconds}


def cmd_wait(args, executor: Executor) -> dict:
    executor.dispatch("wait", {"duration": args.seconds})
    return {"action": "wait", "seconds": args.seconds}


ACTIONS = {
    "shot": cmd_shot, "screen": cmd_screen, "cursor": cmd_cursor, "click": cmd_click,
    "move": cmd_move, "drag": cmd_drag, "scroll": cmd_scroll, "type": cmd_type,
    "key": cmd_key, "hold": cmd_hold, "wait": cmd_wait,
}


def cmd_install_skill(args) -> int:
    if args.show:
        print(skills.skill_text())
        return 0
    if not args.target and not args.dest:
        print(json.dumps({"ok": False, "error": "name a harness or pass --dest",
                          "known": sorted(skills.TARGETS)}))
        return 1
    path = skills.install(args.target, args.dest, args.force)
    print(json.dumps({"ok": True, "installed": str(path), "harness": args.target}))
    return 0


def cmd_run(args) -> int:
    import anthropic

    from doppelhand import screen
    from doppelhand.agent import DEFAULT_MODEL, Agent

    model = args.model or DEFAULT_MODEL

    def report(kind: str, detail: str) -> None:
        if args.quiet:
            return
        marks = {"step": "--", "act": "->", "say": "  "}
        print(f"{marks.get(kind, '  ')} {detail}", flush=True)

    try:
        # Picking the display can fail on a bad --monitor, so it belongs with the rest
        # of the run's error handling rather than above it.
        executor = Executor(max_edge=args.max_edge,
                            monitor=_pick_monitor(screen.monitors(), args.monitor))
        if not args.yes and not _confirm(executor, model, args):
            print("cancelled")
            return 1
        agent = Agent(model=model, executor=executor, max_steps=args.max_steps,
                      on_event=report)
        answer = agent.run(args.task)
    except anthropic.AnthropicError as exc:
        print(f"doppelhand: {exc}", file=sys.stderr)
        return 1
    except TypeError as exc:
        # The SDK reports missing credentials as a TypeError when it builds the request.
        if "authentication" not in str(exc).lower():
            raise
        print("doppelhand: no Anthropic credentials found. Set ANTHROPIC_API_KEY.",
              file=sys.stderr)
        return 1
    except Aborted as exc:
        print(f"doppelhand: stopped, {exc}", file=sys.stderr)
        return 130
    except StepLimit as exc:
        print(f"doppelhand: {exc}", file=sys.stderr)
        return 2
    except Refused as exc:
        print(f"doppelhand: {exc}", file=sys.stderr)
        return 3
    except DoppelhandError as exc:
        print(f"doppelhand: {exc}", file=sys.stderr)
        return 1

    if answer:
        print(answer)
    return 0


def _confirm(executor: Executor, model: str, args) -> bool:
    width, height = executor.view_size
    print(f"doppelhand {__version__}")
    print(f"  task    {args.task}")
    print(f"  model   {model}")
    print(f"  screen  monitor {executor.monitor.index}, "
          f"{executor.screen_size[0]}x{executor.screen_size[1]} "
          f"-> {width}x{height} sent to the model")
    print(f"  budget  {args.max_steps} steps")
    print("This takes over the mouse and keyboard of this machine. "
          "Hold Escape at any point to stop it.")
    try:
        return input("Start? [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def main(argv: list[str] | None = None) -> int:
    _use_utf8()
    args = build_parser().parse_args(argv)

    if args.command == "run":
        return cmd_run(args)
    try:
        if args.command == "install-skill":
            return cmd_install_skill(args)
        payload = ACTIONS[args.command](args, _executor(args))
    except DoppelhandError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    except OSError as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps({"ok": True, **payload}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
