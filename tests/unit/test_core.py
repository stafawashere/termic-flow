import os
import unittest
from unittest import mock

from tf_lib import core
from tf_lib.profile import PLUGIN_ROOT, deep_merge, read_json


class TaskNames(unittest.TestCase):
   def setUp(self):
      self.profile = read_json(PLUGIN_ROOT / "profiles" / "default.json")

   def test_valid_name_is_kind_colon_subject(self):
      self.assertEqual(core.task_name(self.profile, "fix", "vite-chunk-warning"), "fix: vite-chunk-warning")

   def test_unknown_kind_is_refused(self):
      with self.assertRaises(core.TfError):
         core.task_name(self.profile, "hotfix", "x")

   def test_subject_must_be_kebab(self):
      for subject in ("Vite", "two words", "trailing-", "under_score"):
         with self.assertRaises(core.TfError):
            core.task_name(self.profile, "fix", subject)

   def test_every_default_kind_maps_to_a_real_group_colour(self):
      for kind in self.profile["kinds"]:
         self.assertIn(core.kind_colour(self.profile, kind), core.VALID_COLOURS)

   def test_gray_is_rejected_because_termic_has_no_gray(self):
      broken = deep_merge(self.profile, {"kinds": {"ops": "gray"}})

      with self.assertRaises(core.TfError):
         core.kind_colour(broken, "ops")

   def test_role_suffix_is_allowed_but_base_must_be_known(self):
      self.assertEqual(core.check_role(self.profile, "review-opus"), "review-opus")

      with self.assertRaises(core.TfError):
         core.check_role(self.profile, "Terminal")


class Signing(unittest.TestCase):
   def test_signed_prompt_names_sender_and_reply_route(self):
      env = {"TERMIC_TASK": "main", "TERMIC_TASK_ID": "abc-123", "TERMIC_TAB_ID": "tab-9"}

      with mock.patch.dict(os.environ, env):
         signed = core.sign("do the thing")

      self.assertTrue(signed.startswith("[message from agent:claude task:main id:abc-123]"))
      self.assertIn("send abc-123 --tab tab-9 -p", signed)
      self.assertTrue(signed.endswith("-- agent:claude task:main id:abc-123"))

   def test_no_reply_route_outside_a_task(self):
      with mock.patch.dict(os.environ, {}, clear=True):
         signed = core.sign("x")

      self.assertIn("task:outside id:none", signed)
      self.assertNotIn("When done", signed)

   def test_em_dash_is_refused(self):
      with self.assertRaises(core.TfError):
         core.check_text("a " + core.EM_DASH + " b")
