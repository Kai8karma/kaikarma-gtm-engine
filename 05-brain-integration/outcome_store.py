"""Persistent outcome log — append/load Outcomes to a local JSON file.

    python3 05-brain-integration/outcome_store.py        # demo

Stdlib only, no network, no external DB.  The state file lives at:
    05-brain-integration/_state/outcomes.json

The directory is created on first write; the file grows as a JSON array
(pretty-printed for human auditability).  Concurrent writes from multiple
processes are not guarded — single-writer model assumed (same as the rest
of the engine).

Can later sync to an external brain DB (e.g. kai-brain.db) but does not
require one — the pillar runs fully air-gapped.
"""

from __future__ import annotations

import json
from pathlib import Path

from brain_schema import Outcome

# Default path — relative to this file so the pillar is self-contained.
_DEFAULT_PATH = Path(__file__).parent / "_state" / "outcomes.json"


def log_outcome(outcome: Outcome, path: Path = _DEFAULT_PATH) -> None:
    """Append one Outcome to the JSON store, creating the file if missing."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_raw(path)
    existing.append(_to_dict(outcome))

    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_outcomes(path: Path = _DEFAULT_PATH) -> list[Outcome]:
    """Return all Outcomes from the JSON store, oldest first."""
    raw = _read_raw(Path(path))
    return [_from_dict(r) for r in raw]


# ── private helpers ──────────────────────────────────────────────────────────

def _read_raw(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return json.loads(text)


def _to_dict(o: Outcome) -> dict:
    return {
        "entity_type": o.entity_type,
        "key": o.key,
        "verdict": o.verdict,
        "confidence": o.confidence,
        "note": o.note,
    }


def _from_dict(d: dict) -> Outcome:
    return Outcome(
        entity_type=d["entity_type"],
        key=d["key"],
        verdict=d["verdict"],
        confidence=float(d.get("confidence", 0.7)),
        note=d.get("note", ""),
    )


# ── demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "outcomes.json"
        samples = [
            Outcome("icp_dimension", "firmographic", "win",
                    note="tier-A SaaS closed 3/5 — industry signal solid"),
            Outcome("icp_dimension", "signal", "loss",
                    confidence=0.6, note="job_change signal didn't predict close"),
            Outcome("perf_threshold", "scale_when_ratio_below", "neutral"),
        ]
        for o in samples:
            log_outcome(o, store)

        loaded = load_outcomes(store)
        print(f"Logged {len(loaded)} outcomes:\n")
        for o in loaded:
            print(f"  [{o.verdict:7s}] {o.entity_type}.{o.key}"
                  f"  conf={o.confidence}  note={o.note!r}")
