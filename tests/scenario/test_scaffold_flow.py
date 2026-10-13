import json

from tests.helpers import FakeTermic, make_task

OWN_ID = "00000000-0000-4000-8000-000000000000"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
RESTRUCTURE_VERBS = ("rename", "move", "archive", "close")


def scaffold(*categories):
   return {"base": "main", "kinds": {"feat": "teal", "docs": "blue"}, "scaffold": {"categories": list(categories)}}


GUIDES = {"name": "docs", "color": "blue", "sections": [{"name": "guides", "kind": "docs", "tabs": ["outline"]}]}
NEW_INVOICES = ["new", "feat: invoices", "--worktree", "--base", "main", "--agent", "claude", "--no-group", "--project", "demo"]


BILLING = {
   "name": "Billing",
   "color": "purple",
   "sections": [
      {"name": "invoices", "kind": "feat", "tabs": ["api", "ui"]},
      {"name": "refunds", "kind": "docs", "tabs": []},
   ],
}


class ScaffoldFlow(FakeTermic):
   def setUp(self):
      super().setUp()
      self.set_world({"tasks": [self.hub()]})

   def hub(self):
      return make_task("main", OWN_ID, is_main_checkout=True)

   def write_profile(self, profile):
      (self.project / ".termic-flow.json").write_text(json.dumps(profile), encoding="utf-8")

   def task_named(self, name):
      return next(task for task in self.world()["tasks"] if task["name"] == name)

   def restructure_calls(self):
      return [argv for argv in self.calls() if argv[0] in RESTRUCTURE_VERBS or argv[:2] == ["tab", "close"]]

   def test_preview_lists_rows_and_changes_nothing(self):
      self.write_profile(scaffold(BILLING))
      result = self.tf("setup", "--preview")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertIn("create   new 'feat: invoices' --worktree --base main --agent claude --no-group --project demo", result.stdout)
      self.assertIn("create   tab 'feat: invoices' --tab 1 --title api", result.stdout)
      self.assertIn("create   tab 'feat: invoices' --title ui", result.stdout)
      self.assertEqual(self.world()["tasks"], [self.hub()])
      mutating = [argv for argv in self.calls() if argv[0] not in ("list", "status")]
      self.assertEqual(mutating, [])

   def test_apply_titles_the_seed_tab_then_is_idempotent(self):
      self.write_profile(scaffold(BILLING))
      first = self.tf("setup", "--apply")
      self.assertEqual(first.returncode, 0, first.stderr)

      invoices = self.task_named("feat: invoices")
      self.assertEqual([tab["title"] for tab in invoices["tabs"]], ["api", "ui"])
      self.assertEqual(invoices["group"], {"name": "Billing", "color": "purple"})
      self.assertEqual(self.task_named("docs: refunds")["group"], {"name": "Billing", "color": "purple"})
      self.assertIn(NEW_INVOICES, self.calls_of("new"))
      self.assertFalse(self.task_named("feat: invoices")["is_main_checkout"])

      calls_before = len(self.calls_of("new")) + len(self.calls_of("group")) + len(self.calls_of("tab"))
      second = self.tf("setup", "--apply")
      self.assertEqual(second.returncode, 0, second.stderr)
      self.assertEqual(json.loads(second.stdout), {"ran": [], "approve": []})
      calls_after = len(self.calls_of("new")) + len(self.calls_of("group")) + len(self.calls_of("tab"))
      self.assertEqual(calls_after, calls_before)
      self.assertEqual(len(self.world()["tasks"]), 3)

   def test_regroup_of_an_existing_task_is_only_an_approval_row(self):
      self.write_profile(scaffold(BILLING))
      existing = make_task("docs: refunds", OTHER_ID, group={"name": "batch", "color": "teal"})
      self.set_world({"tasks": [self.hub(), existing]})

      preview = self.tf("setup", "--preview")
      self.assertIn(f"approve  group 'docs: refunds' --name Billing --color purple  (regroups an existing task; ! tf approve {OTHER_ID}", preview.stdout)

      applied = self.tf("setup", "--apply")
      self.assertEqual(applied.returncode, 0, applied.stderr)
      self.assertEqual(self.task_named("docs: refunds")["group"], {"name": "batch", "color": "teal"})
      group_targets = [argv[1] for argv in self.calls_of("group")]
      self.assertNotIn(OTHER_ID, group_targets)
      self.assertNotIn("docs: refunds", group_targets)
      self.assertEqual(self.restructure_calls(), [])

   def test_same_name_group_with_another_colour_needs_approval(self):
      self.write_profile(scaffold(BILLING))
      elsewhere = make_task("feat: ledger", OTHER_ID, group={"name": "Billing", "color": "green"})
      self.set_world({"tasks": [self.hub(), elsewhere]})

      preview = self.tf("setup", "--preview")
      self.assertIn("approve  group 'feat: invoices' --name Billing --color purple  (group 'Billing' already exists with colour green", preview.stdout)

      self.tf("setup", "--apply")
      self.assertEqual(self.calls_of("group"), [])
      self.assertEqual(self.task_named("feat: ledger")["group"], {"name": "Billing", "color": "green"})

   def test_apply_never_touches_the_calling_task(self):
      self.write_profile(scaffold(BILLING))
      own = make_task("feat: invoices", OWN_ID, group={"name": "batch", "color": "teal"}, tabs=[])
      self.set_world({"tasks": [own]})

      preview = self.tf("setup", "--preview")
      self.assertIn("targets a hub or the calling task", preview.stdout)

      applied = self.tf("setup", "--apply")
      self.assertEqual(applied.returncode, 0, applied.stderr)
      touched = [argv for argv in self.calls() if argv[0] in ("group", "tab") and argv[1] in (OWN_ID, "feat: invoices")]
      self.assertEqual(touched, [])
      self.assertEqual(self.task_named("feat: invoices")["tabs"], [])

   def test_one_section_apply_then_preview_plans_nothing(self):
      self.write_profile(scaffold(GUIDES))
      applied = self.tf("setup", "--apply")
      self.assertEqual(applied.returncode, 0, applied.stderr)
      self.assertEqual([tab["title"] for tab in self.task_named("docs: guides")["tabs"]], ["outline"])

      preview = self.tf("setup", "--preview")
      self.assertEqual(preview.stdout.strip(), "nothing to scaffold")

   def test_a_row_that_failed_after_new_is_retried_as_a_create(self):
      self.write_profile(scaffold(GUIDES))
      world = self.world()
      world["exit"] = {"group": 1}
      self.set_world(world)
      failed = self.tf("setup", "--apply")
      self.assertNotEqual(failed.returncode, 0)

      world = self.world()
      del world["exit"]
      self.set_world(world)
      preview = self.tf("setup", "--preview")
      self.assertIn("create   group 'docs: guides' --name docs --color blue", preview.stdout)
      self.assertNotIn("approve", preview.stdout)

      retried = self.tf("setup", "--apply")
      self.assertEqual(retried.returncode, 0, retried.stderr)
      self.assertEqual(self.task_named("docs: guides")["group"], {"name": "docs", "color": "blue"})
      self.assertEqual(len(self.calls_of("new")), 1)

   def test_a_seed_tab_title_that_failed_after_new_is_retried(self):
      self.write_profile(scaffold(GUIDES))
      world = self.world()
      world["exit"] = {"tab": 1}
      self.set_world(world)
      failed = self.tf("setup", "--apply")
      self.assertNotEqual(failed.returncode, 0)

      world = self.world()
      del world["exit"]
      self.set_world(world)
      preview = self.tf("setup", "--preview")
      self.assertEqual(preview.stdout.strip(), "create   tab 'docs: guides' --tab 1 --title outline")

      retried = self.tf("setup", "--apply")
      self.assertEqual(retried.returncode, 0, retried.stderr)
      self.assertEqual([tab["title"] for tab in self.task_named("docs: guides")["tabs"]], ["outline"])
      self.assertEqual(self.tf("setup", "--preview").stdout.strip(), "nothing to scaffold")

   def test_tab_titles_come_from_status_not_the_list_count(self):
      self.write_profile(scaffold(BILLING))
      titled = [
         {"id": "t1", "index": 1, "kind": "agent", "title": "api", "state": "idle", "queued": 0},
         {"id": "t2", "index": 2, "kind": "agent", "title": "ui", "state": "idle", "queued": 0},
      ]
      billing = {"name": "Billing", "color": "purple"}
      invoices = make_task("feat: invoices", OTHER_ID, group=billing, tabs=titled, open_tabs=2)
      refunds = make_task("docs: refunds", "33333333-3333-4333-8333-333333333333", group=billing)
      self.set_world({"tasks": [self.hub(), invoices, refunds]})

      preview = self.tf("setup", "--preview")
      self.assertEqual(preview.stdout.strip(), "nothing to scaffold")

   def test_audit_does_not_call_a_fresh_seed_task_finished(self):
      self.write_profile(scaffold(GUIDES))
      self.assertEqual(self.tf("setup", "--apply").returncode, 0)
      leftover = make_task("feat: old-thing", OTHER_ID, group={"name": "batch", "color": "teal"})
      world = self.world()
      world["tasks"].append(leftover)

      for task in world["tasks"]:
         task["work_state"] = "idle"

      self.set_world(world)
      audit = json.loads(self.tf("audit").stdout)
      self.assertEqual(audit["flags"]["finished_unarchived"], ["feat: old-thing"])
      self.assertNotIn("docs: guides", [name for names in audit["flags"].values() for name in names])
