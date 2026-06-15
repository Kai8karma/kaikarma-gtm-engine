# Contributing

## Smoke gate

Before anything merges, the regression guard must pass:

```bash
bash tests/smoke.sh
```

This exits 0 on success and fails loudly otherwise. Nothing ships unless this gate is green.

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
