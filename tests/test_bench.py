import importlib.util
from pathlib import Path


def load_benchmark():
    root = Path(__file__).parent.parent
    spec = importlib.util.spec_from_file_location(
        "doppelhand_benchmark", root / "bench" / "benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_benchmark_covers_all_five_cases():
    """A case dropped from CASES would silently stop measuring that action."""
    cases = load_benchmark().CASES
    assert [(label, method, path) for label, _argv, method, path in cases] == [
        ("cursor", "GET", "/cursor"),
        ("screen", "GET", "/screen"),
        ("move", "POST", "/move?at=640,360"),
        ("shot", "GET", "/shot"),
        ("shot --fast", "GET", "/shot?fast=1"),
    ]


def test_each_case_spawns_the_same_action_it_serves():
    """Spawned and served sides must measure the same action or the speedup lies."""
    for label, argv, method, path in load_benchmark().CASES:
        action = label.split()[0]
        assert argv[1] == action, label
        assert path.split("?")[0] == f"/{action}", label
        if method == "GET":
            assert action in {"cursor", "screen", "shot"}, label
