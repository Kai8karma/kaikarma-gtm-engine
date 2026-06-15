"""Tests for the engagement config loader.

    python3 engagements/_TEMPLATE/test_config.py

Validates that the three example configs in _TEMPLATE parse correctly and that
all structural invariants hold.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Allow running from anywhere.
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import load_engagement

TEMPLATE_DIR = Path(__file__).parent


class TestICPConfig(unittest.TestCase):
    """icp-config.json parses and satisfies ICPProfile invariants."""

    def setUp(self) -> None:
        self.cfg = load_engagement(TEMPLATE_DIR)
        self.icp = self.cfg["icp"]

    def test_required_keys_present(self) -> None:
        for key in ("name", "target_industries", "employee_min", "employee_max",
                    "target_tech", "weights"):
            with self.subTest(key=key):
                self.assertIn(key, self.icp)

    def test_weights_sum_to_100(self) -> None:
        total = sum(self.icp["weights"].values())
        self.assertEqual(total, 100)

    def test_employee_range_valid(self) -> None:
        self.assertLessEqual(self.icp["employee_min"], self.icp["employee_max"])

    def test_target_industries_is_list(self) -> None:
        self.assertIsInstance(self.icp["target_industries"], list)
        self.assertGreater(len(self.icp["target_industries"]), 0)

    def test_target_tech_is_list(self) -> None:
        self.assertIsInstance(self.icp["target_tech"], list)

    def test_weights_keys_match_schema_defaults(self) -> None:
        expected = {"firmographic", "technographic", "signal", "fit"}
        self.assertEqual(set(self.icp["weights"].keys()), expected)


class TestChannelsConfig(unittest.TestCase):
    """channels.json parses and satisfies channel invariants."""

    def setUp(self) -> None:
        self.cfg = load_engagement(TEMPLATE_DIR)
        self.channels = self.cfg["channels"]

    def test_required_top_level_keys(self) -> None:
        for key in ("channels", "account_daily_cap"):
            with self.subTest(key=key):
                self.assertIn(key, self.channels)

    def test_account_daily_cap_positive(self) -> None:
        self.assertGreater(self.channels["account_daily_cap"], 0)

    def test_at_least_one_channel(self) -> None:
        self.assertGreater(len(self.channels["channels"]), 0)

    def test_channel_items_have_required_keys(self) -> None:
        for ch in self.channels["channels"]:
            for key in ("name", "daily_spend_cap", "target_cpa"):
                with self.subTest(channel=ch.get("name"), key=key):
                    self.assertIn(key, ch)

    def test_channel_cpas_positive(self) -> None:
        for ch in self.channels["channels"]:
            with self.subTest(channel=ch["name"]):
                self.assertGreater(ch["target_cpa"], 0)

    def test_channel_spend_caps_non_negative(self) -> None:
        for ch in self.channels["channels"]:
            with self.subTest(channel=ch["name"]):
                self.assertGreaterEqual(ch["daily_spend_cap"], 0)


class TestSLAConfig(unittest.TestCase):
    """sla.json parses and matches RoutingPolicy shape."""

    def setUp(self) -> None:
        self.cfg = load_engagement(TEMPLATE_DIR)
        self.sla = self.cfg["sla"]

    def test_required_top_level_keys(self) -> None:
        for key in ("tier_map", "signal_escalates", "instant_alert_sla_minutes"):
            with self.subTest(key=key):
                self.assertIn(key, self.sla)

    def test_all_four_tiers_present(self) -> None:
        for tier in ("A", "B", "C", "D"):
            with self.subTest(tier=tier):
                self.assertIn(tier, self.sla["tier_map"])

    def test_tier_policies_have_required_keys(self) -> None:
        for tier, policy in self.sla["tier_map"].items():
            for key in ("destination", "sla_minutes"):
                with self.subTest(tier=tier, key=key):
                    self.assertIn(key, policy)

    def test_sla_minutes_non_negative(self) -> None:
        for tier, policy in self.sla["tier_map"].items():
            with self.subTest(tier=tier):
                self.assertGreaterEqual(policy["sla_minutes"], 0)

    def test_instant_alert_sla_non_negative(self) -> None:
        self.assertGreaterEqual(self.sla["instant_alert_sla_minutes"], 0)

    def test_signal_escalates_is_bool(self) -> None:
        self.assertIsInstance(self.sla["signal_escalates"], bool)

    def test_a_tier_sla_faster_than_b(self) -> None:
        """A-tier should be routed faster than B (lower sla_minutes)."""
        a_sla = self.sla["tier_map"]["A"]["sla_minutes"]
        b_sla = self.sla["tier_map"]["B"]["sla_minutes"]
        self.assertLess(a_sla, b_sla)

    def test_instant_alert_faster_than_a_tier(self) -> None:
        a_sla = self.sla["tier_map"]["A"]["sla_minutes"]
        instant = self.sla["instant_alert_sla_minutes"]
        self.assertLess(instant, a_sla)


class TestLoadEngagementValidation(unittest.TestCase):
    """Validation errors are raised for malformed configs."""

    def _write_configs(self, tmp: Path, icp: dict, channels: dict, sla: dict) -> None:
        (tmp / "icp-config.json").write_text(json.dumps(icp), encoding="utf-8")
        (tmp / "channels.json").write_text(json.dumps(channels), encoding="utf-8")
        (tmp / "sla.json").write_text(json.dumps(sla), encoding="utf-8")

    def _valid_icp(self) -> dict:
        return {
            "name": "Test ICP",
            "target_industries": ["saas"],
            "employee_min": 50,
            "employee_max": 500,
            "target_tech": ["hubspot"],
            "weights": {"firmographic": 40, "technographic": 20, "signal": 30, "fit": 10},
        }

    def _valid_channels(self) -> dict:
        return {
            "channels": [{"name": "li", "daily_spend_cap": 100.0, "target_cpa": 50.0}],
            "account_daily_cap": 200.0,
        }

    def _valid_sla(self) -> dict:
        return {
            "tier_map": {
                "A": {"destination": "ae_queue", "sla_minutes": 60},
                "B": {"destination": "sdr_sequence", "sla_minutes": 240},
                "C": {"destination": "nurture", "sla_minutes": 1440},
                "D": {"destination": "disqualified", "sla_minutes": 0},
            },
            "signal_escalates": True,
            "instant_alert_sla_minutes": 5,
        }

    def test_weights_not_summing_to_100_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            icp = self._valid_icp()
            icp["weights"]["firmographic"] = 99  # sum = 159
            self._write_configs(tmp, icp, self._valid_channels(), self._valid_sla())
            with self.assertRaises(ValueError):
                load_engagement(tmp)

    def test_missing_icp_key_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            icp = self._valid_icp()
            del icp["employee_min"]
            self._write_configs(tmp, icp, self._valid_channels(), self._valid_sla())
            with self.assertRaises(ValueError):
                load_engagement(tmp)

    def test_missing_sla_tier_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            sla = self._valid_sla()
            del sla["tier_map"]["D"]
            self._write_configs(tmp, self._valid_icp(), self._valid_channels(), sla)
            with self.assertRaises(ValueError):
                load_engagement(tmp)

    def test_missing_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                load_engagement(td)


if __name__ == "__main__":
    unittest.main(verbosity=2)
