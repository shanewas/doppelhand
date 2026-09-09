# Changelog

## 1.0.0 — 2026-09-09

First release.

- `doppelhand run "<task>"` drives the desktop from a plain-language instruction, using Claude's computer toolset.
- `doppelhand shot` saves a screenshot without calling the API.
- Screen capture through GDI and input through `SendInput`, with no capture or automation dependency.
- All seventeen toolset actions are carried out: screenshot, zoom, the five click kinds, drag, move, button down and up, cursor position, scroll, type, key, hold key and wait.
- Coordinates are scaled between screenshot pixels and display pixels, and the process declares per-monitor DPI awareness so the two agree on scaled displays.
- A run stops when Escape is held, when the step budget runs out, or when the model declines the task.
- Screenshot history is pruned in batches and a prompt-cache breakpoint follows the newest tool result.
