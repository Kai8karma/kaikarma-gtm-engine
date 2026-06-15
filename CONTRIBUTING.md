# Contributing

## Smoke gate

Before anything merges, the regression guard must pass:

```bash
bash tests/smoke.sh
```

This exits 0 on success and fails loudly otherwise. Nothing ships unless this gate is green.

## Running tests

Two paths are supported — pick whichever suits your workflow.

**stdlib runner (canonical)**

```bash
bash tests/smoke.sh
```

Runs every pillar demo and test file directly with `python3`. No dependencies
beyond a working Python 3.11+ install. This is what CI uses and what `make
test` (alias: `make smoke`) calls.

**pytest path (optional, contributor convenience)**

```bash
pytest
```

`pyproject.toml` sets `pythonpath` so pytest can discover modules across the
numbered pillar directories without any extra `sys.path` wiring on your part.
You need `pytest` installed (`pip install pytest`) — it is not a declared
dependency of the project. All other rules (stdlib-only logic, no external
deps) still apply.

Both paths must exit 0 before a PR is ready for review.

## House pattern for adding a pillar

Each pillar lives in a numbered directory (`NN-<name>/`) and follows this exact layout:

```
NN-name/
  __init__.py        # empty or absent — no package machinery needed
  conftest.py        # empty file — pytest discovery hook, always present
  name_schema.py     # @dataclass typed primitives only; no logic
  name_logic.py      # the engine; `if __name__ == "__main__"` demo at bottom
  test_name.py       # stdlib unittest.TestCase + unittest.main(verbosity=2)
```

### Rules

1. **`from __future__ import annotations`** at the top of every `.py` file.
2. **`*_schema.py`** — typed `@dataclass` primitives only. No functions, no I/O.
3. **Logic module** — pure functions, deterministic, stdlib only (no `pip` deps — this repo is air-gapped-positioned). Always includes an `if __name__ == "__main__"` demo that runs without arguments.
4. **`test_*.py`** — one `unittest.TestCase` subclass; guard with `if __name__ == "__main__": unittest.main(verbosity=2)`.
5. **`conftest.py`** — empty file, must exist for pytest path resolution.
6. **No runtime deps.** `pyproject.toml` lists zero dependencies intentionally.

### Adding a smoke line

After creating your pillar, add two lines to `tests/smoke.sh` — one for the demo, one for the tests:

```bash
echo
echo "▶ <name> demo"
"$PY" NN-name/name_logic.py

echo
echo "▶ <name> tests"
"$PY" NN-name/test_name.py
```

### Verification gate

A PR is only ready to merge when:

1. `bash tests/smoke.sh` exits 0 locally.
2. The CI matrix (Python 3.11 / 3.12 / 3.13) is green on GitHub Actions.

No exceptions. If the smoke gate is red, fix it before requesting review.
