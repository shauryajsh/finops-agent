"""Sanity checks for rule-based diagnosis logic.

Confirms known-wasteful patterns get flagged and known-fine queries don't,
before the LLM baseline comparison in Phase 4.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))
from rule_based_agent import diagnose

CASES = [
    ("SELECT * FROM `project.dataset.table`", True, "SELECT * with no filter"),
    ("SELECT a, b FROM `project.dataset.table` WHERE d = CURRENT_DATE()", False, "filtered, few columns"),
    ("SELECT * FROM `project.dataset.table` WHERE status = 'Closed'", True, "SELECT * even with a filter"),
    ("SELECT status FROM `project.dataset.table` LIMIT 100", False, "single column, no issues"),
]


def run():
    passed = 0
    for sql, should_flag, description in CASES:
        reasons = diagnose(sql)
        flagged = reasons[0] != "No issue matched by current rules."
        ok = flagged == should_flag
        passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {description}")

    print(f"\n{passed}/{len(CASES)} passed")


if __name__ == "__main__":
    run()