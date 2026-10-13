import re

from tf_lib.core import TfError

STATUSES = ("pass", "fail", "blocked")
FIELDS = ("status", "checks", "changed", "risks", "next")
FIELD_LINE = re.compile(r"^(status|checks|changed|risks|next|failure):\s*(.*)$", re.M)

TEMPLATE = """# report: {task}

status: pass|fail|blocked
checks: <name>=<numeric exit code>, ... (numbers only, for example unit=0, build=0; phrase absence checks so success exits 0)
changed: <files changed count>
risks: <one line, or none>
next: <one line>
failure: <reasoning|environment|none>
"""


def parse_report(text):
   found = {key: value.strip() for key, value in FIELD_LINE.findall(text)}
   missing = [field for field in FIELDS if field not in found]

   if missing:
      raise TfError(f"report is missing fields: {', '.join(missing)}")

   if found["status"] not in STATUSES:
      raise TfError(f"report status '{found['status']}' is not one of: {' '.join(STATUSES)}")

   checks = {}

   for item in filter(None, (part.strip() for part in found["checks"].split(","))):
      name, _, exit_code = item.partition("=")
      checks[name.strip()] = exit_code.strip()

   all_checks_zero = all(code == "0" for code in checks.values())
   claims_pass = found["status"] == "pass"

   if claims_pass and not all_checks_zero:
      raise TfError("report says pass but a check exited non-zero")

   found["checks"] = checks
   found.setdefault("failure", "none")
   return found
