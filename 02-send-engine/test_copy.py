"""Tests for framework_registry and copy_eval.

Stdlib unittest — no install needed (runs air-gapped).
    python3 02-send-engine/test_copy.py            # stdlib
    python3 -m pytest 02-send-engine/test_copy.py  # if pytest installed
"""

import unittest

from copy_eval import BANNED_WORDS, WORD_MAX, WORD_MIN, EvalResult, score_copy
from framework_registry import Framework, get_framework, list_frameworks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clean_draft(fw: Framework | None = None) -> tuple[Framework, str]:
    """Return a (framework, rendered_draft) pair that should score 100/100."""
    fw = fw or get_framework("problem-first")
    draft = fw.render({
        "first_name": "Sarah",
        "observed_signal": "saw you just posted four SDR roles on LinkedIn",
        "quantified_pain": "most scaling teams lose 8 hours per rep per week on manual CRM entry",
        "one_liner_solution": "we auto-sync every call note straight to HubSpot in real-time",
        "soft_cta": "Worth a 15-min chat this week to see if it fits?",
    })
    return fw, draft


# ---------------------------------------------------------------------------
# framework_registry — registry API
# ---------------------------------------------------------------------------

class TestRegistryAPI(unittest.TestCase):

    def test_list_frameworks_returns_list(self):
        names = list_frameworks()
        self.assertIsInstance(names, list)

    def test_list_frameworks_contains_known_names(self):
        names = list_frameworks()
        for expected in ("problem-first", "do-the-math", "pattern-interrupt", "upfront-value"):
            self.assertIn(expected, names)

    def test_get_framework_returns_framework(self):
        fw = get_framework("problem-first")
        self.assertIsInstance(fw, Framework)

    def test_get_framework_unknown_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_framework("does-not-exist")

    def test_all_listed_frameworks_are_retrievable(self):
        for name in list_frameworks():
            fw = get_framework(name)
            self.assertEqual(fw.name, name)

    def test_framework_has_required_slots(self):
        fw = get_framework("problem-first")
        self.assertIn("first_name", fw.required_slots)
        self.assertIn("soft_cta", fw.required_slots)

    def test_framework_has_best_use(self):
        for name in list_frameworks():
            fw = get_framework(name)
            self.assertTrue(len(fw.best_use) > 10, f"{name} has no best_use text")


# ---------------------------------------------------------------------------
# framework_registry — render happy path
# ---------------------------------------------------------------------------

class TestFrameworkRender(unittest.TestCase):

    def test_render_problem_first_happy_path(self):
        fw = get_framework("problem-first")
        _, draft = _make_clean_draft(fw)
        self.assertIn("Sarah", draft)
        self.assertIn("SDR", draft)

    def test_render_do_the_math_happy_path(self):
        fw = get_framework("do-the-math")
        draft = fw.render({
            "first_name": "Marcus",
            "observed_signal": "noticed you raised your Series A last month",
            "cost_of_problem": "$6k per month in wasted admin time",
            "what_we_do": "we cut that by 70 percent",
            "proof_point": "Deel saw the same outcome in 3 weeks",
            "soft_cta": "Open to a quick call Tuesday?",
        })
        self.assertIn("Marcus", draft)
        self.assertIn("Tuesday", draft)

    def test_render_pattern_interrupt_happy_path(self):
        fw = get_framework("pattern-interrupt")
        draft = fw.render({
            "first_name": "Priya",
            "disruptive_opener": "I know you get 40 cold emails a day",
            "unexpected_angle": "so I will skip the pitch and ask one thing",
            "single_question": "What would it take to cut your team's data-entry time in half?",
            "soft_cta": "Happy to share how if you reply.",
        })
        self.assertIn("Priya", draft)

    def test_render_upfront_value_happy_path(self):
        fw = get_framework("upfront-value")
        draft = fw.render({
            "first_name": "Tom",
            "value_artifact": "a teardown of your onboarding flow",
            "key_finding": "found 3 drop-off points in the first 48h",
            "why_it_matters": "fixing the first one could lift activation by 15 percent",
            "soft_cta": "Want me to send it over?",
        })
        self.assertIn("Tom", draft)

    def test_render_returns_string(self):
        fw, draft = _make_clean_draft()
        self.assertIsInstance(draft, str)

    def test_render_is_deterministic(self):
        fw = get_framework("problem-first")
        slots = {
            "first_name": "Ali",
            "observed_signal": "saw your Series B announcement",
            "quantified_pain": "rapid growth usually surfaces CRM gaps within 60 days",
            "one_liner_solution": "we auto-log every call to Salesforce",
            "soft_cta": "15 minutes this week?",
        }
        self.assertEqual(fw.render(slots), fw.render(slots))


