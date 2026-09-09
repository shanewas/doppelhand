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
| `shot [PATH] [--region X,Y,W,H]` | capture, write a PNG, report the coordinate space |
| `screen` | report the coordinate space without capturing |
| `click X,Y [--button] [--count] [--modifiers]` | click, double click, right click |
| `move X,Y` / `drag X1,Y1 X2,Y2` | move the pointer, or press and drag |
| `scroll up\|down\|left\|right [N] [--at X,Y]` | scroll |
| `type "text"` / `key "ctrl+s" [--repeat N]` | type text, press a combination |
| `hold "shift" 2` / `wait 1.5` | hold a key, or pause |
| `cursor` | where the pointer is, in both spaces |

Coordinates are the pixels of the screenshot, not of the display; doppelhand scales them back up. Pass `--space display` if you already have real display pixels. The size a shot was taken at is remembered, so a later click lands in the same space without repeating `--max-edge`.

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

## Limits in 1.1.0

- Primary display only. A second monitor is not captured and cannot be clicked.
- Actions are run against the display as a whole; there is no per-window targeting.
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
