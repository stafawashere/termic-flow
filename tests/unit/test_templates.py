import re
import unittest

from tf_lib.core import BANNED_DASHES
from tf_lib.profile import PLUGIN_ROOT, deep_merge, read_json
from tf_lib.prompts import render

TEMPLATES = sorted(path.stem for path in (PLUGIN_ROOT / "templates").glob("*.txt"))
TIMEOUT = re.compile(r"(^|\s)timeout \d+ ")


class Templates(unittest.TestCase):
   def setUp(self):
      default = read_json(PLUGIN_ROOT / "profiles" / "default.json")
      self.profile = deep_merge(default, read_json(PLUGIN_ROOT / "profiles" / "termic-plus.json"))

   def rendered(self, template, flags=("ui",)):
      return render(self.profile, template, task="fix: x", task_id="id-1", packet="pad-1", report="pad-2", subject="x", flags=flags)

   def test_every_slot_is_filled(self):
      for template in TEMPLATES:
         self.assertIsNone(re.search(r"\{[a-z_]+\}", self.rendered(template)), template)

   def test_every_check_line_runs_under_timeout(self):
      for template in TEMPLATES:
         check_lines = [line for line in self.rendered(template).splitlines() if line.startswith("- ") and ": " in line]

         for line in check_lines:
            if any(word in line for word in ("npm", "cargo", "make")):
               self.assertRegex(line, TIMEOUT, line)

   def test_ui_check_is_locked_and_only_present_for_ui_work(self):
      with_ui = self.rendered("impl", flags=("ui",))
      without_ui = self.rendered("impl", flags=())
      self.assertIn("tf lock e2e -- timeout 1800 make e2e", with_ui)
      self.assertNotIn("make e2e", without_ui)

   def test_build_isolation_exports_a_per_worktree_target(self):
      self.assertIn('CARGO_TARGET_DIR="$(git rev-parse --show-toplevel)/src-tauri/target"', self.rendered("impl"))

   def test_no_banned_dashes(self):
      for template in TEMPLATES:
         for dash in BANNED_DASHES:
            self.assertNotIn(dash, self.rendered(template), template)
