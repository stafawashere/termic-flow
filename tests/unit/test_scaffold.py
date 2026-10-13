import unittest

from tests.helpers import make_task
from tf_lib import setup
from tf_lib.core import TfError
from tf_lib.profile import PLUGIN_ROOT, deep_merge, read_json


def sample_profile(**overrides):
   profile = {
      "agent": "claude",
      "kinds": {"feat": "teal", "docs": "blue"},
      "scaffold": {
         "categories": [
            {
               "name": "Billing",
               "color": "purple",
               "sections": [
                  {"name": "invoices", "kind": "feat", "tabs": ["api", "ui"]},
                  {"name": "refunds", "kind": "docs", "tabs": []},
               ],
            },
            {"name": "Auth", "color": "red", "sections": [{"name": "login", "kind": "feat", "tabs": ["api"]}]},
         ]
      },
   }
   profile.update(overrides)
   return profile


class DefaultProfile(unittest.TestCase):
   def test_ships_an_empty_scaffold(self):
      default = read_json(PLUGIN_ROOT / "profiles" / "default.json")
      self.assertEqual(default["scaffold"], {"categories": []})

   def test_project_file_overrides_scaffold_through_the_merge(self):
      default = read_json(PLUGIN_ROOT / "profiles" / "default.json")
      override = {"scaffold": {"categories": [{"name": "Billing", "color": "blue", "sections": []}]}}
      merged = deep_merge(default, override)
      self.assertEqual(merged["scaffold"]["categories"][0]["name"], "Billing")


class Validation(unittest.TestCase):
   def test_accepts_a_well_formed_scaffold(self):
      setup.validate_scaffold(sample_profile())

   def test_rejects_unknown_section_kind(self):
      profile = sample_profile()
      profile["scaffold"]["categories"][0]["sections"][0]["kind"] = "nonsense"
      with self.assertRaisesRegex(TfError, "kind 'nonsense'"):
         setup.validate_scaffold(profile)

   def test_rejects_colour_outside_the_group_palette(self):
      profile = sample_profile()
      profile["scaffold"]["categories"][0]["color"] = "magenta"
      with self.assertRaisesRegex(TfError, "colour 'magenta'"):
         setup.validate_scaffold(profile)

   def test_rejects_duplicate_category_names(self):
      profile = sample_profile()
      profile["scaffold"]["categories"][1]["name"] = "Billing"
      with self.assertRaisesRegex(TfError, "category 'Billing'"):
         setup.validate_scaffold(profile)

   def test_rejects_duplicate_section_names_across_categories(self):
      profile = sample_profile()
      profile["scaffold"]["categories"][1]["sections"][0]["name"] = "invoices"
      with self.assertRaisesRegex(TfError, "section 'invoices'"):
         setup.validate_scaffold(profile)


class Malformed(unittest.TestCase):
   def test_missing_names_and_kinds_raise_tf_errors(self):
      nameless_category = sample_profile(scaffold={"categories": [{"color": "blue", "sections": []}]})
      nameless_section = sample_profile(scaffold={"categories": [{"name": "A", "color": "blue", "sections": [{"kind": "feat"}]}]})
      no_kinds = sample_profile()
      del no_kinds["kinds"]

      for profile in (nameless_category, nameless_section, no_kinds):
         with self.assertRaises(TfError):
            setup.validate_scaffold(profile)


class Plan(unittest.TestCase):
   def test_empty_scaffold_plans_nothing(self):
      self.assertEqual(setup.scaffold_plan(sample_profile(scaffold={"categories": []}), []), [])

   def test_orders_rows_new_then_group_then_tabs(self):
      rows = setup.scaffold_plan(sample_profile(), [])
      self.assertEqual(rows[:4], [
         ["new", "feat: invoices", "--agent", "claude"],
         ["group", "feat: invoices", "--name", "Billing", "--color", "purple"],
         ["tab", "feat: invoices", "--tab", "1", "--title", "api"],
         ["tab", "feat: invoices", "--title", "ui"],
      ])
      self.assertEqual(rows[4:6], [
         ["new", "docs: refunds", "--agent", "claude"],
         ["group", "docs: refunds", "--name", "Billing", "--color", "purple"],
      ])
      self.assertEqual(len(rows), 9)

   def test_skips_everything_already_present(self):
      tabs = [
         {"id": "t1", "index": 1, "kind": "agent", "title": "api", "state": "idle", "queued": 0},
         {"id": "t2", "index": 2, "kind": "agent", "title": "ui", "state": "idle", "queued": 0},
      ]
      tasks = [
         make_task("feat: invoices", "11111111-aaaa", group={"name": "Billing", "color": "purple"}, tabs=tabs),
         make_task("docs: refunds", "22222222-bbbb", group={"name": "Billing", "color": "purple"}),
         make_task("feat: login", "33333333-cccc", group={"name": "Auth", "color": "red"}, tabs=tabs[:1]),
      ]
      self.assertEqual(setup.scaffold_plan(sample_profile(), tasks), [])

   def test_adds_only_the_missing_pieces_of_an_existing_task(self):
      tabs = [{"id": "t1", "index": 1, "kind": "agent", "title": "api", "state": "idle", "queued": 0}]
      tasks = [make_task("feat: invoices", "11111111-aaaa", group=None, tabs=tabs)]
      rows = setup.scaffold_plan(sample_profile(), tasks)
      self.assertEqual(rows[0], ["group", "feat: invoices", "--name", "Billing", "--color", "purple"])
      self.assertEqual(rows[1], ["tab", "feat: invoices", "--title", "ui"])
      self.assertNotIn(["new", "feat: invoices", "--agent", "claude"], rows)

   def test_accepts_real_snapshot_rows(self):
      snapshot = [
         {"id": "8219bc17", "name": "feat: invoices", "tabs": 1, "group": "Billing"},
         {"id": "9a1b2c3d", "name": "docs: refunds", "tabs": 1, "group": ""},
         {"id": "7f6e5d4c", "name": "feat: login", "tabs": 2, "group": "Auth"},
      ]
      rows = setup.scaffold_plan(sample_profile(), snapshot)
      self.assertEqual(rows, [
         ["tab", "feat: invoices", "--title", "api"],
         ["tab", "feat: invoices", "--title", "ui"],
         ["group", "docs: refunds", "--name", "Billing", "--color", "purple"],
      ])

   def test_tab_count_of_a_setup_created_task_covers_its_titled_seed_tab(self):
      snapshot = [
         {"id": "8219bc17", "name": "feat: invoices", "tabs": 1, "group": "Billing"},
         {"id": "9a1b2c3d", "name": "docs: refunds", "tabs": 1, "group": "Billing"},
         {"id": "7f6e5d4c", "name": "feat: login", "tabs": 1, "group": "Auth"},
      ]
      rows = setup.scaffold_rows(sample_profile(), snapshot, adopted={"feat: invoices", "feat: login"})
      self.assertEqual([row["argv"] for row in rows], [["tab", "feat: invoices", "--title", "ui"]])

   def test_plan_refuses_an_invalid_scaffold(self):
      profile = sample_profile()
      profile["scaffold"]["categories"][0]["color"] = "magenta"
      with self.assertRaises(TfError):
         setup.scaffold_plan(profile, [])


if __name__ == "__main__":
   unittest.main()
