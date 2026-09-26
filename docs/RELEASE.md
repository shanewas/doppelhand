# Release checklist

Bump, gate, tag, publish. Every step runs on the Windows box unless noted.

## 1. Bump

- Edit one line: `__version__` in `src/doppelhand/__init__.py`.
  `pyproject.toml` reads it dynamically — nothing else carries the version.
- Add a `CHANGELOG.md` entry at the top. Keep it to what changed and why.
- Version rules: patch = fixes only, minor = new feature, major = breaking.

## 2. Gate

- `py -m pytest` from repo root — must be green on Windows (Linux run is
  advisory: Win32 paths are faked there).
- `doppelhand --version` prints the new version.
- `python -m build` then `twine check dist/*` — sdist + wheel build clean.
- `bench/benchmark.py` output matches the locked table (see step 5 notes in repo).

## 3. Tag

- `git tag v<version>` on the release commit, e.g. `git tag v1.3.2`.
- Push commit then tag: `git push origin main && git push origin v<version>`.

## 4. Publish

- `twine upload dist/*` (needs a PyPI API token, `__token__` user).
- Confirm the PyPI page shows the new version and README renders.
- Sync the installed skill copy outside the repo
  (`%USERPROFILE%\.agents\skills\doppelhand\SKILL.md`) with
  `src/doppelhand/skill/SKILL.md` — it is not tracked by git and goes stale.
