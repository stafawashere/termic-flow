import json
import subprocess
import sys
import time

from tests.helpers import TF, FakeTermic, make_task

TASK_ID = "11111111-1111-4111-8111-111111111111"
NAME = "fix: flaky-thing"


class Mutations(FakeTermic):
   def setUp(self):
      super().setUp()
      self.set_world({"tasks": [make_task(NAME, TASK_ID)]})

   def approve(self):
      return self.tf("approve", TASK_ID, "ok")

   def test_archive_without_approval_never_reaches_the_cli(self):
      result = self.tf("do", "archive", NAME)
      self.assertEqual(result.returncode, 2)
      self.assertIn("tf approve " + TASK_ID, result.stderr)
      self.assertEqual(self.calls_of("archive"), [])

   def test_approved_archive_runs_by_id_with_yes(self):
      self.approve()
      result = self.tf("do", "archive", NAME)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(self.calls_of("archive"), [["archive", TASK_ID, "--yes"]])

   def test_task_vanishing_between_checks_aborts_before_acting(self):
      world = self.world()
      world["vanish_on_status"] = {TASK_ID: 1}
      self.set_world(world)
      self.approve()
      result = self.tf("do", "archive", NAME)
      self.assertEqual(result.returncode, 20, result.stderr)
      self.assertIn("stale", result.stderr)
      self.assertEqual(self.calls_of("archive"), [])

   def test_refused_archive_is_tried_once_and_queued_for_the_human(self):
      world = self.world()
      world["refuse"] = ["archive"]
      self.set_world(world)
      self.approve()
      result = self.tf("do", "archive", NAME)
      self.assertEqual(result.returncode, 21, result.stderr)
      self.assertEqual(len(self.calls_of("archive")), 1)
      script = (self.state / "fallback" / "adhoc.sh").read_text(encoding="utf-8")
      self.assertIn(f"status {TASK_ID}", script)
      self.assertIn(f"archive {TASK_ID} --yes", script)
      self.assertIn(["prop", "blocked", "needs-you"], self.calls())

   def test_archive_with_unlanded_diff_is_refused_even_when_approved(self):
      dirty = make_task(NAME, TASK_ID, diff={"files_changed": 2, "insertions": 5, "deletions": 0, "untracked": 0})
      self.set_world({"tasks": [dirty]})
      self.approve()
      result = self.tf("do", "archive", NAME)
      self.assertEqual(result.returncode, 2)
      self.assertIn("unlanded", result.stderr)
      self.assertEqual(self.calls_of("archive"), [])

   def test_apply_needs_the_manual_test_answer_then_unlocks_archive(self):
      dirty = make_task(NAME, TASK_ID, diff={"files_changed": 2, "insertions": 5, "deletions": 0, "untracked": 0})
      self.set_world({"tasks": [dirty]})
      blocked = self.tf("do", "apply", NAME)
      self.assertEqual(blocked.returncode, 2)
      self.assertIn("tf tested", blocked.stderr)
      self.assertEqual(self.calls_of("apply"), [])

      self.tf("tested", TASK_ID, "clicked through the dialog")
      applied = self.tf("do", "apply", NAME)
      self.assertEqual(applied.returncode, 0, applied.stderr)

      self.approve()
      archived = self.tf("do", "archive", NAME)
      self.assertEqual(archived.returncode, 0, archived.stderr)

   def test_settled_expectation_blocks_a_working_task(self):
      busy = make_task(NAME, TASK_ID, work_state="working")
      self.set_world({"tasks": [busy]})
      result = self.tf("do", "--expect", "settled", "send", NAME, "-p", "hi")
      self.assertEqual(result.returncode, 20)
      self.assertEqual(self.calls_of("send"), [])

   def test_rename_of_an_existing_task_needs_approval(self):
      result = self.tf("do", "rename", NAME, "fix: renamed")
      self.assertEqual(result.returncode, 2)
      self.assertIn("tf approve " + TASK_ID, result.stderr)
      self.assertEqual(self.calls_of("rename"), [])

   def test_approved_rename_runs_by_id(self):
      self.approve()
      result = self.tf("do", "rename", NAME, "fix: renamed")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(self.calls_of("rename"), [["rename", TASK_ID, "fix: renamed"]])

   def test_regrouping_an_existing_task_needs_approval(self):
      result = self.tf("do", "group", NAME, "--name", "other")
      self.assertEqual(result.returncode, 2)
      self.assertIn("tf approve " + TASK_ID, result.stderr)
      self.assertEqual(self.calls_of("group"), [])

   def test_regroup_swaps_the_task_not_a_flag_value_spelled_the_same(self):
      self.approve()
      result = self.tf("do", "group", "--name", NAME, NAME)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(self.calls_of("group"), [["group", "--name", NAME, TASK_ID]])

   def test_naming_a_new_group_stays_ungated(self):
      result = self.tf("do", "group", "--name", "fresh", "--color", "teal")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(self.calls_of("group"), [["group", "--name", "fresh", "--color", "teal"]])
      self.assertEqual(self.calls_of("status"), [])


