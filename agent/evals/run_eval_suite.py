"""Runs the full generated eval suite through rule-based and LLM diagnosis.

Reports pass/fail per category, not just one overall total, since category
breakdown is what shows where each system's real strengths and gaps are.
"""

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent / "src"))
from rule_based_agent import diagnose as rule_based_diagnose
from llm_agent import diagnose_and_fix

from generate_eval_cases import (
    generate_select_star_cases,
    generate_missing_partition_cases,
    generate_wildcard_table_cases,
    generate_count_distinct_cases,
    generate_udf_cases,
    generate_fan_out_join_cases,
    generate_known_fine_cases,
)


def get_all_cases() -> list[dict]:
    """Returns every generated eval case, tagged with its category."""
    categories = {
        "select_star": generate_select_star_cases(),
        "partition": generate_missing_partition_cases(),
        "wildcard": generate_wildcard_table_cases(),
        "distinct": generate_count_distinct_cases(),
        "udf": generate_udf_cases(),
        "join": generate_fan_out_join_cases(),
        "known_fine": generate_known_fine_cases(),
    }

    cases = []
    for category, category_cases in categories.items():
        for case in category_cases:
            case["category"] = category
            cases.append(case)

    return cases


def score(diagnosis_text: str, expected_concepts: list[str]) -> bool:
    """Checks whether every expected concept appears in the diagnosis.

    An empty expected_concepts list means the case should NOT be flagged.
    """
    diagnosis_text = diagnosis_text.lower()

    if not expected_concepts:
        return "no issue" in diagnosis_text

    for concept in expected_concepts:
        if concept.lower() not in diagnosis_text:
            return False

    return True


def run():
    cases = get_all_cases()
    print(f"Running {len(cases)} cases through both systems\n")

    results_by_category = {}

    for i, case in enumerate(cases):
        category = case["category"]
        query = case["query"]
        expected_concepts = case["expected_concepts"]

        rule_based_reasons = rule_based_diagnose(query)
        rule_based_text = " ".join(rule_based_reasons)
        rule_based_ok = score(rule_based_text, expected_concepts)

        llm_result = diagnose_and_fix(query)
        llm_text = llm_result["explanation"]
        llm_ok = score(llm_text, expected_concepts)

        if category not in results_by_category:
            results_by_category[category] = {"rule_based_passed": 0, "llm_passed": 0, "total": 0}

        results_by_category[category]["total"] = results_by_category[category]["total"] + 1

        if rule_based_ok:
            results_by_category[category]["rule_based_passed"] = results_by_category[category]["rule_based_passed"] + 1

        if llm_ok:
            results_by_category[category]["llm_passed"] = results_by_category[category]["llm_passed"] + 1

        print(f"[{i + 1}/{len(cases)}] {case['description']}")

        if rule_based_ok:
            print("  Rule-based: PASS")
        else:
            print("  Rule-based: FAIL")

        if llm_ok:
            print("  LLM:        PASS")
        else:
            print(f"  LLM:        FAIL - {llm_text[:100]}")

        # Groq's free tier caps at 30 requests/minute - pace calls so a
        # long run does not hit rate limits partway through.
        time.sleep(2)

    print("\n" + "=" * 50)
    print("RESULTS BY CATEGORY")
    print("=" * 50)

    total_rule_based_passed = 0
    total_llm_passed = 0
    total_cases = 0

    for category, results in results_by_category.items():
        rb = results["rule_based_passed"]
        llm = results["llm_passed"]
        total = results["total"]
        print(f"{category}: rule-based {rb}/{total}, LLM {llm}/{total}")

        total_rule_based_passed = total_rule_based_passed + rb
        total_llm_passed = total_llm_passed + llm
        total_cases = total_cases + total

    print("=" * 50)
    print(f"OVERALL: rule-based {total_rule_based_passed}/{total_cases}, LLM {total_llm_passed}/{total_cases}")


if __name__ == "__main__":
    run()