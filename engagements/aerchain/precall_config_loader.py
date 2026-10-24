"""Aerchain engagement config loader — precall_config.json.

Loads and validates the client-specific parameters that
06-precall-intelligence-engine/ needs at runtime (calendar mailbox, internal
domain allowlist, trigger mode, error-alert routing). Per CLAUDE.md governance:
these values are JSON, never hardcoded into the engine code, and never bleed
into another engagement's folder.

    python3 engagements/aerchain/precall_config_loader.py        # demo
    python3 engagements/aerchain/test_precall_config_loader.py   # tests

Stdlib only, no network. Safe to run air-gapped.
"""

from __future__ import annotations

import json
from pathlib import Path

_REQUIRED: frozenset[str] = frozenset(
    {
        "engagement",
        "hubspot_portal_id",
        "calendar_email",
        "internal_domains",
        "trigger_mode",
        "catchup_threshold_hours",
        "claude_model_tier",
        "error_alert_email",
        "hubspot_briefing_property",
    }
)
_VALID_TRIGGER_MODES: frozenset[str] = frozenset({"daily_sweep", "hybrid"})


def _load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(f"config file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _validate(cfg: dict, path: Path) -> None:
    missing = _REQUIRED - cfg.keys()
    if missing:
        raise ValueError(f"{path}: missing keys {sorted(missing)}")

    if cfg["trigger_mode"] not in _VALID_TRIGGER_MODES:
        raise ValueError(
            f"{path}: trigger_mode must be one of {sorted(_VALID_TRIGGER_MODES)}, "
            f"got {cfg['trigger_mode']!r}"
        )

    if not cfg["internal_domains"]:
        raise ValueError(f"{path}: internal_domains must not be empty")

    if cfg["catchup_threshold_hours"] <= 0:
        raise ValueError(f"{path}: catchup_threshold_hours must be positive")


def load_precall_config(directory: str | Path) -> dict:
    """Load and validate precall_config.json from an engagement directory.

    Returns the parsed dict (with ``internal_domains`` still a JSON list —
    callers pass ``frozenset(cfg["internal_domains"])`` into calendar_parser).

    Raises:
        FileNotFoundError: if the file is missing.
        ValueError: if required keys are absent or values are invalid.
    """
    path = Path(directory) / "precall_config.json"
    cfg = _load_json(path)
    _validate(cfg, path)
    return cfg


if __name__ == "__main__":
    target = Path(__file__).parent
    print(f"Loading Aerchain precall config from: {target}\n")

    cfg = load_precall_config(target)
    print(f"Engagement       : {cfg['engagement']}")
    print(f"HubSpot portal   : {cfg['hubspot_portal_id']}")
    print(f"Calendar mailbox : {cfg['calendar_email']}")
    print(f"Internal domains : {cfg['internal_domains']}")
    print(f"Trigger mode     : {cfg['trigger_mode']}")
    print(f"Catch-up window  : {cfg['catchup_threshold_hours']}h")
    print(f"Claude model     : {cfg['claude_model_tier']}")
    print(f"Error alerts to  : {cfg['error_alert_email']}")

    if cfg.get("pending_decisions"):
        print("\nPending decisions (not yet confirmed by the client team):")
        for item in cfg["pending_decisions"]:
            print(f"  - {item}")

    print("\nOK — config loaded and validated.")