class Locks(FakeTermic):
   def test_two_holders_of_one_lock_never_overlap(self):
      marks = self.project / "marks"
      body = f"import time,sys; open({str(marks)!r},'a').write('start\\n'); time.sleep(0.4); open({str(marks)!r},'a').write('end\\n')"
      runs = [
         subprocess.Popen([sys.executable, str(TF), "lock", "e2e", "--", sys.executable, "-c", body], env=self.env)
         for _ in range(2)
      ]

      for run in runs:
         run.wait(timeout=20)

      self.assertEqual(marks.read_text().split(), ["start", "end", "start", "end"])


class Runs(FakeTermic):
   def test_run_pad_carries_header_and_log_lines(self):
      started = json.loads(self.tf("run", "start", "dispatch", "demo-run").stdout)
      self.tf("log", "spawned something")
      pad_text = self.world()["pads"][started["pad"]]
      self.assertIn('"workflow": "dispatch"', pad_text)
      self.assertRegex(pad_text, r"- \d\d:\d\d spawned something")
      self.assertIn(["prop", "run", started["pad"]], self.calls())

   def test_new_routes_model_and_refuses_bad_names(self):
      ok = self.tf("new", "perf", "idle-cpu", "--packet", "pad-1")
      self.assertEqual(ok.returncode, 0, ok.stderr)
      new_call = self.calls_of("new")[0]
      self.assertIn("claude-opus-5-5", new_call)
      self.assertIn("perf: idle-cpu", new_call)

      bad = self.tf("new", "perf", "Idle CPU", "--packet", "pad-1")
      self.assertEqual(bad.returncode, 2)
      self.assertEqual(len(self.calls_of("new")), 1)


   def test_new_branches_worktree_from_the_local_checkout_branch(self):
      subprocess.run(["git", "init", "-q", "-b", "trunk", str(self.project)], check=True)
      result = self.tf("new", "fix", "stale-base", "--packet", "pad-1")
      self.assertEqual(result.returncode, 0, result.stderr)

      new_call = self.calls_of("new")[0]
      base_index = new_call.index("--base")
      self.assertEqual(new_call[base_index + 1], "trunk")


class AutoMarkers(FakeTermic):
   def setUp(self):
      super().setUp()
      reviewed_tabs = [{"id": "tab-1", "index": 1, "kind": "agent", "title": "impl", "state": "idle", "queued": 0, "props": [{"key": "phase", "value": "ready"}]}]
      self.set_world({"tasks": [make_task(NAME, TASK_ID, tabs=reviewed_tabs)]})

   def enable(self):
      (self.project / ".termic-flow.json").write_text(json.dumps({"auto_approve": True}), encoding="utf-8")

   def marker(self, folder):
      path = self.state / folder / TASK_ID
      return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

   def test_auto_is_refused_while_the_profile_has_it_off(self):
      result = self.tf("tested", TASK_ID, "--auto")
      self.assertEqual(result.returncode, 2)
      self.assertIsNone(self.marker("tested"))

   def test_auto_tested_needs_a_passed_review(self):
      self.enable()
      world = self.world()
      world["tasks"][0]["tabs"][0]["props"] = [{"key": "phase", "value": "review"}]
      self.set_world(world)
      result = self.tf("tested", TASK_ID, "--auto")
      self.assertEqual(result.returncode, 2)
      self.assertIsNone(self.marker("tested"))

   def test_auto_tested_records_a_marked_note_after_review(self):
      self.enable()
      result = self.tf("tested", TASK_ID, "--auto")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertTrue(self.marker("tested")["note"].startswith("auto: "))

   def test_auto_approve_needs_a_landed_task(self):
      self.enable()
      refused = self.tf("approve", TASK_ID, "--auto")
      self.assertEqual(refused.returncode, 2)
      self.assertIsNone(self.marker("approvals"))

      (self.state / "landed").mkdir(parents=True, exist_ok=True)
      (self.state / "landed" / TASK_ID).write_text(json.dumps({"task_id": TASK_ID, "note": "", "at": ""}), encoding="utf-8")
      allowed = self.tf("approve", TASK_ID, "--auto")
      self.assertEqual(allowed.returncode, 0, allowed.stderr)
      self.assertIsNotNone(self.marker("approvals"))

   def test_auto_approve_never_covers_a_hub(self):
      self.enable()
      hub_id = "22222222-2222-4222-8222-222222222222"
      self.set_world({"tasks": [make_task("plan", hub_id)]})
      (self.state / "landed").mkdir(parents=True, exist_ok=True)
      (self.state / "landed" / hub_id).write_text(json.dumps({"task_id": hub_id, "note": "", "at": ""}), encoding="utf-8")
      result = self.tf("approve", hub_id, "--auto")
      self.assertEqual(result.returncode, 2)


