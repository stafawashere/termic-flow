import json

from tf_lib import core, routing
from tf_lib.profile import load_profile
from tests.helpers import FakeTermic, make_task

OWN_ID = "00000000-0000-4000-8000-000000000000"


class AuditKind(FakeTermic):
   def profile(self):
      return load_profile(str(self.project))

   def test_default_profile_has_a_readonly_audit_kind_coloured_like_review(self):
      kinds = self.profile()["kinds"]
      self.assertEqual(kinds.get("audit"), kinds["review"])

   def test_audit_task_name_is_accepted(self):
      self.assertEqual(core.task_name(self.profile(), "audit", "docs-drift"), "audit: docs-drift")

   def test_audit_kind_routes_like_review_through_the_real_table(self):
      table = routing.load_routing(self.profile())
      ordinary = routing.route(table, "review", kind="audit")
      risky = routing.route(table, "review", kind="audit", risk="high")
      self.assertEqual((ordinary["rule"], ordinary["model"]), ("review", "sonnet"))
      self.assertEqual((risky["rule"], risky["model"]), ("review-risk", "opus"))

   def test_tf_group_accepts_audit_kind(self):
      self.set_world({"tasks": [make_task("main", OWN_ID, group={"name": "", "color": ""})]})
      result = self.tf("group", "sweep", "audit")
      self.assertEqual(result.returncode, 0, result.stderr)


class GroupColour(FakeTermic):
   def setUp(self):
      super().setUp()
      (self.project / ".termic-flow.json").write_text(json.dumps({"base": "main"}), encoding="utf-8")

   def test_existing_group_is_not_recoloured(self):
      other = make_task("fix: other", "11111111-aaaa", group={"name": "sweep", "color": "purple"})
      self.set_world({"tasks": [make_task("main", OWN_ID, group={"name": "", "color": ""}), other]})
      result = self.tf("group", "sweep", "fix")
      self.assertEqual(result.returncode, 0, result.stderr)
      sent = self.calls_of("group")[0]
      self.assertNotIn("--color", sent)
      self.assertEqual(json.loads(result.stdout)["color"], "purple")

   def test_new_group_gets_the_kind_colour(self):
      self.set_world({"tasks": [make_task("main", OWN_ID, group={"name": "", "color": ""})]})
      result = self.tf("group", "fresh", "fix")
      self.assertEqual(result.returncode, 0, result.stderr)
      sent = self.calls_of("group")[0]
      self.assertEqual(sent[sent.index("--color") + 1], "red")
