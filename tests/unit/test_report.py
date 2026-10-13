import unittest

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