class PullRequests(FakeTermic):
   def test_pr_without_manual_test_answer_never_calls_the_forge(self):
      self.set_world({"tasks": [make_task(NAME, TASK_ID)]})
      result = self.tf("pr", NAME, "--", "--title", "x")
      self.assertEqual(result.returncode, 2)
      self.assertIn("tf tested", result.stderr)
      self.assertEqual(self.calls_of("path"), [])


class CrossTaskPads(FakeTermic):
   def test_worker_prompt_reads_the_packet_from_the_orchestrators_task(self):
      self.tf("new", "docs", "fix-ref", "--packet", "pad-9")
      new_stdin = [json.loads(line)["stdin"] for line in self.log_path.read_text().splitlines() if json.loads(line)["argv"][0] == "new"][0]
      self.assertIn("scratchpad read pad-9 --task 00000000-0000-4000-8000-000000000000", new_stdin)

   def test_new_titles_the_default_tab_with_the_role(self):
      self.tf("new", "docs", "fix-ref", "--packet", "pad-9")
      self.assertIn(["tab", "docs: fix-ref", "--tab", "1", "--title", "impl"], self.calls())

   def test_new_records_the_task_in_the_run_header(self):
      started = json.loads(self.tf("run", "start", "dispatch", "demo").stdout)
      self.tf("new", "docs", "fix-ref", "--packet", "pad-9")
      self.assertIn('"docs: fix-ref"', self.world()["pads"][started["pad"]])

   def test_report_reads_from_the_named_task(self):
      self.tf("report", "pad-x", "--task", "docs: fix-ref")
      self.assertIn(["scratchpad", "read", "pad-x", "--task", "docs: fix-ref"], self.calls())


class Acceptance(FakeTermic):
   BAD = "status: pass\nchecks: grep=1\nchanged: 1\nrisks: none\nnext: land\n"

   def setUp(self):
      super().setUp()
      self.set_world({"tasks": [make_task(NAME, TASK_ID)], "pads": {"pad-r": self.BAD}})

   def test_contradictory_report_is_rejected_with_the_accept_command(self):
      result = self.tf("report", "pad-r", "--task", NAME)
      self.assertEqual(result.returncode, 2)
      self.assertIn(f"tf accept {TASK_ID}", result.stderr)

   def test_human_acceptance_turns_it_into_a_logged_pass(self):
      self.tf("accept", TASK_ID, "grep exits 1 on absence")
      result = self.tf("report", "pad-r", "--task", NAME)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(json.loads(result.stdout)["accepted"], "grep exits 1 on absence")


