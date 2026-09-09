---
name: doppelhand
description: Use when a task needs the Windows desktop itself rather than files or a browser - clicking a native application, reading a dialog that has no log, filling a GUI form, driving an installer, or checking what is on screen right now. Provides screenshots plus real mouse and keyboard control through the `doppelhand` command. Triggers - "click", "on my screen", "the dialog", "open the app", "type into", "what is on screen", "drive the GUI".
---

# doppelhand

`doppelhand` gives you eyes and hands on the Windows desktop. You supply the judgement: take a screenshot, look at it, decide, act, look again.

Every command prints one JSON object on stdout and exits non-zero if the action did not happen.

## The loop

1. `doppelhand shot` writes a PNG and tells you where it is.
2. Read that file with your own image tool.
3. Decide what to do, then run one action command using coordinates read off that screenshot.
4. Take another shot to confirm the screen changed the way you expected.

```
$ doppelhand shot
{"ok": true, "path": "C:\\Users\\you\\AppData\\Local\\doppelhand\\shot.png",
 "view": [1280, 720], "display": [1920, 1080], "scale": 0.6667, "space": "view"}
```

## Coordinates

**Use the pixel coordinates of the screenshot you were given.** The image is smaller than the real display, and `doppelhand` scales your coordinates back up. Never convert to display pixels yourself; if you have real display coordinates from somewhere else, pass `--space display` and they will be used as they are.

The `view` size in the JSON is the space you are working in. Its origin is the top left.

## Commands

| Command | What it does |
|---|---|
| `doppelhand shot` | Capture the display, write a PNG, print its path and the coordinate space |
| `doppelhand shot --region X,Y,W,H` | Capture one part of the screen, useful for reading small text |
| `doppelhand screen` | Report the coordinate space without capturing anything |
| `doppelhand click X,Y` | Left click. `--button right\|middle`, `--count 2` for a double click, `--modifiers ctrl+shift` |
| `doppelhand move X,Y` | Move the pointer without clicking, to reveal a hover state |
| `doppelhand drag X1,Y1 X2,Y2` | Press, drag and release |
| `doppelhand scroll down 3` | Scroll at the pointer. Directions are `up`, `down`, `left`, `right`. `--at X,Y` scrolls somewhere else |
| `doppelhand type "some text"` | Type literal text at the keyboard focus |
| `doppelhand key "ctrl+s"` | Press a key or combination. `--repeat N` presses it several times |
| `doppelhand hold "shift" 2` | Hold a key down for a number of seconds |
| `doppelhand wait 1.5` | Pause and let the screen settle |
| `doppelhand cursor` | Report where the pointer is, in both spaces |

Key names follow the X11 style the computer-use toolset uses: `Return`, `Escape`, `Tab`, `BackSpace`, `Delete`, `Up`, `Down`, `Left`, `Right`, `Home`, `End`, `Page_Up`, `Page_Down`, `F1` to `F24`, and combinations like `ctrl+s`, `alt+Tab`, `ctrl+shift+Escape`.

## Working well

Take a screenshot before your first action, always. The desktop is not where you left it.

Prefer keyboard routes over clicking when one exists. `key "ctrl+s"` beats hunting for a toolbar button, and the Start menu opens with `key "super"` then `type "notepad"` then `key "Return"`.

After clicking something that opens a window or a menu, wait briefly and take another shot before acting again. A click on a menu item that has not rendered yet lands on whatever was underneath.

When text is too small to read in the full screenshot, capture just that part with `--region` instead of guessing. A region shot comes back with `"space": "region"`, and its pixels start at the crop's own corner, so read it and then take your coordinates from a full shot.

If a command returns `"ok": false`, the action did not happen. Read the `error` field, fix the input and try again rather than moving on as though it worked.

## Care

This moves the user's real pointer and types on their real keyboard, on the machine they are sitting at. It can click anything they can click.

Ask before you start acting unless the user has already told you to go ahead. Say what you are about to do. Stay inside the task you were given; do not close windows, dismiss dialogs or save files that the task did not mention. If the screen is not what you expected, stop and describe what you see rather than clicking to find out.

The user can hold Escape to stop a `doppelhand run` at any time. Individual commands are single actions, so they finish immediately.

## Installing

`pip install git+https://github.com/shanewas/doppelhand`, then `doppelhand screen` to check it works. Windows only.
