import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tf_lib import routing
from tf_lib.core import TfError


def load(profile=None, user=None):
   with tempfile.TemporaryDirectory() as config:
      if user is not None:
         folder = Path(config) / "termic-flow"
         folder.mkdir()
         (folder / "routing.json").write_text(json.dumps(user), encoding="utf-8")

      with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
         return routing.load_routing(profile or {})


class Defaults(unittest.TestCase):
   def setUp(self):
      self.table = load()

   def pick(self, role, **kwargs):
      return routing.route(self.table, role, **kwargs)["model"]

   def test_mechanical_roles_get_haiku(self):
      for role in ("scout", "packer", "audit"):
         self.assertEqual(self.pick(role), "haiku")

   def test_plain_fix_gets_sonnet_and_perf_gets_opus(self):
      self.assertEqual(self.pick("impl", kind="fix"), "sonnet")
      self.assertEqual(self.pick("impl", kind="perf"), "opus")

   def test_flags_promote_impl_to_opus(self):
      self.assertEqual(self.pick("impl", kind="feat", flags=["cross-component"]), "opus")

   def test_high_risk_review_gets_opus(self):
      self.assertEqual(self.pick("review", risk="high"), "opus")
      self.assertEqual(self.pick("review", risk="low"), "sonnet")

   def test_first_reasoning_failure_retries_same_model_then_steps_up(self):
      self.assertEqual(self.pick("impl", kind="fix", failed_attempts=1, failure="reasoning"), "sonnet")
      self.assertEqual(self.pick("impl", kind="fix", failed_attempts=2, failure="reasoning"), "opus")

   def test_environment_failures_never_escalate(self):
      self.assertEqual(self.pick("impl", kind="fix", failed_attempts=5, failure="environment"), "sonnet")

   def test_fable_is_off_unless_allowed(self):
      self.assertEqual(self.pick("plan", failed_attempts=3, failure="reasoning"), "opus")


class Overrides(unittest.TestCase):
   def test_user_rule_wins_over_default(self):
      table = load(user={"rules": [{"id": "mine", "roles": ["impl"], "model": "opus"}]})
      self.assertEqual(routing.route(table, "impl", kind="fix")["rule"], "mine")

   def test_project_rule_wins_over_user_rule(self):
      user = {"rules": [{"id": "user", "roles": ["review"], "model": "opus"}]}
      project = {"routing": {"rules": [{"id": "project", "roles": ["review"], "model": "haiku"}]}}
      table = load(profile=project, user=user)
      self.assertEqual(routing.route(table, "review")["rule"], "project")

   def test_allow_fable_opens_the_top_rung(self):
      table = load(user={"allow_fable": True})
      choice = routing.route(table, "plan", failed_attempts=2, failure="reasoning")
      self.assertEqual(choice["model_id"], "claude-fable-5-1")

   def test_unknown_model_is_rejected(self):
      with self.assertRaises(TfError):
         load(user={"rules": [{"id": "bad", "model": "gpt"}]})
