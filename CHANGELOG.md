# Changelog

## 1.2.0 — 2026-09-09

Every display is reachable, the pointer is visible, and a coordinate that misses now says so.

- A point outside the view is refused instead of being clamped to the nearest edge. Clamping meant a scale mistake clicked a screen corner and still reported success, which on Windows 11 is the show-desktop hotspot.
- Usage errors print the same JSON shape as every other failure, so a caller parsing stdout never has to fall back to reading argparse's prose. They exit 2, while a refused action exits 1.
- `screen` lists every display, numbered left to right. `--monitor N` picks one and `--monitor all` captures them as a single wide image. Each display has its own view space starting at 0,0, so coordinates stay positive whatever the desktop layout.
- Screenshots include the mouse pointer, composited in after the capture because a GDI copy never contains it. `shot --no-cursor` leaves it out.
- `cursor` reports which display the pointer is actually on, not just where it is in the current view.
- The display of the last shot is remembered along with its size. Moving or unplugging a monitor discards the memory instead of misplacing a click.
- Input refused by a background desktop is retried after attaching to the input desktop, sending only the events that did not get through.

## 1.1.0 — 2026-09-09

Any AI harness can now use doppelhand as its hands, with no API key and no second model.

- Each action is its own command: `shot`, `screen`, `click`, `move`, `drag`, `scroll`, `type`, `key`, `hold`, `wait` and `cursor`. They print one JSON object and exit non-zero when the action did not happen.
- `shot` writes a PNG and reports the coordinate space, so the calling agent reads the image with its own tools and answers in the pixels it saw.
- Coordinates default to the screenshot's space and are scaled back to the display. `--space display` passes real pixels straight through.
- The size of the last full screenshot is remembered, so a click after a `--max-edge` shot lands in the space that shot was taken in.
- `install-skill` drops a portable agent skill into Claude Code, opencode, AGY (global or workspace), or any directory given with `--dest`. `--print` writes it to stdout.
- `run` is unchanged and remains the only path that calls the Anthropic API.

## 1.0.0 — 2026-09-09

First release.

- `doppelhand run "<task>"` drives the desktop from a plain-language instruction, using Claude's computer toolset.
- `doppelhand shot` saves a screenshot without calling the API.
- Screen capture through GDI and input through `SendInput`, with no capture or automation dependency.
- All seventeen toolset actions are carried out: screenshot, zoom, the five click kinds, drag, move, button down and up, cursor position, scroll, type, key, hold key and wait.
- Coordinates are scaled between screenshot pixels and display pixels, and the process declares per-monitor DPI awareness so the two agree on scaled displays.
- A run stops when Escape is held, when the step budget runs out, or when the model declines the task.
- Screenshot history is pruned in batches and a prompt-cache breakpoint follows the newest tool result.
