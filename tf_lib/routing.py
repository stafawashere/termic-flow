import json

from tf_lib.core import TfError
from tf_lib.profile import PLUGIN_ROOT, read_json, user_config_dir

MODEL_IDS = {
   "haiku": "claude-haiku-5-5",
   "sonnet": "claude-sonnet-5-5",
   "opus": "claude-opus-5-5",
   "fable": "claude-fable-5-1",
}


def load_routing(profile):
   routing = read_json(PLUGIN_ROOT / "config" / "routing.default.json")
   user_file = user_config_dir() / "routing.json"
   layers = []

   if user_file.is_file():
      layers.append(read_json(user_file))

   if profile.get("routing"):
      layers.append(profile["routing"])

   for layer in layers:
      prepended_rules = layer.get("rules", [])
      routing = {**routing, **{k: v for k, v in layer.items() if k != "rules"}}
      routing["rules"] = prepended_rules + routing["rules"]

   for rule in routing["rules"]:
      if rule["model"] not in MODEL_IDS:
         raise TfError(f"routing rule '{rule.get('id')}' names unknown model '{rule['model']}'")

   return routing


def rule_matches(rule, role, kind, risk, flags):
   checks = (
      ("roles", role),
      ("kinds", kind),
      ("risk", risk),
   )

   for key, value in checks:
      if key in rule and value not in rule[key]:
         return False

   wanted_flags = set(rule.get("flags", []))
   return wanted_flags.issubset(flags)


def escalate(routing, model, steps):
   ladder = [name for name in routing["ladder"] if name != "fable" or routing.get("allow_fable")]
   position = ladder.index(model) if model in ladder else len(ladder) - 1
   return ladder[min(position + steps, len(ladder) - 1)]


def route(routing, role, kind=None, risk=None, flags=(), failed_attempts=0, failure="none"):
   """failed_attempts counts reasoning failures only; environment failures never escalate."""
   flag_set = set(flags)

   for rule in routing["rules"]:
      if rule_matches(rule, role, kind, risk, flag_set):
         base = rule["model"]
         rule_id = rule.get("id", "unnamed")
         break
   else:
      raise TfError("no routing rule matched and there is no catch-all")

   is_reasoning_failure = failure == "reasoning"
   steps = max(failed_attempts - 1, 0) if is_reasoning_failure else 0
   model = escalate(routing, base, steps)
   reason = rule_id if steps == 0 else f"{rule_id}+escalated{steps}"
   return {"model": model, "model_id": MODEL_IDS[model], "rule": reason}


def explain(routing):
   return json.dumps(routing, indent=2)
