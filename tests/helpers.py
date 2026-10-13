import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE_CLI = ROOT / "tests" / "fake" / "termic-cli"
TF = ROOT / "bin" / "tf"


def make_task(name, task_id, **overrides):
   task = {
      "id": task_id,
      "name": name,
      "project": "demo",
      "agent": "claude",
      "branch": name.replace(": ", "-"),
      "base_branch": "main",
      "path": f"/Users/u/worktrees/{task_id[:8]}",
      "is_main_checkout": False,
      "work_state": "idle",
      "open_tabs": 1,
      "diff": {"files_changed": 0, "insertions": 0, "deletions": 0, "untracked": 0},
      "group": {"name": "batch", "color": "teal"},
      "props": [],
      "tabs": [{"id": "tab-1", "index": 1, "kind": "agent", "title": "impl", "state": "idle", "queued": 0}],
   }
   task.update(overrides)
   return task


class FakeTermic(unittest.TestCase):
   def setUp(self):
      self.temp = tempfile.TemporaryDirectory()
      base = Path(self.temp.name)
      self.world_path = base / "world.json"
      self.log_path = base / "calls.jsonl"
      self.state = base / "state"
      self.project = base / "project"
      self.project.mkdir()
      self.log_path.touch()
      self.set_world({"tasks": []})
      self.env = {
         **os.environ,
         "TERMIC_CLI": str(FAKE_CLI),
         "TF_FAKE_WORLD": str(self.world_path),
         "TF_FAKE_LOG": str(self.log_path),
         "TF_STATE_DIR": str(self.state),
         "TERMIC_TASK": "main",
         "TERMIC_TASK_ID": "00000000-0000-4000-8000-000000000000",
         "TERMIC_TAB_ID": "tab-orch",
         "XDG_CONFIG_HOME": str(base / "config"),
      }
      self.env.pop("CLAUDE_PLUGIN_DATA", None)

   def tearDown(self):
      self.temp.cleanup()

   def set_world(self, world):
      self.world_path.write_text(json.dumps(world), encoding="utf-8")

   def world(self):
      return json.loads(self.world_path.read_text(encoding="utf-8"))

   def calls(self):
      lines = self.log_path.read_text(encoding="utf-8").splitlines()
      return [json.loads(line)["argv"] for line in lines]

   def calls_of(self, verb):
      return [argv for argv in self.calls() if argv[:len(verb.split())] == verb.split()]

   def tf(self, *args, stdin=None):
      return subprocess.run(
         [sys.executable, str(TF), *args],
         input=stdin,
         capture_output=True,
         text=True,
         env=self.env,
         cwd=self.project,
      )
