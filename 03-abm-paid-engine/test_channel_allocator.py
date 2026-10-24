"""Tests for cross-channel budget allocation.

    python3 03-abm-paid-engine/test_channel_allocator.py
"""

from __future__ import annotations

import unittest

from channel_allocator import allocate_channel_budgets, cascade_to_campaigns, rollup_by_channel
from perf_schema import CUT, HOLD, SCALE, Campaign, PerfPolicy

CHANNEL_OF = {
    "LI-ABM-tier1": "linkedin", "LI-newtest": "linkedin",
    "Google-brand": "google",
    "Meta-broad": "meta", "Meta-retarget": "meta",
}

CAMPAIGNS = [
    Campaign("LI-ABM-tier1", spend=1200, conversions=40, daily_budget=150),
    Campaign("LI-newtest", spend=200, conversions=8, daily_budget=30),
    Campaign("Google-brand", spend=2000, conversions=40, daily_budget=200),
    Campaign("Meta-broad", spend=3200, conversions=40, daily_budget=200),
    Campaign("Meta-retarget", spend=120, conversions=0, daily_budget=20),
]

POLICY = PerfPolicy(target_cpa=50.0, account_daily_cap=100_000.0)


class TestRollupByChannel(unittest.TestCase):

    def test_aggregates_spend_and_conversions_per_channel(self):
        rows = {r.name: r for r in rollup_by_channel(CAMPAIGNS, CHANNEL_OF)}
        self.assertEqual(rows["linkedin"].spend, 1400)
        self.assertEqual(rows["linkedin"].conversions, 48)
        self.assertEqual(rows["linkedin"].daily_budget, 180)

    def test_single_campaign_channel_passes_through(self):
        rows = {r.name: r for r in rollup_by_channel(CAMPAIGNS, CHANNEL_OF)}
        self.assertEqual(rows["google"].spend, 2000)
        self.assertEqual(rows["google"].conversions, 40)

    def test_meta_channel_sums_both_campaigns(self):
        rows = {r.name: r for r in rollup_by_channel(CAMPAIGNS, CHANNEL_OF)}
        self.assertEqual(rows["meta"].spend, 3320)
        self.assertEqual(rows["meta"].conversions, 40)
        self.assertEqual(rows["meta"].daily_budget, 220)

    def test_unmapped_campaign_raises(self):
        with self.assertRaises(KeyError):
            rollup_by_channel([Campaign("Unmapped", 100, 5, 50)], CHANNEL_OF)

    def test_three_channels_produced(self):
        rows = rollup_by_channel(CAMPAIGNS, CHANNEL_OF)
        self.assertEqual({r.name for r in rows}, {"linkedin", "google", "meta"})


class TestAllocateChannelBudgets(unittest.TestCase):

    def test_linkedin_scales_on_strong_cpa(self):
        actions = allocate_channel_budgets(CAMPAIGNS, CHANNEL_OF, POLICY)
        by_channel = {a.campaign: a for a in actions}
        # linkedin blended cpa = 1400/48 = 29.2 -> 58% of target -> SCALE
        self.assertEqual(by_channel["linkedin"].verdict, SCALE)

    def test_google_holds_on_target(self):
        actions = allocate_channel_budgets(CAMPAIGNS, CHANNEL_OF, POLICY)
        by_channel = {a.campaign: a for a in actions}
        self.assertEqual(by_channel["google"].verdict, HOLD)

    def test_meta_cuts_on_weak_blended_cpa(self):
        actions = allocate_channel_budgets(CAMPAIGNS, CHANNEL_OF, POLICY)
        by_channel = {a.campaign: a for a in actions}
        # meta blended cpa = 3320/40 = 83 -> 166% of target -> CUT
        self.assertEqual(by_channel["meta"].verdict, CUT)

    def test_total_cap_enforced_across_channels(self):
        tight_policy = PerfPolicy(target_cpa=50.0, account_daily_cap=300.0)
        actions = allocate_channel_budgets(CAMPAIGNS, CHANNEL_OF, tight_policy)
        self.assertLessEqual(sum(a.new_budget for a in actions), 300.0 + 1e-6)


class TestCascadeToCampaigns(unittest.TestCase):

    def test_cascaded_total_matches_channel_action(self):
        actions = allocate_channel_budgets(CAMPAIGNS, CHANNEL_OF, POLICY)
        cascaded = cascade_to_campaigns(CAMPAIGNS, CHANNEL_OF, actions)
        by_channel_action = {a.campaign: a.new_budget for a in actions}
        for channel in ("linkedin", "google", "meta"):
            channel_total = sum(
                c.daily_budget for c in cascaded if CHANNEL_OF[c.name] == channel
            )
            self.assertAlmostEqual(channel_total, by_channel_action[channel], places=2)

    def test_splits_proportionally_to_spend(self):
        actions = allocate_channel_budgets(CAMPAIGNS, CHANNEL_OF, POLICY)
        cascaded = cascade_to_campaigns(CAMPAIGNS, CHANNEL_OF, actions)
        by_name = {c.name: c for c in cascaded}
        # LI-ABM-tier1 spent 1200 of linkedin's 1400 total -> 6/7 share
        li_tier1_share = by_name["LI-ABM-tier1"].daily_budget
        li_newtest_share = by_name["LI-newtest"].daily_budget
        linkedin_total = li_tier1_share + li_newtest_share
        self.assertAlmostEqual(li_tier1_share / linkedin_total, 1200 / 1400, places=2)

    def test_zero_spend_channel_splits_evenly(self):
        zero_spend_campaigns = [
            Campaign("A", spend=0, conversions=0, daily_budget=50),
            Campaign("B", spend=0, conversions=0, daily_budget=50),
        ]
        channel_of = {"A": "new_channel", "B": "new_channel"}
        policy = PerfPolicy(target_cpa=50.0, account_daily_cap=100.0, kill_when_ratio_above=2.0)
        actions = allocate_channel_budgets(zero_spend_campaigns, channel_of, policy)
        cascaded = cascade_to_campaigns(zero_spend_campaigns, channel_of, actions)
        by_name = {c.name: c for c in cascaded}
        self.assertAlmostEqual(by_name["A"].daily_budget, by_name["B"].daily_budget, places=2)

    def test_missing_action_for_channel_raises(self):
        actions = allocate_channel_budgets(CAMPAIGNS, CHANNEL_OF, POLICY)
        actions_without_meta = [a for a in actions if a.campaign != "meta"]
        with self.assertRaises(KeyError):
            cascade_to_campaigns(CAMPAIGNS, CHANNEL_OF, actions_without_meta)


if __name__ == "__main__":
    unittest.main()
