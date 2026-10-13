import unittest

from tf_lib.profile import PLUGIN_ROOT, deep_merge, read_json
from tf_lib.prompts import render

REPORTING_TEMPLATES = ("impl", "plan")


class ReportPadsCarryTheRound(unittest.TestCase):
   def setUp(self):
      default = read_json(PLUGIN_ROOT / "profiles" / "default.json")
      self.profile = deep_merge(default, read_json(PLUGIN_ROOT / "profiles" / "termic-plus.json"))

   def rendered(self, template):
      return render(self.profile, template, task="fix: x", task_id="id-1", packet="pad-1", report="pad-2", subject="fix: x")

   def test_every_report_pad_title_names_its_round(self):
      for template in REPORTING_TEMPLATES:
         report_creates = [
            line for line in self.rendered(template).splitlines()
            if "scratchpad new" in line and '--title "report: ' in line
         ]

         self.assertTrue(report_creates, template)

         for line in report_creates:
            self.assertIn('--title "report: fix: x r<N>"', line, template)

   def test_contract_item_seven_names_the_round(self):
      contract = (PLUGIN_ROOT / "skills" / "drive" / "references" / "worker-contract.md").read_text(encoding="utf-8")
      item_seven = next(line for line in contract.splitlines() if line.startswith("7. "))
      self.assertIn("report: <task> r<N>", item_seven)
