"""Engagement config loader — reads and validates the three engagement JSONs.

Loads icp-config.json, channels.json, and sla.json from an engagement directory
and returns a single merged dict. Validates that ICP weights sum to 100 and that
all required keys are present.

    python3 engagements/_TEMPLATE/config_loader.py        # demo
    python3 engagements/_TEMPLATE/test_config.py          # tests

Stdlib only, no network. Safe to run air-gapped.
"""

from __future__ import annotations

import json
from pathlib import Path


# Required top-level keys per config file.
_ICP_REQUIRED: frozenset[str] = frozenset(
    {"name", "target_industries", "employee_min", "employee_max", "target_tech", "weights"}
)
_CHANNELS_REQUIRED: frozenset[str] = frozenset({"channels", "account_daily_cap"})
_CHANNEL_ITEM_REQUIRED: frozenset[str] = frozenset({"name", "daily_spend_cap", "target_cpa"})
_SLA_REQUIRED: frozenset[str] = frozenset({"tier_map", "signal_escalates", "instant_alert_sla_minutes"})
_TIER_REQUIRED: frozenset[str] = frozenset({"destination", "sla_minutes"})
_VALID_TIERS: frozenset[str] = frozenset({"A", "B", "C", "D"})


def _load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(f"config file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _validate_icp(icp: dict, path: Path) -> None:
    missing = _ICP_REQUIRED - icp.keys()
    if missing:
        raise ValueError(f"{path}: missing keys {sorted(missing)}")

    weights: dict = icp["weights"]
    total = sum(weights.values())
    if total != 100:
        raise ValueError(
            f"{path}: weights must sum to 100, got {total} "
            f"(keys: {list(weights.keys())})"
        )

    if icp["employee_min"] > icp["employee_max"]:
        raise ValueError(
            f"{path}: employee_min ({icp['employee_min']}) "
            f"exceeds employee_max ({icp['employee_max']})"
        )


def _validate_channels(channels: dict, path: Path) -> None:
    missing = _CHANNELS_REQUIRED - channels.keys()
    if missing:
        raise ValueError(f"{path}: missing keys {sorted(missing)}")

    for i, ch in enumerate(channels["channels"]):
        ch_missing = _CHANNEL_ITEM_REQUIRED - ch.keys()
        if ch_missing:
            raise ValueError(f"{path}: channels[{i}] missing keys {sorted(ch_missing)}")

        if ch["daily_spend_cap"] < 0:
            raise ValueError(f"{path}: channels[{i}] daily_spend_cap must be non-negative")
        if ch["target_cpa"] <= 0:
            raise ValueError(f"{path}: channels[{i}] target_cpa must be positive")

    if channels["account_daily_cap"] <= 0:
        raise ValueError(f"{path}: account_daily_cap must be positive")


def _validate_sla(sla: dict, path: Path) -> None:
    missing = _SLA_REQUIRED - sla.keys()
    if missing:
        raise ValueError(f"{path}: missing keys {sorted(missing)}")

    tier_map: dict = sla["tier_map"]
    missing_tiers = _VALID_TIERS - tier_map.keys()
    if missing_tiers:
        raise ValueError(f"{path}: tier_map missing tiers {sorted(missing_tiers)}")

    for tier, policy in tier_map.items():
        tier_missing = _TIER_REQUIRED - policy.keys()
        if tier_missing:
            raise ValueError(
                f"{path}: tier_map[{tier!r}] missing keys {sorted(tier_missing)}"
            )
        if policy["sla_minutes"] < 0:
            raise ValueError(
                f"{path}: tier_map[{tier!r}] sla_minutes must be non-negative"
            )

    if sla["instant_alert_sla_minutes"] < 0:
        raise ValueError(f"{path}: instant_alert_sla_minutes must be non-negative")


def load_engagement(directory: str | Path) -> dict:
    """Load and validate all three engagement config JSONs.

    Returns a merged dict with keys ``icp``, ``channels``, and ``sla``.
    Raises ``FileNotFoundError`` if a file is missing, ``ValueError`` if
    validation fails.
    """
    base = Path(directory)
    icp = _load_json(base / "icp-config.json")
    channels = _load_json(base / "channels.json")
    sla = _load_json(base / "sla.json")

    _validate_icp(icp, base / "icp-config.json")
    _validate_channels(channels, base / "channels.json")
    _validate_sla(sla, base / "sla.json")

    return {"icp": icp, "channels": channels, "sla": sla}


if __name__ == "__main__":
    import sys

    target = Path(__file__).parent
    print(f"Loading engagement config from: {target}\n")

    cfg = load_engagement(target)

    icp = cfg["icp"]
    print(f"ICP:  {icp['name']}")
    print(f"      industries : {icp['target_industries']}")
    print(f"      employees  : {icp['employee_min']}–{icp['employee_max']}")
    print(f"      tech       : {icp['target_tech']}")
    print(f"      weights    : {icp['weights']}  (sum={sum(icp['weights'].values())})")

    print()
    ch = cfg["channels"]
    print(f"Channels (account cap ${ch['account_daily_cap']:.0f}/day):")
    for c in ch["channels"]:
        print(f"  {c['name']:20s}  cap ${c['daily_spend_cap']:.0f}/day  target CPA ${c['target_cpa']:.0f}")

    print()
    sla = cfg["sla"]
    print(f"SLA  (signal_escalates={sla['signal_escalates']}, instant={sla['instant_alert_sla_minutes']}m):")
    for tier in ("A", "B", "C", "D"):
        p = sla["tier_map"][tier]
        print(f"  {tier}  → {p['destination']:16s}  {p['sla_minutes']} min")

    print("\nOK — all configs loaded and validated.")
    sys.exit(0)
