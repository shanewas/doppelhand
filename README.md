# doppelhand

A double of you at the keyboard. doppelhand captures the Windows screen and drives the mouse and keyboard: clicking, dragging, scrolling and typing the way a person would.

Use it two ways. Give an AI agent you already have eyes and hands, so it looks at your desktop with its own model and acts through doppelhand. Or let doppelhand drive itself with Claude, using its own key.

## Install

```
pip install git+https://github.com/shanewas/doppelhand
```

Not on PyPI yet.

Windows only, Python 3.10 or newer. The only dependencies are the Anthropic SDK and Pillow; screen capture and input go straight through the Win32 API.

## Give your agent hands

Install the skill into whichever harness you use, and it learns the loop by itself:

```
doppelhand install-skill claude-code
doppelhand install-skill opencode
doppelhand install-skill agy               # global, ~/.gemini/config/skills
doppelhand install-skill agy-workspace     # this project's .agents/skills
doppelhand install-skill --dest path/to/skills/doppelhand   # anything else
doppelhand install-skill --print           # read it first
```

No API key is involved. The agent takes a screenshot, reads the PNG with its own image tool, and calls back with coordinates. Every command answers with one JSON object and exits non-zero when the action did not happen.

```
$ doppelhand shot
{"ok": true, "path": "C:\\Users\\you\\AppData\\Local\\doppelhand\\shot.png",
 "view": [1280, 720], "display": [1920, 1080], "scale": 0.666667, "space": "view"}

$ doppelhand click 640,360
{"ok": true, "action": "left_click", "at": [640, 360]}
```

| Command | |
|---|---|
| `shot [PATH] [--region X,Y,W,H] [--monitor N]` | capture, write a PNG, report the coordinate space |
| `screen` | list the displays and report the coordinate space |
| `click X,Y [--button] [--count] [--modifiers]` | click, double click, right click |
| `move X,Y` / `drag X1,Y1 X2,Y2` | move the pointer, or press and drag |
| `scroll up\|down\|left\|right [N] [--at X,Y]` | scroll |
| `type "text"` / `key "ctrl+s" [--repeat N]` | type text, press a combination |
| `hold "shift" 2` / `wait 1.5` | hold a key, or pause |
| `cursor` | where the pointer is, in both spaces |

Coordinates are the pixels of the screenshot, not of the display; doppelhand scales them back up. A point outside that view is refused rather than clamped, so a scale mistake fails loudly instead of clicking a corner. Pass `--space display` if you already have real display pixels.

Every display is addressable. `screen` lists them numbered left to right, `--monitor N` picks one, and `--monitor all` captures the lot as a single wide image. Each display has its own view space starting at 0,0, so coordinates never go negative. The display and size of the last shot are remembered, so the next command lands in the same space without repeating flags; rearranging or unplugging a monitor discards that memory rather than misplacing a click.

Screenshots include the mouse pointer, which a GDI capture leaves out by default. Turn it off with `shot --no-cursor`.

## Real time

A fresh process costs about 300ms before it does anything, which dominates a session of
many small actions. Run a server once and talk to it over loopback instead:

```
doppelhand serve
```

It prints a port and a secret, and writes both to `%LOCALAPPDATA%\doppelhand\serve.json`.
Reads are GET, anything that moves the pointer or types is POST, and arguments keep the
names the command line uses:

```
curl -sH "X-Doppelhand-Token: $TOKEN" "http://127.0.0.1:$PORT/shot?fast=1"
curl -sXPOST -H "X-Doppelhand-Token: $TOKEN" "http://127.0.0.1:$PORT/click?at=640,360"
```

One run of `python bench/benchmark.py` on a three-monitor desktop. The spawned column
moves a lot with what the machine is doing, so re-measure rather than trusting these:

| action | spawned | served | |
|---|---|---|---|
| `cursor` | 309 ms | 5.6 ms | 55× |
| `screen` | 262 ms | 5.3 ms | 49× |
| `move` | 262 ms | 5.9 ms | 44× |
| `shot` | 430 ms | 77 ms | 5.5× |
| `shot --fast` | 378 ms | 30 ms | 12× |

Most of the screenshot gain comes from capturing through DXGI Desktop Duplication, which
hands over the frame the compositor already holds. Opening one costs more than a whole
GDI capture, so it only pays inside the server; one-shot commands keep the GDI path, and
so does any display that refuses to be duplicated. Every shot reports which it used in
`source`.

The server binds to loopback only, needs the secret from that file, and turns away any
request that carries browser headers or names a host other than loopback.

## Or let it drive itself

This is the only path that calls the Anthropic API, and the only one that needs a key.

```
export ANTHROPIC_API_KEY=sk-ant-...
doppelhand run "open the calculator and work out 19% of 4,320"
```

`run` prints what it is about to do and waits for confirmation. **Hold Escape at any point to stop the run** — the key is checked before every action.

```
--max-steps N    model turns before giving up (default 30)
--max-edge N     long edge of the screenshots sent to the model (default 1280)
--model NAME     defaults to claude-opus-5
-y               skip the confirmation
-q               print only the final answer
```

As a library:

```python
from doppelhand.agent import Agent

print(Agent(max_steps=10).run("close the notification in the corner"))
```

## How it works

1. `screen.py` captures the primary display through GDI `BitBlt` and hands back a Pillow image.
2. `executor.py` shrinks that image to a 1280-pixel long edge, and scales every coordinate the model returns back up to real pixels.
3. `inputs.py` drives the mouse and keyboard with `SendInput`. Text is typed as Unicode, so it does not depend on the active keyboard layout.
4. `cli.py` exposes each of those actions as a command, or `agent.py` runs the whole loop against Claude: send the screen, execute the actions in the reply, send the result, repeat.

In the built-in loop, costs are kept down two ways: one prompt-cache breakpoint moves along with the newest tool result, and screenshots older than the last ten are dropped from the history in batches.

## Limits in 1.2.0

- Actions are run against a display as a whole; there is no per-window targeting.
- Displays are addressed one at a time. `--monitor all` captures them together but scales the result down too far to read.
- The Escape stop applies to `run`, which checks it before each action. Single commands have already finished by the time you could press anything.
- The built-in loop is covered by tests against a scripted client, not by a recorded live run.

## Safety

This program moves your real mouse and types on your real keyboard. It can click anything you can click. Run it on a machine where that is acceptable, watch what it does, and keep a hand near Escape.

## Development

```
pip install -e ".[dev]"
pytest tests -q
```

## License

MIT
