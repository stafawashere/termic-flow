import json
import unittest

from tests.helpers import FakeTermic, make_task
from tf_lib import report
from tf_lib.core import TfError
from tf_lib.report import parse_report

GOOD = """# report: fix: x
status: pass
checks: unit=0, rust=0
changed: 3
risks: none
next: review
"""


class Reports(unittest.TestCase):
   def test_good_report_parses_checks(self):
      parsed = parse_report(GOOD)
      self.assertEqual(parsed["checks"], {"unit": "0", "rust": "0"})
      self.assertEqual(parsed["failure"], "none")

   def test_pass_with_a_red_check_is_rejected(self):
      with self.assertRaises(TfError):
         parse_report(GOOD.replace("rust=0", "rust=101"))

   def test_missing_field_is_rejected(self):
      with self.assertRaises(TfError):
         parse_report(GOOD.replace("next: review\n", ""))

   def test_unknown_status_is_rejected(self):
      with self.assertRaises(TfError):
         parse_report(GOOD.replace("status: pass", "status: done"))


class ExpectedFailChecks(unittest.TestCase):
   def test_red_prefixed_non_zero_check_passes(self):
      parsed = parse_report(GOOD.replace("rust=0", "red_rust=101"))
      self.assertEqual(parsed["checks"]["red_rust"], "101")

   def test_red_prefixed_zero_check_is_rejected(self):
      with self.assertRaises(TfError):
         parse_report(GOOD.replace("rust=0", "red_rust=0"))

   def test_plain_non_zero_check_beside_a_red_check_is_rejected(self):
      with self.assertRaises(TfError):
         parse_report(GOOD.replace("unit=0, rust=0", "unit=1, red_rust=101"))

   def test_red_prefixed_padded_zero_is_rejected(self):
      with self.assertRaises(TfError):
         parse_report(GOOD.replace("rust=0", "red_rust=00"))


def pad(pad_id, title):
   return {"id": pad_id, "title": title}


class RoundPick(unittest.TestCase):
   def test_highest_round_wins(self):
      pads = [pad("pad-a", "report: fix: x r1"), pad("pad-b", "report: fix: x r2")]
      self.assertEqual(report.pick_latest_round(pads, "fix: x"), {"pad": "pad-b", "round": 2})

   def test_legacy_pad_without_suffix_reads_as_round_one(self):
      pads = [pad("pad-a", "report: fix: x")]
      self.assertEqual(report.pick_latest_round(pads, "fix: x"), {"pad": "pad-a", "round": 1})

   def test_tagged_round_beats_legacy_pad(self):
      pads = [pad("pad-a", "report: fix: x"), pad("pad-b", "report: fix: x r2")]
      self.assertEqual(report.pick_latest_round(pads, "fix: x")["pad"], "pad-b")

   def test_rounds_compare_as_numbers(self):
      pads = [pad("pad-a", "report: fix: x r9"), pad("pad-b", "report: fix: x r10")]
      self.assertEqual(report.pick_latest_round(pads, "fix: x")["round"], 10)

   def test_other_tasks_and_pad_kinds_are_ignored(self):
      pads = [
         pad("pad-a", "report: fix: x r1"),
         pad("pad-b", "report: fix: xy r5"),
         pad("pad-c", "packet: fix: x r7"),
      ]
      self.assertEqual(report.pick_latest_round(pads, "fix: x")["pad"], "pad-a")

   def test_no_report_pad_is_an_error(self):
      with self.assertRaises(TfError):
         report.pick_latest_round([pad("pad-a", "packet: fix: x")], "fix: x")

   def test_pad_list_lines_split_into_id_and_title(self):
      text = "5f1c0a3e-1b2d-4c3e-8f4a-0123456789ab  report: fix: x r2\n\nnot a pad line\n"
      self.assertEqual(
         report.parse_pad_list(text),
         [pad("5f1c0a3e-1b2d-4c3e-8f4a-0123456789ab", "report: fix: x r2")],
      )


class TfReportByTask(FakeTermic):
   NAME = "fix: x"
   TASK_ID = "11111111-2222-4333-8444-555555555555"

   def seed(self, pads, titles):
      self.set_world({"tasks": [make_task(self.NAME, self.TASK_ID)], "pads": pads, "titles": titles})

   def test_task_without_a_pad_returns_the_highest_round(self):
      other = GOOD.replace("changed: 3", "changed: 9")
      self.seed(
         {"pad-a": GOOD, "pad-b": other},
         {"pad-a": "report: fix: x r1", "pad-b": "report: fix: x r2"},
      )
      result = self.tf("report", "--task", self.NAME)
      self.assertEqual(result.returncode, 0, result.stderr)
      parsed = json.loads(result.stdout)
      self.assertEqual((parsed["round"], parsed["pad"], parsed["changed"]), (2, "pad-b", "9"))

   def test_legacy_pad_reports_round_one(self):
      self.seed({"pad-a": GOOD}, {"pad-a": "report: fix: x"})
      result = self.tf("report", "--task", self.NAME)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(json.loads(result.stdout)["round"], 1)
