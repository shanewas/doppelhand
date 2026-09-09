# doppelhand

A double of you at the keyboard. doppelhand captures the Windows screen, hands it to Claude, and carries out what comes back — moving the mouse, clicking, dragging, scrolling and typing the way a person would.

It is the local half of Claude's computer-use toolset: the model decides, doppelhand acts.

## Install

```
pip install doppelhand
export ANTHROPIC_API_KEY=sk-ant-...
```

Windows only, Python 3.10 or newer. The only dependencies are the Anthropic SDK and Pillow; screen capture and input go straight through the Win32 API.

## Use

```
doppelhand run "open the calculator and work out 19% of 4,320"
doppelhand shot desktop.png          # capture only, no API call, no key needed
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
4. `agent.py` runs the loop: send the screen, execute the actions in the reply, send the result, repeat.

Costs are kept down two ways: one prompt-cache breakpoint moves along with the newest tool result, and screenshots older than the last ten are dropped from the history in batches.

## Limits in 1.0.0

- Primary display only. A second monitor is not captured and cannot be clicked.
- Actions are run against the display as a whole; there is no per-window targeting.
- The Escape stop is checked between actions, so it takes effect once the action in flight finishes.
- The agent loop is covered by tests against a scripted client, not by a recorded live run.

## Safety

This program moves your real mouse and types on your real keyboard. It can click anything you can click. Run it on a machine where that is acceptable, watch what it does, and keep a hand near Escape.

## Development

```
pip install -e ".[dev]"
pytest tests -q
```

## License

MIT
