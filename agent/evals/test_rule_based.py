"""Sanity checks for rule-based diagnosis logic.

Confirms known-wasteful patterns get flagged and known-fine queries don't.
"""

import sys
from pathlib import Path

# evals sits next to src, not inside it - add src to the path manually.
sys.path.append(str(Path(__file__).parent.parent / "src"))
from rule_based_agent import diagnose

CASES = [
    ("SELECT * FROM `project.dataset.table`", True, "SELECT * with no filter"),
    ("SELECT a, b FROM `project.dataset.table` WHERE d = CURRENT_DATE()", False, "filtered, few columns"),
    ("SELECT * FROM `project.dataset.table` WHERE status = 'Closed'", True, "SELECT * even with a filter"),
    ("SELECT status FROM `project.dataset.table` LIMIT 100", False, "single column, no issues"),
    ("SELECT event_name FROM `project.dataset.events_*`", True, "wildcard table scan"),
    ("SELECT COUNT(DISTINCT user_id) FROM `project.dataset.table`", True, "COUNT DISTINCT on large column"),
    ("SELECT a, b FROM `project.dataset.table` ORDER BY a", True, "ORDER BY with no LIMIT"),
    ("SELECT a, b FROM `project.dataset.table` ORDER BY a LIMIT 50", False, "ORDER BY with LIMIT should not flag"),
]


def run():
    passed = 0

    for sql, should_flag, description in CASES:
        reasons = diagnose(sql)
        flagged = reasons[0] != "No issue matched by current rules."
        ok = flagged == should_flag

        if ok:
            passed = passed + 1

        if ok:
            print(f"[PASS] {description}")
        else:
            print(f"[FAIL] {description}")

    print(f"\n{passed}/{len(CASES)} passed")


if __name__ == "__main__":
    run()