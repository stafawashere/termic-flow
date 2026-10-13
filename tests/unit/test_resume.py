import json
import re
import time

from tests.helpers import FakeTermic, make_task

HEADER = re.compile(r"```json run\n(.*?)\n```", re.S)
SLOW_ID = "11111111-1111-4111-8111-111111111111"
SLOW = "feat: slow"
DONE_ID = "22222222-2222-4222-8222-222222222222"
DONE = "fix: done"
STUCK_ID = "33333333-3333-4333-8333-333333333333"
STUCK = "docs: stuck"


def phase_prop(value):
   return {"key": "phase", "values": [value]}


class StallCase(FakeTermic):
   def start_run(self, *names):
      started = self.tf("run", "start", "dispatch", "demo-slug")
      self.assertEqual(started.returncode, 0, started.stderr)
      self.pad = json.loads(self.tf("run", "show").stdout)["pad"]
      self.edit_header(lambda header: header["tasks"].update({name: {"role": "impl"} for name in names}))

   def edit_header(self, change):
      world = self.world()
      text = world["pads"][self.pad]
      header = json.loads(HEADER.search(text).group(1))
      change(header)
      block = "```json run\n" + json.dumps(header, indent=2) + "\n```"
      world["pads"][self.pad] = HEADER.sub(lambda _: block, text, count=1)
      self.set_world(world)

   def age_stall(self, name, field, minutes):
      past = time.time() - minutes * 60
      self.edit_header(lambda header: header["stall"][name].update({field: past}))

   def add_pad(self, title, content="x"):
      world = self.world()
      pad_id = f"aaaaaaaa-aaaa-4aaa-8aaa-{len(world.get('pads', {})):012d}"
      world.setdefault("pads", {})[pad_id] = content
      world.setdefault("titles", {})[pad_id] = title
      self.set_world(world)
      return pad_id

   def stall_check(self):
      checked = self.tf("run", "stall-check")
      self.assertEqual(checked.returncode, 0, checked.stderr)
      return checked


class StallCheck(StallCase):
   def setUp(self):
      super().setUp()
      self.set_world({"tasks": [make_task(SLOW, SLOW_ID, props=[phase_prop("impl")])]})
      self.start_run(SLOW)

   def test_one_nudge_only(self):
      self.stall_check()
      self.assertEqual(self.calls_of("send"), [])

      self.age_stall(SLOW, "seen", 11)
      self.stall_check()
      self.stall_check()
      sends = self.calls_of("send")
      self.assertEqual(len(sends), 1)
      self.assertIn(SLOW_ID, sends[0])
      self.assertIn("nudged feat: slow", self.world()["pads"][self.pad])

   def test_nudge_is_signed(self):
      self.stall_check()
      self.age_stall(SLOW, "seen", 11)
      self.stall_check()
      body = [line for line in self.log_path.read_text().splitlines() if '"send"' in line][0]
      self.assertIn("[message from agent:claude task:main id:", json.loads(body)["stdin"])

   def test_blocked_after_second_expiry(self):
      self.stall_check()
      self.age_stall(SLOW, "seen", 11)
      self.stall_check()
      self.age_stall(SLOW, "nudged", 11)
      self.stall_check()
      blocks = [argv for argv in self.calls_of("prop") if argv[1:2] == ["blocked"]]
      self.assertEqual(len(blocks), 1)
      self.assertIn("silent past 10 min after nudge", blocks[0])
      self.assertIn(SLOW_ID, blocks[0])
      self.assertIn("blocked feat: slow: silent past 10 min after nudge", self.world()["pads"][self.pad])
      self.assertEqual(len(self.calls_of("send")), 1)

   def set_task(self, index, **fields):
      world = self.world()
      world["tasks"][index].update(fields)
      self.set_world(world)

   def stall_entry(self, name):
      header = json.loads(HEADER.search(self.world()["pads"][self.pad]).group(1))
      return (header.get("stall") or {}).get(name)

   def test_nudge_goes_to_the_impl_tab(self):
      self.stall_check()
      self.age_stall(SLOW, "seen", 11)
      self.stall_check()
      self.assertIn(["--tab", "impl"], [send[2:4] for send in self.calls_of("send")])

   def test_no_op_turn_after_nudge_still_ends_blocked(self):
      self.stall_check()
      self.age_stall(SLOW, "seen", 11)
      self.stall_check()
      self.set_task(0, work_state="working")
      self.stall_check()
      self.set_task(0, work_state="idle")
      self.stall_check()
      self.assertIsNotNone(self.stall_entry(SLOW)["nudged"])
      self.age_stall(SLOW, "nudged", 11)
      self.stall_check()
      blocks = [argv for argv in self.calls_of("prop") if argv[1:2] == ["blocked"]]
      self.assertEqual(len(blocks), 1)
      self.assertEqual(len(self.calls_of("send")), 1)

   def test_failed_block_is_not_logged(self):
      self.stall_check()
      self.age_stall(SLOW, "seen", 11)
      self.stall_check()
      self.age_stall(SLOW, "nudged", 11)
      world = self.world()
      world["exit"] = {"prop": 1}
      self.set_world(world)
      checked = self.tf("run", "stall-check")
      self.assertNotEqual(checked.returncode, 0)
      self.assertNotIn("blocked feat: slow", self.world()["pads"][self.pad])
      self.assertFalse(self.stall_entry(SLOW)["blocked"])

   def test_activity_resets_the_timer(self):
      self.stall_check()
      self.age_stall(SLOW, "seen", 11)
      world = self.world()
      world["tasks"][0]["props"] = [phase_prop("test")]
      self.set_world(world)
      self.stall_check()
      self.assertEqual(self.calls_of("send"), [])


