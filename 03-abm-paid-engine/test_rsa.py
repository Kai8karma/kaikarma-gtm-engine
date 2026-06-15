"""Tests for the Google RSA builder/validator — Google's format rules, provable.

    python3 03-abm-paid-engine/test_rsa.py
"""

import unittest

from rsa_builder import generation_brief, rsa_to_csv, validate_rsa
from rsa_schema import ResponsiveSearchAd


def base() -> ResponsiveSearchAd:
    """A minimal compliant RSA; tests mutate copies of it."""
    return ResponsiveSearchAd(
        headlines=("Alpha One", "Beta Two", "Gamma Three"),
        descriptions=("A clear concise description here.",
                      "Another concise compliant description."),
        path1="gtm", path2="engine",
    )


def _issues(text: str) -> str:
    return " || ".join(text)


class TestValidation(unittest.TestCase):

    def test_valid_ad_passes(self):
        v = validate_rsa(base())
        self.assertTrue(v.ok, _issues(v.issues))
        self.assertEqual(v.issues, ())

    def test_headline_too_long(self):
        ad = ResponsiveSearchAd(headlines=("X" * 31, "Beta Two", "Gamma Three"),
                                descriptions=base().descriptions)
        v = validate_rsa(ad)
        self.assertFalse(v.ok)
        self.assertTrue(any("exceeds 30" in i for i in v.issues), _issues(v.issues))

    def test_too_few_headlines(self):
        ad = ResponsiveSearchAd(headlines=("Only", "Two"), descriptions=base().descriptions)
        self.assertTrue(any("need 3-15" in i for i in validate_rsa(ad).issues))

    def test_too_many_headlines(self):
        ad = ResponsiveSearchAd(headlines=tuple(f"Headline {i}" for i in range(16)),
                                descriptions=base().descriptions)
        self.assertTrue(any("need 3-15" in i for i in validate_rsa(ad).issues))

    def test_duplicate_headlines_rejected(self):
        ad = ResponsiveSearchAd(headlines=("Same Thing", "Same Thing", "Other One"),
                                descriptions=base().descriptions)
        self.assertTrue(any("unique" in i for i in validate_rsa(ad).issues))

    def test_exclamation_in_headline_rejected(self):
        ad = ResponsiveSearchAd(headlines=("Buy Now!", "Beta Two", "Gamma Three"),
                                descriptions=base().descriptions)
        self.assertTrue(any("may not contain '!'" in i for i in validate_rsa(ad).issues))

    def test_at_most_one_exclamation_per_ad(self):
        ad = ResponsiveSearchAd(headlines=base().headlines,
                                descriptions=("Save big today!", "Limited offer now!"))
        self.assertTrue(any("exceeds max 1" in i for i in validate_rsa(ad).issues))

    def test_repeated_punctuation_rejected(self):
        ad = ResponsiveSearchAd(headlines=base().headlines,
                                descriptions=("Best deal ever...", "Solid compliant description."))
        self.assertTrue(any("repeated punctuation" in i for i in validate_rsa(ad).issues))

    def test_gratuitous_caps_rejected(self):
        ad = ResponsiveSearchAd(headlines=("HUGE SAVINGS HERE", "Beta Two", "Gamma Three"),
                                descriptions=base().descriptions)
        self.assertTrue(any("gratuitous capitalization" in i for i in validate_rsa(ad).issues))

    def test_known_acronyms_allowed(self):
        ad = ResponsiveSearchAd(headlines=("ROAS Up, CPA Down", "Beta Two", "Gamma Three"),
                                descriptions=base().descriptions)
        v = validate_rsa(ad)
        self.assertTrue(v.ok, _issues(v.issues))

    def test_description_too_long(self):
        ad = ResponsiveSearchAd(headlines=base().headlines,
                                descriptions=("Y" * 91, "Another concise compliant description."))
        self.assertTrue(any("exceeds 90" in i for i in validate_rsa(ad).issues))

    def test_too_few_descriptions(self):
        ad = ResponsiveSearchAd(headlines=base().headlines, descriptions=("Only one here.",))
        self.assertTrue(any("need 2-4" in i for i in validate_rsa(ad).issues))


class TestExport(unittest.TestCase):

    def test_csv_has_headers_and_values(self):
        out = rsa_to_csv(base())
        self.assertIn("Headline 1", out)
        self.assertIn("Description 1", out)
        self.assertIn("Alpha One", out)

    def test_generation_brief_encodes_limits(self):
        b = generation_brief("kaikarma", ["gtm engineering"], "technical")
        for token in ("30", "90", "15", "kaikarma", "gtm engineering"):
            self.assertIn(token, b)


class TestDeterminism(unittest.TestCase):

    def test_validation_is_deterministic(self):
        self.assertEqual(validate_rsa(base()), validate_rsa(base()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
