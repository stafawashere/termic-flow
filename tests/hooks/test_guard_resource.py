import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

GUARD = ROOT / "hooks" / "guard.py"
HEAVY = (
   "python3 -m unittest discover -s tests",
   "timeout 600 python -m unittest discover -s tests",
   "make",
   "make build",
   "cd app && swift build",
   "npm run build",
)
TARGETED = (
   "python3 -m unittest discover -s tests -k guard",
   "python3 -m unittest tests.hooks.test_guard -v",
   "swift test --filter Foo",
   "git status",
)


class GuardResource(unittest.TestCase):
   def setUp(self):
      self.temp = tempfile.TemporaryDirectory()
      self.project = Path(self.temp.name)
      (self.project / ".termic-flow.json").write_text(json.dumps({"extends": "termic-plus"}), encoding="utf-8")
      self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.project / "cfg")}
      self.env.pop("TERMIC_TASK_ID", None)
      self.env.pop("TERMIC_TASK", None)

   def tearDown(self):
      self.temp.cleanup()

   def run_guard(self, command, task=None, **extra_input):
      env = dict(self.env)

      if task:
         env["TERMIC_TASK_ID"] = "id-1"
         env["TERMIC_TASK"] = task

      event = {"tool_name": "Bash", "tool_input": {"command": command, **extra_input}, "cwd": str(self.project)}
      run = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True, env=env)
      return run.returncode, run.stderr

   def test_worker_foreground_heavy_command_warns_without_blocking(self):
      for command in HEAVY:
         code, err = self.run_guard(command, task="feat: x")
         self.assertEqual(code, 0, command)
         self.assertIn("in the background", err, command)

   def test_each_link_of_a_chain_is_judged_on_its_own(self):
      for command in ("make && ./run &", "make; ./run &", "swift build || ./run &", "npm run build\n./run &"):
         code, err = self.run_guard(command, task="feat: x")
         self.assertEqual(code, 0, command)
         self.assertIn("in the background", err, command)

      for command in ("./prep && make > /tmp/b.log 2>&1 &", "make > /tmp/b.log 2>&1 & ./run", "make &> /tmp/b.log &"):
         self.assertEqual(self.run_guard(command, task="feat: x"), (0, ""), command)

   def test_redirect_ampersands_do_not_count_as_backgrounding(self):
      for command in ("make > /tmp/b.log 2>&1", "make &> /tmp/b.log"):
         code, err = self.run_guard(command, task="feat: x")
         self.assertEqual(code, 0, command)
         self.assertIn("in the background", err, command)

   def test_backgrounded_runs_are_silent(self):
      for command in HEAVY:
         code, err = self.run_guard(command, task="feat: x", run_in_background=True)
         self.assertEqual((code, err), (0, ""), command)

         code, err = self.run_guard(f"{command} > /tmp/full.log 2>&1 &", task="feat: x")
         self.assertEqual((code, err), (0, ""), command)

   def test_targeted_runs_are_silent(self):
      for command in TARGETED:
         code, err = self.run_guard(command, task="feat: x")
         self.assertEqual((code, err), (0, ""), command)

   def test_orchestrator_and_outside_runs_are_silent(self):
      for command in HEAVY:
         self.assertEqual(self.run_guard(command, task="ops: drive x"), (0, ""), command)
         self.assertEqual(self.run_guard(command), (0, ""), command)

   def test_user_only_verbs_still_block_for_a_worker(self):
      for command in ("tf tested 1111 ok", "tf approve 1111", "tf accept 1111 ok"):
         code, _ = self.run_guard(command, task="feat: x")
         self.assertEqual(code, 2, command)
