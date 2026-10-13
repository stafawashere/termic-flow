import json

from tests.helpers import FakeTermic, make_task

TASK_ID = "11111111-1111-4111-8111-111111111111"
NAME = "fix: flaky-thing"


class ReviewRound(FakeTermic):
   def setUp(self):
      super().setUp()
      self.set_world({"tasks": [make_task(NAME, TASK_ID)]})

   def open_tab(self, *extra):
      return self.tf("tab", NAME, "review", "--packet", "pad-1", "--report", "pad-prev", *extra)

   def last_tab_call(self):
      entries = [json.loads(line) for line in self.log_path.read_text().splitlines()]
      tab_entries = [entry for entry in entries if entry["argv"][:2] == ["tab", TASK_ID]]
      return tab_entries[-1]

   def title_of(self, entry):
      argv = entry["argv"]
      return argv[argv.index("--title") + 1]

   def model_of(self, entry):
      argv = entry["argv"]
      return argv[argv.index("--model") + 1]

   def test_round_two_opens_a_tab_titled_review_r2(self):
      result = self.open_tab("--round", "2")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(self.title_of(self.last_tab_call()), "review-r2")

   def test_round_one_keeps_the_plain_review_title(self):
      self.open_tab("--round", "1")
      self.assertEqual(self.title_of(self.last_tab_call()), "review")

   def test_no_round_flag_keeps_the_plain_review_title(self):
      self.open_tab()
      self.assertEqual(self.title_of(self.last_tab_call()), "review")

   def test_round_two_uses_the_rereview_template_naming_the_previous_report(self):
      self.open_tab("--round", "2")
      body = self.last_tab_call()["stdin"]
      self.assertIn("scratchpad read pad-prev", body)
      self.assertIn("fixed", body)
      self.assertIn("re-check", body)

   def test_round_one_body_is_the_full_review_template(self):
      self.open_tab("--round", "1")
      self.assertNotIn("re-check", self.last_tab_call()["stdin"])

   def test_round_two_routes_like_review(self):
      self.open_tab()
      first_model = self.model_of(self.last_tab_call())
      result = self.open_tab("--round", "2")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(self.model_of(self.last_tab_call()), first_model)

   def test_an_explicit_template_wins_over_the_round_default(self):
      self.open_tab("--round", "2", "--template", "review")
      self.assertNotIn("re-check", self.last_tab_call()["stdin"])

   def test_round_below_one_is_rejected(self):
      result = self.open_tab("--round", "0")
      self.assertNotEqual(result.returncode, 0)
      self.assertEqual(self.calls_of("tab " + TASK_ID), [])

   def test_round_two_without_a_report_is_refused_before_any_tab_opens(self):
      result = self.tf("tab", NAME, "review", "--packet", "pad-1", "--round", "2")
      self.assertNotEqual(result.returncode, 0)
      self.assertIn("--round", result.stderr)
      self.assertEqual(self.calls_of("tab " + TASK_ID), [])
