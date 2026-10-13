import json

from tests.helpers import FakeTermic, make_task

OWN_ID = "00000000-0000-4000-8000-000000000000"
PROFILE = {"base": "main", "kinds": {"feat": "teal", "ops": "pink"}}


class OrchestratorName(FakeTermic):
   def setUp(self):
      super().setUp()
      (self.project / ".termic-flow.json").write_text(json.dumps(PROFILE), encoding="utf-8")

   def audit(self):
      return json.loads(self.tf("audit").stdout)

   def test_run_start_renames_default_named_orchestrator(self):
      self.env["TERMIC_TASK"] = "claude-1"
      self.set_world({"tasks": [make_task("claude-1", OWN_ID)]})
      result = self.tf("run", "start", "dispatch", "invoices")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(self.calls_of("rename"), [["rename", OWN_ID, "ops: dispatch invoices"]])

   def test_run_start_leaves_a_named_task_alone(self):
      self.env["TERMIC_TASK"] = "main"
      self.set_world({"tasks": [make_task("main", OWN_ID, is_main_checkout=True)]})
      result = self.tf("run", "start", "dispatch", "invoices")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(self.calls_of("rename"), [])

   def test_audit_flags_a_dirty_main_checkout_separately(self):
      dirty = {"files_changed": 2, "insertions": 5, "deletions": 1, "untracked": 0}
      self.set_world({"tasks": [make_task("main", OWN_ID, is_main_checkout=True, diff=dirty)]})
      audit = self.audit()
      self.assertEqual(audit["flags"]["dirty_main"], ["main"])
      self.assertEqual(audit["counts"]["dirty_main"], 1)
      self.assertEqual(audit["flags"]["bad_name"], [])

   def test_audit_flags_untracked_only_main_checkout(self):
      untracked = {"files_changed": 0, "insertions": 0, "deletions": 0, "untracked": 1}
      self.set_world({"tasks": [make_task("main", OWN_ID, is_main_checkout=True, diff=untracked)]})
      self.assertEqual(self.audit()["flags"]["dirty_main"], ["main"])

   def test_audit_does_not_flag_a_clean_main_checkout(self):
      self.set_world({"tasks": [make_task("main", OWN_ID, is_main_checkout=True)]})
      self.assertEqual(self.audit()["flags"]["dirty_main"], [])

   def test_audit_does_not_flag_a_dirty_worktree_as_dirty_main(self):
      dirty = {"files_changed": 3, "insertions": 5, "deletions": 1, "untracked": 0}
      self.set_world({"tasks": [make_task("feat: invoices", OWN_ID, diff=dirty)]})
      self.assertEqual(self.audit()["flags"]["dirty_main"], [])

   def test_audit_still_flags_a_default_orchestrator_name(self):
      self.set_world({"tasks": [make_task("claude-1", OWN_ID)]})
      self.assertEqual(self.audit()["flags"]["bad_name"], ["claude-1"])