class PatchLanding(FakeTermic):
   def git(self, cwd, *args):
      subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)

   def setUp(self):
      super().setUp()
      self.repo = self.project / "repo"
      self.repo.mkdir()
      self.git(self.repo, "init", "-q", "-b", "main")
      self.git(self.repo, "config", "user.email", "e2e@termic.dev")
      self.git(self.repo, "config", "user.name", "alice")
      (self.repo / "doc.md").write_text("old line\n")
      (self.repo / "other.txt").write_text("base\n")
      self.git(self.repo, "add", "-A")
      self.git(self.repo, "commit", "-q", "-m", "base")
      self.worktree = self.project / "wt"
      self.git(self.repo, "worktree", "add", "-q", "-b", "docs-x", str(self.worktree))
      (self.worktree / "doc.md").write_text("new line\n")
      (self.worktree / "added.md").write_text("fresh\n")
      (self.repo / "other.txt").write_text("someone else's edit\n")
      dirty = {"files_changed": 2, "insertions": 2, "deletions": 1, "untracked": 1}
      self.set_world({"tasks": [make_task(NAME, TASK_ID, path=str(self.worktree), diff=dirty)]})

   def test_patch_needs_the_manual_test_answer(self):
      result = self.tf("patch", NAME)
      self.assertEqual(result.returncode, 2)
      self.assertEqual((self.repo / "doc.md").read_text(), "old line\n")

   def test_patch_lands_only_the_task_diff_into_a_dirty_main_checkout(self):
      self.tf("tested", TASK_ID, "read it")
      result = self.tf("patch", NAME)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual((self.repo / "doc.md").read_text(), "new line\n")
      self.assertEqual((self.repo / "added.md").read_text(), "fresh\n")
      self.assertEqual((self.repo / "other.txt").read_text(), "someone else's edit\n")

      self.tf("approve", TASK_ID)
      archived = self.tf("do", "archive", NAME)
      self.assertEqual(archived.returncode, 0, archived.stderr)

   def test_patch_records_a_diff_already_merged_by_hand_without_touching_main(self):
      (self.repo / "doc.md").write_text("new line\n")
      (self.repo / "added.md").write_text("fresh\n")
      self.tf("tested", TASK_ID, "read it")
      result = self.tf("patch", NAME)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertIn("already", result.stdout)
      self.assertEqual((self.repo / "doc.md").read_text(), "new line\n")
      self.assertEqual((self.repo / "other.txt").read_text(), "someone else's edit\n")

      self.tf("approve", TASK_ID)
      archived = self.tf("do", "archive", NAME)
      self.assertEqual(archived.returncode, 0, archived.stderr)

   def test_hand_merge_next_to_other_new_code_still_counts_as_landed(self):
      (self.repo / "doc.md").write_text("main grew this\nnew line\nand this\n")
      (self.repo / "added.md").write_text("fresh\n")
      self.tf("tested", TASK_ID, "read it")
      result = self.tf("patch", NAME)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertIn("already", result.stdout)
      self.assertEqual((self.repo / "doc.md").read_text(), "main grew this\nnew line\nand this\n")

   def test_partly_merged_diff_is_not_recorded_as_landed(self):
      (self.repo / "doc.md").write_text("new line\n")
      self.tf("tested", TASK_ID, "read it")
      result = self.tf("patch", NAME)
      self.assertEqual(result.returncode, 2)
      self.assertNotIn("already", result.stdout)

      self.tf("approve", TASK_ID)
      archived = self.tf("do", "archive", NAME)
      self.assertNotEqual(archived.returncode, 0)


class ProjectScope(FakeTermic):
   ORCHESTRATOR_ID = "00000000-0000-4000-8000-000000000000"
   OTHER_PLAN_ID = "22222222-2222-4222-8222-222222222222"

   def setUp(self):
      super().setUp()
      orchestrator = make_task("chore: setup", self.ORCHESTRATOR_ID, project="mine", is_main_checkout=True)
      other_plan = make_task("plan", self.OTHER_PLAN_ID, project="elsewhere", is_main_checkout=True)
      self.set_world({"tasks": [orchestrator, other_plan]})

   def test_hubs_of_another_project_do_not_count(self):
      missing = json.loads(self.tf("hubs").stdout)["missing"]
      self.assertIn("plan", missing)

   def test_a_hub_name_never_resolves_to_another_projects_task(self):
      result = self.tf("tab", "plan", "spec", "--packet", "pad-1")
      self.assertNotEqual(result.returncode, 0)
      tab_calls = [argv for argv in self.calls_of("tab") if self.OTHER_PLAN_ID in argv]
      self.assertEqual(tab_calls, [])