# ---------------------------------------------------------------------------
# framework_registry — missing-slot error
# ---------------------------------------------------------------------------

class TestFrameworkMissingSlot(unittest.TestCase):

    def test_missing_one_slot_raises_key_error(self):
        fw = get_framework("problem-first")
        incomplete = {
            "first_name": "Sarah",
            "observed_signal": "saw your job posting",
            # missing: quantified_pain, one_liner_solution, soft_cta
        }
        with self.assertRaises(KeyError):
            fw.render(incomplete)

    def test_missing_slot_error_names_the_slot(self):
        fw = get_framework("problem-first")
        try:
            fw.render({"first_name": "X"})
        except KeyError as exc:
            self.assertIn("quantified_pain", str(exc))
        else:
            self.fail("Expected KeyError was not raised")

    def test_empty_dict_raises(self):
        fw = get_framework("do-the-math")
        with self.assertRaises(KeyError):
            fw.render({})

    def test_extra_slots_do_not_raise(self):
        """Passing extra keys beyond required_slots should not raise."""
        fw = get_framework("problem-first")
        slots = {
            "first_name": "Sarah",
            "observed_signal": "A",
            "quantified_pain": "B",
            "one_liner_solution": "C",
            "soft_cta": "D?",
            "extra_key": "ignored",
        }
        # Must NOT raise
        result = fw.render(slots)
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# copy_eval — clean draft scores high
# ---------------------------------------------------------------------------

class TestCopyEvalCleanDraft(unittest.TestCase):

    def setUp(self) -> None:
        self.fw, self.draft = _make_clean_draft()
        self.result = score_copy(self.draft, self.fw)

    def test_returns_eval_result(self):
        self.assertIsInstance(self.result, EvalResult)

    def test_clean_draft_scores_100(self):
        self.assertEqual(self.result.score, 100)

    def test_clean_draft_has_no_issues(self):
        self.assertEqual(self.result.issues, [])

    def test_breakdown_keys_match_criteria(self):
        expected = {
            "word_count_in_bounds", "question_or_cta",
            "no_banned_words", "personalization_token", "single_clear_ask",
        }
        self.assertEqual(set(self.result.breakdown.keys()), expected)

    def test_breakdown_sums_to_score(self):
        self.assertEqual(sum(self.result.breakdown.values()), self.result.score)


# ---------------------------------------------------------------------------
# copy_eval — hypey draft scores low
# ---------------------------------------------------------------------------

class TestCopyEvalHypeyDraft(unittest.TestCase):

    def setUp(self) -> None:
        self.fw = get_framework("problem-first")
        # Hype words + no question + way too long (ensure > WORD_MAX)
        self.hypey = (
            "Hi there,\n\n"
            "Our revolutionary game-changer synergy platform is the most innovative "
            "best-in-class cutting-edge disruptive world-class solution on the market. "
            "We leverage paradigm-shifting technology to deliver results no one else can. "
            "You should definitely try it because it is very very good and amazing. "
            "Our team has built the most outstanding product and you will love it. "
            "Truly best in class across every dimension possible. Thank you."
        )
        self.result = score_copy(self.hypey, self.fw)

    def test_hypey_draft_scores_below_50(self):
        self.assertLess(self.result.score, 50)

    def test_hypey_draft_has_issues(self):
        self.assertGreater(len(self.result.issues), 0)

    def test_no_question_flagged(self):
        issue_text = " ".join(self.result.issues).lower()
        self.assertTrue(
            "question" in issue_text or "ask" in issue_text or "cta" in issue_text
        )


# ---------------------------------------------------------------------------
# copy_eval — banned-word detection
# ---------------------------------------------------------------------------

