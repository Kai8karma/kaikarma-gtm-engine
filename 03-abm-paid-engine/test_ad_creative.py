"""Tests for the Meta + LinkedIn ad-creative validator.

    python3 03-abm-paid-engine/test_ad_creative.py
"""

from __future__ import annotations

import unittest

from ad_creative import (
    linkedin_generation_brief,
    meta_generation_brief,
    validate_linkedin_creative,
    validate_meta_creative,
)
from creative_schema import (
    LINKEDIN_HEADLINE_RECOMMENDED_MAX,
    LINKEDIN_INTRO_TEXT_RECOMMENDED_MAX,
    META_DESCRIPTION_RECOMMENDED_MAX,
    META_HEADLINE_RECOMMENDED_MAX,
    META_PRIMARY_TEXT_RECOMMENDED_MAX,
    LinkedInAdCreative,
    MetaAdCreative,
)


class TestValidateMetaCreative(unittest.TestCase):

    def test_valid_creative_ok_no_warnings(self):
        ad = MetaAdCreative(primary_text="Short and punchy.", headline="Great Headline", description="A description.")
        v = validate_meta_creative(ad)
        self.assertTrue(v.ok)
        self.assertEqual(v.warnings, ())

    def test_blank_primary_text_is_hard_issue(self):
        ad = MetaAdCreative(primary_text="", headline="Headline")
        v = validate_meta_creative(ad)
        self.assertFalse(v.ok)
        self.assertTrue(any("primary_text" in i for i in v.issues))

    def test_blank_headline_is_hard_issue(self):
        ad = MetaAdCreative(primary_text="Text", headline="")
        v = validate_meta_creative(ad)
        self.assertFalse(v.ok)

    def test_long_primary_text_is_warning_not_issue(self):
        ad = MetaAdCreative(primary_text="A" * (META_PRIMARY_TEXT_RECOMMENDED_MAX + 1), headline="Headline")
        v = validate_meta_creative(ad)
        self.assertTrue(v.ok)  # still ok — truncation risk is advisory
        self.assertTrue(any("primary_text" in w for w in v.warnings))

    def test_long_headline_is_warning(self):
        ad = MetaAdCreative(primary_text="Text", headline="B" * (META_HEADLINE_RECOMMENDED_MAX + 1))
        v = validate_meta_creative(ad)
        self.assertTrue(any("headline" in w for w in v.warnings))

    def test_long_description_is_warning(self):
        ad = MetaAdCreative(primary_text="Text", headline="Headline", description="D" * (META_DESCRIPTION_RECOMMENDED_MAX + 1))
        v = validate_meta_creative(ad)
        self.assertTrue(any("description" in w for w in v.warnings))

    def test_empty_description_no_warning(self):
        ad = MetaAdCreative(primary_text="Text", headline="Headline", description="")
        v = validate_meta_creative(ad)
        self.assertEqual(v.warnings, ())


class TestValidateLinkedInCreative(unittest.TestCase):

    def test_valid_creative_ok_no_warnings(self):
        ad = LinkedInAdCreative(introductory_text="Short intro text.", headline="Great Headline")
        v = validate_linkedin_creative(ad)
        self.assertTrue(v.ok)
        self.assertEqual(v.warnings, ())

    def test_blank_intro_text_is_hard_issue(self):
        ad = LinkedInAdCreative(introductory_text="", headline="Headline")
        v = validate_linkedin_creative(ad)
        self.assertFalse(v.ok)

    def test_blank_headline_is_hard_issue(self):
        ad = LinkedInAdCreative(introductory_text="Intro", headline="")
        v = validate_linkedin_creative(ad)
        self.assertFalse(v.ok)

    def test_long_intro_text_is_warning_not_issue(self):
        ad = LinkedInAdCreative(introductory_text="A" * (LINKEDIN_INTRO_TEXT_RECOMMENDED_MAX + 1), headline="Headline")
        v = validate_linkedin_creative(ad)
        self.assertTrue(v.ok)
        self.assertTrue(any("introductory_text" in w for w in v.warnings))

    def test_long_headline_is_warning(self):
        ad = LinkedInAdCreative(introductory_text="Intro", headline="B" * (LINKEDIN_HEADLINE_RECOMMENDED_MAX + 1))
        v = validate_linkedin_creative(ad)
        self.assertTrue(any("headline" in w for w in v.warnings))


class TestGenerationBriefs(unittest.TestCase):

    def test_meta_brief_includes_inputs_and_limits(self):
        brief = meta_generation_brief("Acme", "RevOps leaders", "confident")
        self.assertIn("Acme", brief)
        self.assertIn("RevOps leaders", brief)
        self.assertIn(str(META_PRIMARY_TEXT_RECOMMENDED_MAX), brief)

    def test_linkedin_brief_includes_inputs_and_limits(self):
        brief = linkedin_generation_brief("Acme", "RevOps leaders", "confident")
        self.assertIn("Acme", brief)
        self.assertIn(str(LINKEDIN_INTRO_TEXT_RECOMMENDED_MAX), brief)


if __name__ == "__main__":
    unittest.main()