class Resume(StallCase):
   def setUp(self):
      super().setUp()
      tasks = [
         make_task(SLOW, SLOW_ID, work_state="working", props=[phase_prop("impl")]),
         make_task(DONE, DONE_ID, props=[phase_prop("ready")]),
         make_task(STUCK, STUCK_ID, props=[phase_prop("impl"), {"key": "blocked", "values": ["no network"]}]),
      ]
      self.set_world({"tasks": tasks})
      self.start_run(SLOW, DONE, STUCK)

   def resume(self, ref="demo-slug"):
      resumed = self.tf("run", "resume", ref)
      self.assertEqual(resumed.returncode, 0, resumed.stderr)
      return resumed.stdout

   def line_for(self, output, name):
      return next(line for line in output.splitlines() if line.startswith(name))

   def test_three_task_resume(self):
      report_pad = self.add_pad(f"report: {DONE}")
      output = self.resume()
      self.assertEqual(len(output.strip().splitlines()), 3)
      self.assertIn("phase=impl next=wait", self.line_for(output, SLOW))
      self.assertIn("phase=ready next=review", self.line_for(output, DONE))
      self.assertIn(report_pad, self.line_for(output, DONE))
      self.assertIn("next=blocked: no network", self.line_for(output, STUCK))

   def test_resume_works_on_a_closed_run(self):
      (self.state / "current-run-tab-orch.json").unlink()
      output = self.resume()
      self.assertEqual(len(output.strip().splitlines()), 3)

   def test_resume_by_pad_id(self):
      output = self.resume(self.pad)
      self.assertIn(SLOW, output)

   def test_only_pads_newer_than_the_log_show(self):
      old_pad = self.add_pad(f"report: {DONE}")
      self.tf("log", f"report {DONE} report={old_pad}")
      new_pad = self.add_pad(f"report: {DONE} r2")
      done_line = self.line_for(self.resume(), DONE)
      self.assertIn(new_pad, done_line)
      self.assertNotIn(old_pad, done_line)

   def test_review_pad_means_land(self):
      self.add_pad(f"review: {DONE}")
      self.assertIn("next=land", self.line_for(self.resume(), DONE))

   def test_stalled_idle_task_means_nudge(self):
      world = self.world()
      world["tasks"][0]["work_state"] = "idle"
      self.set_world(world)
      self.stall_check()
      self.age_stall(SLOW, "seen", 11)
      self.assertIn("next=nudge", self.line_for(self.resume(), SLOW))


class StallSendFails(StallCase):
   def setUp(self):
      super().setUp()
      tasks = [
         make_task(STUCK, STUCK_ID, props=[phase_prop("impl")]),
         make_task(SLOW, SLOW_ID, props=[phase_prop("impl")]),
      ]
      self.set_world({"tasks": tasks})
      self.start_run(STUCK, SLOW)

   def test_entries_handled_before_a_failed_send_are_saved(self):
      self.stall_check()
      self.age_stall(STUCK, "seen", 11)
      self.stall_check()
      self.age_stall(STUCK, "nudged", 11)
      self.age_stall(SLOW, "seen", 11)
      world = self.world()
      world["exit"] = {"send": 1}
      self.set_world(world)
      checked = self.tf("run", "stall-check")
      self.assertNotEqual(checked.returncode, 0)
      header = json.loads(HEADER.search(self.world()["pads"][self.pad]).group(1))
      self.assertTrue(header["stall"][STUCK]["blocked"])
      self.assertIsNone(header["stall"][SLOW]["nudged"])