class TestBannedWords(unittest.TestCase):

    def test_single_banned_word_triggers_issue(self):
        fw = get_framework("problem-first")
        draft = fw.render({
            "first_name": "Dana",
            "observed_signal": "noticed you are hiring",
            "quantified_pain": "most teams hit this wall within 90 days",
            "one_liner_solution": "our revolutionary tool fixes it automatically",
            "soft_cta": "Worth a quick chat?",
        })
        result = score_copy(draft, fw)
        issues_text = " ".join(result.issues).lower()
        self.assertIn("revolutionary", issues_text)

    def test_all_banned_words_are_lowercase(self):
        """BANNED_WORDS must be lowercase so case-insensitive matching works."""
        for word in BANNED_WORDS:
            self.assertEqual(word, word.lower(), f"BANNED_WORDS entry not lowercase: {word}")

    def test_banned_word_in_caps_still_caught(self):
        fw = get_framework("problem-first")
        draft = fw.render({
            "first_name": "Pat",
            "observed_signal": "saw your product launch",
            "quantified_pain": "teams usually see friction here",
            "one_liner_solution": "we LEVERAGE your existing stack to remove it",
            "soft_cta": "Open for a 15-min call this week?",
        })
        result = score_copy(draft, fw)
        issues_text = " ".join(result.issues).lower()
        self.assertIn("leverage", issues_text)

    def test_draft_with_no_banned_words_earns_full_ban_pts(self):
        fw, draft = _make_clean_draft()
        result = score_copy(draft, fw)
        self.assertEqual(result.breakdown["no_banned_words"], 20)


# ---------------------------------------------------------------------------
# copy_eval — word-count bounds
# ---------------------------------------------------------------------------

class TestWordCountBounds(unittest.TestCase):

    def test_word_count_constants_are_sane(self):
        self.assertGreater(WORD_MAX, WORD_MIN)
        self.assertGreater(WORD_MIN, 0)

    def test_draft_under_min_word_count_penalised(self):
        fw = get_framework("pattern-interrupt")
        # Force an ultra-short draft by supplying very short slot values
        draft = fw.render({
            "first_name": "Jo",
            "disruptive_opener": "Hi",
            "unexpected_angle": "Skip",
            "single_question": "Interested?",
            "soft_cta": "Reply.",
        })
        result = score_copy(draft, fw)
        if len(draft.split()) < WORD_MIN:
            self.assertEqual(result.breakdown["word_count_in_bounds"], 0)
            self.assertTrue(any("word count" in i for i in result.issues))

    def test_within_bounds_earns_full_pts(self):
        fw, draft = _make_clean_draft()
        wc = len(draft.split())
        result = score_copy(draft, fw)
        if WORD_MIN <= wc <= WORD_MAX:
            self.assertEqual(result.breakdown["word_count_in_bounds"], 25)


# ---------------------------------------------------------------------------
# copy_eval — single clear ask (question count)
# ---------------------------------------------------------------------------

class TestSingleClearAsk(unittest.TestCase):

    def test_zero_questions_penalised(self):
        fw = get_framework("upfront-value")
        draft = fw.render({
            "first_name": "Alex",
            "value_artifact": "a competitive teardown on your top 3 rivals",
            "key_finding": "your pricing page is 40 percent longer than any competitor",
            "why_it_matters": "that alone may be dropping conversion by double digits",
            "soft_cta": "Let me know if you want it sent over",  # no '?'
        })
        result = score_copy(draft, fw)
        self.assertEqual(result.breakdown["single_clear_ask"], 0)

    def test_exactly_one_question_earns_full_pts(self):
        fw, draft = _make_clean_draft()
        result = score_copy(draft, fw)
        self.assertEqual(result.breakdown["single_clear_ask"], 15)

    def test_multiple_questions_penalised(self):
        fw = get_framework("problem-first")
        draft = fw.render({
            "first_name": "Lee",
            "observed_signal": "saw you just hired two ops managers",
            "quantified_pain": "ops hires often follow a doubling of manual work",
            "one_liner_solution": "we automate the reporting layer end to end",
            "soft_cta": "Worth a chat? Or maybe next week? Or whenever works?",
        })
        result = score_copy(draft, fw)
        self.assertEqual(result.breakdown["single_clear_ask"], 0)
        self.assertTrue(any("question" in i for i in result.issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
