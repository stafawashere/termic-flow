import json
import subprocess

from tests.helpers import FakeTermic, make_task

TASK_ID = "11111111-1111-4111-8111-111111111111"
NAME = "docs: run-end"
OTHER_ID = "33333333-3333-4333-8333-333333333333"
OTHER_NAME = "fix: still-going"


class RunEnd(FakeTermic):
   def seed_state(self):
      self.state.mkdir(parents=True, exist_ok=True)
      other_tab = self.state / "current-run-tab-other.json"
      other_tab.write_text(json.dumps({"pad": "x", "slug": "other", "workflow": "plan-build"}), encoding="utf-8")
      kept = [other_tab]

      for folder in ("approvals", "tested", "landed", "accepted"):
         (self.state / folder).mkdir(parents=True, exist_ok=True)
         marker = self.state / folder / "22222222-2222-4222-8222-222222222222"
         marker.write_text(json.dumps({"note": "kept"}), encoding="utf-8")
         kept.append(marker)

      return kept

   def test_run_end_removes_only_this_tabs_run_file(self):
      started = self.tf("run", "start", "plan-build", "demo-slug")
      self.assertEqual(started.returncode, 0, started.stderr)
      own_run = self.state / "current-run-tab-orch.json"
      self.assertTrue(own_run.is_file())
      kept = self.seed_state()

      ended = self.tf("run", "end")
      self.assertEqual(ended.returncode, 0, ended.stderr)
      self.assertFalse(own_run.exists())

      for path in kept:
         self.assertTrue(path.is_file(), path)

   def test_run_end_without_an_open_run_fails(self):
      ended = self.tf("run", "end")
      self.assertNotEqual(ended.returncode, 0)


class RunEndsWhenWorkLeaves(FakeTermic):
   def git(self, cwd, *args):
      subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)

   def setUp(self):
      super().setUp()
      repo = self.project / "repo"
      repo.mkdir()
      self.git(repo, "init", "-q", "-b", "main")
      self.git(repo, "config", "user.email", "e2e@termic.dev")
      self.git(repo, "config", "user.name", "alice")
      (repo / "doc.md").write_text("old line\n")
      self.git(repo, "add", "-A")
      self.git(repo, "commit", "-q", "-m", "base")
      worktree = self.project / "wt"
      self.git(repo, "worktree", "add", "-q", "-b", "docs-x", str(worktree))
      (worktree / "doc.md").write_text("new line\n")
      dirty = {"files_changed": 1, "insertions": 1, "deletions": 1, "untracked": 0}
      self.set_world({"tasks": [make_task(NAME, TASK_ID, path=str(worktree), diff=dirty)]})
      started = self.tf("run", "start", "dispatch", "demo-slug")
      self.assertEqual(started.returncode, 0, started.stderr)
      self.own_run = self.state / "current-run-tab-orch.json"
      self.kept = RunEnd.seed_state(self)

   def record_in_run(self, *names):
      world = self.world()
      pad = json.loads(self.tf("run", "show").stdout)["pad"]
      recorded = json.dumps({name: {"role": "impl"} for name in names})
      world["pads"][pad] = world["pads"][pad].replace('"tasks": {}', '"tasks": ' + recorded)
      self.set_world(world)

   def add_task(self, name, task_id):
      world = self.world()
      world["tasks"].append(make_task(name, task_id))
      self.set_world(world)

   def assert_run_closed(self):
      self.assertFalse(self.own_run.exists())

      for path in self.kept:
         self.assertTrue(path.is_file(), path)

   def test_patch_land_closes_the_run(self):
      self.tf("tested", TASK_ID, "read it")
      landed = self.tf("patch", NAME)
      self.assertEqual(landed.returncode, 0, landed.stderr)
      self.assert_run_closed()

   def test_do_apply_closes_the_run(self):
      self.tf("tested", TASK_ID, "read it")
      self.tf("approve", TASK_ID)
      applied = self.tf("do", "apply", NAME)
      self.assertEqual(applied.returncode, 0, applied.stderr)
      self.assert_run_closed()

   def test_do_archive_closes_the_run(self):
      self.set_world({**self.world(), "tasks": [make_task(NAME, TASK_ID)]})
      self.tf("approve", TASK_ID)
      archived = self.tf("do", "archive", NAME)
      self.assertEqual(archived.returncode, 0, archived.stderr)
      self.assert_run_closed()

   def test_refused_archive_keeps_the_run(self):
      archived = self.tf("do", "archive", NAME)
      self.assertNotEqual(archived.returncode, 0)
      self.assertTrue(self.own_run.is_file())

   def test_land_keeps_the_run_while_another_spawned_task_is_live(self):
      self.add_task(OTHER_NAME, OTHER_ID)
      self.record_in_run(NAME, OTHER_NAME)
      self.tf("tested", TASK_ID, "read it")
      landed = self.tf("patch", NAME)
      self.assertEqual(landed.returncode, 0, landed.stderr)
      self.assertTrue(self.own_run.is_file())
      self.assertIn(f"run stays open: 1 live task ({OTHER_NAME})", landed.stderr)

   def test_archive_of_the_last_live_spawned_task_closes_the_run(self):
      self.set_world({**self.world(), "tasks": [make_task(NAME, TASK_ID)]})
      self.record_in_run(NAME, OTHER_NAME)
      self.tf("approve", TASK_ID)
      archived = self.tf("do", "archive", NAME)
      self.assertEqual(archived.returncode, 0, archived.stderr)
      self.assert_run_closed()

   def test_landed_spawned_task_no_longer_holds_the_run(self):
      self.add_task(OTHER_NAME, OTHER_ID)
      (self.state / "landed").mkdir(exist_ok=True)
      (self.state / "landed" / OTHER_ID).write_text(json.dumps({"note": "landed"}), encoding="utf-8")
      self.record_in_run(NAME, OTHER_NAME)
      self.tf("tested", TASK_ID, "read it")
      landed = self.tf("patch", NAME)
      self.assertEqual(landed.returncode, 0, landed.stderr)
      self.assert_run_closed()

   def test_unreadable_run_pad_does_not_fail_the_archive(self):
      self.set_world({"tasks": [make_task(NAME, TASK_ID)]})
      self.tf("approve", TASK_ID)
      archived = self.tf("do", "archive", NAME)
      self.assertEqual(archived.returncode, 0, archived.stderr)
      self.assertTrue(self.own_run.is_file())
      self.assertIn("run stays open:", archived.stderr)
