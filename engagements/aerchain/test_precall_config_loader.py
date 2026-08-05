"""Tests for the Aerchain precall config loader.

    python3 engagements/aerchain/test_precall_config_loader.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from precall_config_loader import load_precall_config

AERCHAIN_DIR = Path(__file__).parent

REQUIRED_KEYS = (
    "engagement",
    "hubspot_portal_id",
    "calendar_email",
    "internal_domains",
    "trigger_mode",
    "catchup_threshold_hours",
    "claude_model_tier",
    "error_alert_email",
    "hubspot_briefing_property",
)


class TestLoadPrecallConfig(unittest.TestCase):

    def setUp(self) -> None:
        self.cfg = load_precall_config(AERCHAIN_DIR)

    def test_required_keys_present(self) -> None:
        for key in REQUIRED_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, self.cfg)

    def test_trigger_mode_is_hybrid_per_sow_recommendation(self) -> None:
        self.assertEqual(self.cfg["trigger_mode"], "hybrid")

    def test_catchup_threshold_matches_sow(self) -> None:
        self.assertEqual(self.cfg["catchup_threshold_hours"], 48)

    def test_internal_domains_non_empty(self) -> None:
        self.assertTrue(self.cfg["internal_domains"])

    def test_pending_decisions_are_surfaced_not_hidden(self) -> None:
        """SOW Section 8 decisions 2 and 4 are not yet confirmed by the
        client team — the config must say so, not silently assume."""
        self.assertIn("pending_decisions", self.cfg)
        self.assertGreaterEqual(len(self.cfg["pending_decisions"]), 1)


class TestValidation(unittest.TestCase):

    def _write(self, tmpdir: str, payload: dict) -> None:
        with (Path(tmpdir) / "precall_config.json").open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def test_missing_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_precall_config(tmp)

    def test_missing_required_key_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, {"engagement": "x"})
            with self.assertRaises(ValueError):
                load_precall_config(tmp)

    def test_invalid_trigger_mode_raises(self) -> None:
        base = dict(load_precall_config(AERCHAIN_DIR))
        base["trigger_mode"] = "carrier_pigeon"
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, base)
            with self.assertRaises(ValueError):
                load_precall_config(tmp)

    def test_empty_internal_domains_raises(self) -> None:
        base = dict(load_precall_config(AERCHAIN_DIR))
        base["internal_domains"] = []
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, base)
            with self.assertRaises(ValueError):
                load_precall_config(tmp)

    def test_non_positive_catchup_threshold_raises(self) -> None:
        base = dict(load_precall_config(AERCHAIN_DIR))
        base["catchup_threshold_hours"] = 0
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, base)
            with self.assertRaises(ValueError):
                load_precall_config(tmp)

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (Path(tmp) / "precall_config.json").open("w", encoding="utf-8") as fh:
                fh.write("{not valid json")
            with self.assertRaises(ValueError):
                load_precall_config(tmp)


if __name__ == "__main__":
    unittest.main()
