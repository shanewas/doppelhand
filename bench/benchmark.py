"""Measure doppelhand two ways: a fresh process per command, and a warm server.

    python bench/benchmark.py

Starts its own server on a spare port, runs each action both ways, prints a table.
Numbers move with what the desktop is doing, so run it twice before believing a change.
"""

from __future__ import annotations

import http.client
import json
import statistics
import subprocess
import sys
import time

TOKEN = "benchmark"


def spawned(argv, rounds=5):
    times = []
    for _ in range(rounds):
        start = time.perf_counter()
        subprocess.run(argv, capture_output=True)
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def served(port, method, path, rounds=15):
    times = []
    for _ in range(rounds):
        start = time.perf_counter()
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        connection.request(method, path, headers={"X-Doppelhand-Token": TOKEN})
        answer = json.loads(connection.getresponse().read())
        connection.close()
        times.append((time.perf_counter() - start) * 1000)
        if not answer.get("ok"):
            raise SystemExit(f"{path} failed: {answer}")
    return statistics.median(times), answer


CASES = [
    ("cursor", ["doppelhand", "cursor"], "GET", "/cursor"),
    ("screen", ["doppelhand", "screen"], "GET", "/screen"),
    ("move", ["doppelhand", "move", "640,360"], "POST", "/move?at=640,360"),
    ("shot", ["doppelhand", "shot"], "GET", "/shot"),
    ("shot --fast", ["doppelhand", "shot", "--fast"], "GET", "/shot?fast=1"),
]


def main() -> int:
    port = 5677
    server = subprocess.Popen(["doppelhand", "serve", "--port", str(port),
                               "--token", TOKEN, "-q"])
    try:
        for _ in range(50):
            try:
                served(port, "GET", "/health", rounds=1)
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise SystemExit("the server never came up")

        served(port, "GET", "/shot", rounds=2)  # let the duplication warm up
        print(f"{'action':14}{'spawned':>12}{'served':>10}{'speedup':>10}")
        for label, argv, method, path in CASES:
            one_shot = spawned(argv)
            warm, answer = served(port, method, path)
            print(f"{label:14}{one_shot:10.1f}ms{warm:8.1f}ms{one_shot / warm:9.1f}x")
        print(f"\nframes came from: {answer.get('source', 'n/a')}")
    finally:
        server.terminate()
        server.wait(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
