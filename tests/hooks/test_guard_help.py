import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

GUARD = ROOT / "hooks" / "guard.py"
VERBS = ("tested", "approve", "accept")


class GuardHelp(unittest.TestCase):
   def setUp(self):
      self.temp = tempfile.TemporaryDirectory()
      self.project = Path(self.temp.name)
      (self.project / ".termic-flow.json").write_text(json.dumps({"extends": "termic-plus"}), encoding="utf-8")
      self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.project / "cfg")}

   def tearDown(self):
      self.temp.cleanup()

   def code_for(self, command):
      event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.project)}
      run = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True, env=self.env)
      return run.returncode

   def test_bare_help_flags_are_allowed(self):
      for verb in VERBS:
         for flag in ("--help", "-h", "-h --help"):
            self.assertEqual(self.code_for(f"tf {verb} {flag}"), 0, f"{verb} {flag}")

   def test_help_beside_a_real_argument_stays_blocked(self):
      for verb in VERBS:
         for tail in ("1111 --help", "--help 1111", "1111 ok -h", "--helpx", "-hh"):
            self.assertEqual(self.code_for(f"tf {verb} {tail}"), 2, f"{verb} {tail}")

   def test_help_does_not_shield_a_later_real_call(self):
      for verb in VERBS:
         self.assertEqual(self.code_for(f"tf {verb} --help; tf {verb} 1111 ok"), 2, verb)
         self.assertEqual(self.code_for(f"tf {verb} --help && tf {verb} 1111"), 2, verb)
