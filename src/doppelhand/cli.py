"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from doppelhand import __version__
from doppelhand.errors import Aborted, DoppelhandError, Refused, StepLimit
from doppelhand.executor import DEFAULT_MAX_EDGE, Executor, fit


def _use_utf8() -> None:
    """Model output and window titles routinely contain characters the default Windows
    console encoding cannot represent, and printing one would end the run."""
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doppelhand",
        description="Read the Windows screen, drive the mouse and keyboard.",
    )
    parser.add_argument("--version", action="version", version=f"doppelhand {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="carry out a task on this desktop")
    run.add_argument("task", help="what to do, in plain language")
    run.add_argument("--model", default=None, help="Claude model to drive the run")
    run.add_argument("--max-steps", type=int, default=30, help="model turns before giving up")
    run.add_argument("--max-edge", type=int, default=DEFAULT_MAX_EDGE,
                     help="long edge of the screenshots sent to the model")
    run.add_argument("-y", "--yes", action="store_true", help="skip the confirmation")
    run.add_argument("-q", "--quiet", action="store_true", help="only print the final answer")

    shot = commands.add_parser("shot", help="save a screenshot and exit")
    shot.add_argument("path", nargs="?", default="screenshot.png")
    shot.add_argument("--max-edge", type=int, default=DEFAULT_MAX_EDGE)
    shot.add_argument("--full", action="store_true", help="save at the display's own size")
    return parser


def cmd_shot(args) -> int:
    from doppelhand import screen

    image = screen.grab()
    if not args.full:
        image = fit(image, args.max_edge)
    image.save(args.path)
    display_width, display_height = screen.screen_size()
    print(f"{args.path}  {image.width}x{image.height}  "
          f"(display {display_width}x{display_height})")
    return 0


def cmd_run(args) -> int:
    import anthropic

    from doppelhand.agent import DEFAULT_MODEL, Agent

    executor = Executor(max_edge=args.max_edge)
    model = args.model or DEFAULT_MODEL
    if not args.yes and not _confirm(executor, model, args):
        print("cancelled")
        return 1

    def report(kind: str, detail: str) -> None:
        if args.quiet:
            return
        marks = {"step": "--", "act": "->", "say": "  "}
        print(f"{marks.get(kind, '  ')} {detail}", flush=True)

    try:
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
    print(f"  screen  {executor.screen_size[0]}x{executor.screen_size[1]} "
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
    if args.command == "shot":
        return cmd_shot(args)
    return cmd_run(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
