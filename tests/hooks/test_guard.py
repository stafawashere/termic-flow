import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

GUARD = ROOT / "hooks" / "guard.py"
EM = chr(0x2014)


class Guard(unittest.TestCase):
   def setUp(self):
      self.temp = tempfile.TemporaryDirectory()
      self.project = Path(self.temp.name)
      (self.project / ".termic-flow.json").write_text(json.dumps({"extends": "termic-plus"}), encoding="utf-8")
      self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.project / "cfg")}

   def tearDown(self):
      self.temp.cleanup()

   def decide(self, tool, **tool_input):
      event = {"tool_name": tool, "tool_input": tool_input, "cwd": str(self.project)}
      run = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True, env=self.env)
      return run.returncode, run.stderr

   def assert_blocked(self, command):
      code, _ = self.decide("Bash", command=command)
      self.assertEqual(code, 2, command)

   def assert_allowed(self, command):
      code, err = self.decide("Bash", command=command)
      self.assertEqual(code, 0, f"{command}: {err}")

   def test_raw_destructive_cli_calls_are_blocked(self):
      for command in (
         '"$TERMIC_CLI" archive "fix: x" --yes',
         "termic-cli tab close main --tab 2",
         "termic quit --yes",
         '"$TERMIC_CLI" apply fix-x --yes',
      ):
         self.assert_blocked(command)

   def test_reads_and_tf_do_are_allowed(self):
      for command in ('"$TERMIC_CLI" list --json', "tf do archive fix-x", "tf snapshot", "git log --oneline | head"):
         self.assert_allowed(command)

   def test_model_cannot_approve_or_record_tests_itself(self):
      self.assert_blocked("tf approve 1111")
      self.assert_blocked("cd x && tf tested 1111 'looked fine'")
      self.assert_blocked("tf accept 1111 ok")

   def enable_auto_approve(self):
      profile = {"extends": "termic-plus", "auto_approve": True}
      (self.project / ".termic-flow.json").write_text(json.dumps(profile), encoding="utf-8")

   def test_auto_markers_are_blocked_unless_the_profile_opts_in(self):
      self.assert_blocked("tf tested 1111 --auto")
      self.enable_auto_approve()
      self.assert_allowed("tf tested 1111 --auto")
      self.assert_allowed("cd x && tf approve 1111 --auto")
      self.assert_blocked("tf tested 1111 'looked fine'")
      self.assert_blocked("tf accept 1111 --auto")

   def test_auto_flag_must_sit_in_the_same_command(self):
      self.enable_auto_approve()
      self.assert_blocked("tf tested 1111; echo --auto")

   def test_marker_verbs_named_as_text_are_not_runs(self):
      self.assert_allowed('tf log "asked the user to run tf tested 1111"')

   def test_raw_pr_creation_is_blocked(self):
      self.assert_blocked("gh pr create --fill")

   def test_profile_forbidden_commands_and_paths(self):
      self.assert_blocked("make release-patch")
      code, _ = self.decide("Edit", file_path=str(self.project / "CHANGELOG.md"))
      self.assertEqual(code, 2)
      code, _ = self.decide("Edit", file_path=str(self.project / "README.md"))
      self.assertEqual(code, 0)

   def test_test_commands_need_timeout_under_this_profile(self):
      self.assert_blocked("npm test")
      self.assert_blocked("cd src-tauri && cargo test")
      self.assert_allowed("timeout 600 npm test")
      self.assert_blocked("python3 -m " + "pytest -q")
      self.assert_blocked("timeout 60 npm test; npm test")

   def test_a_runner_named_as_text_is_not_a_test_run(self):
      runner = "py" + "test"
      self.assert_allowed(f"grep -n {runner} tf_lib/setup.py")
      self.assert_allowed(f'tf log "switched off {runner}"')

   def test_dashes_in_tf_text_are_blocked(self):
      self.assert_blocked(f'tf log "done {EM} next"')
      self.assert_allowed('tf log "done, next"')

   def test_default_profile_does_not_require_timeouts(self):
      (self.project / ".termic-flow.json").unlink()
      self.assert_allowed("npm test")
