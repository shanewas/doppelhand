# Changelog

## 1.3.1 — 2026-09-09

First release on PyPI: `pip install doppelhand`.

- The Anthropic SDK is no longer installed by default. Only `doppelhand run` talks to an API, so it moved to an extra: `pip install "doppelhand[run]"`. Running it without the SDK now says so instead of raising an import error. The floor is `anthropic>=0.124`, the first version carrying the computer-toolset types.
- A rotated display falls back to GDI capture. Desktop Duplication hands over the frame in the screen's native orientation, so a portrait monitor would have produced a sideways image whose coordinates disagreed with the desktop rectangle.
- The source archive now carries the whole test suite, the benchmark and the changelog, so a clean checkout can run what the repository runs.
- The warning about driving the real mouse and keyboard sits under Install, where someone arriving from the package page will see it.

## 1.3.0 — 2026-09-09

Built for driving a desktop in real time. An action costs about 6ms instead of 300, and a screenshot about 30ms instead of 400.

Measured first: a command that did no work at all cost ~400ms, of which ~300ms was Python starting and importing, while capturing the screen through GDI cost 150-775ms and varied wildly from call to call. Resizing and encoding, the parts that looked expensive, were never more than 50ms together.

- `doppelhand serve` holds one warm process open and answers the same actions over loopback HTTP. Reads are GET, anything that moves the pointer or types is POST, and the arguments keep the names the command line uses. The query string is turned back into a command line and handed to the same parser and the same functions, so the two surfaces cannot drift apart.
- Screens are captured through DXGI Desktop Duplication, which hands over the frame the compositor already holds instead of asking the system to read the screen back. Held open by the server, a capture costs microseconds rather than hundreds of milliseconds, and an unchanged screen costs nothing at all. Opening a duplication is expensive, so one-shot commands keep using GDI, and any display that refuses duplication falls back to it too.
- The pointer is composited onto duplicated frames, which arrive without one.
- `shot --fast` writes JPEG and resizes by box filter, roughly a third of the time for slightly softer text.
- A shot reports which path produced it in `source`.
- The argument parser is built once in a long-lived process, which was costing 13ms of every request.
- Usage errors return an exit code instead of raising, so a bad argument reads the same as any other failure.

The server binds to loopback only, requires a secret it writes to a file in the user's own profile, refuses any request carrying browser headers, and refuses any request whose Host is not loopback, which is what stops a web page reaching it by name.

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
