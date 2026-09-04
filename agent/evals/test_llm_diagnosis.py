"""Compares rule-based vs LLM diagnosis against known root causes.

Each case defines concepts a correct diagnosis should mention. Scores
both systems against the same cases for a real comparison number.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))
from rule_based_agent import diagnose as rule_based_diagnose
from llm_agent import diagnose as llm_diagnose

AUSTIN = "`bigquery-public-data.austin_311.311_service_requests`"
SHAKESPEARE = "`bigquery-public-data.samples.shakespeare`"

CASES = [
    {
        "query": f"SELECT * FROM {AUSTIN}",
        "expected_concepts": ["select *"],
        "description": "SELECT * with no filter",
    },
    {
        "query": f"SELECT * FROM {AUSTIN} WHERE status = 'Closed'",
        "expected_concepts": ["select *"],
        "description": "SELECT * even with a filter",
    },
    {
        "query": f"SELECT * FROM {SHAKESPEARE}",
        "expected_concepts": ["select *"],
        "description": "SELECT * on a different table",
    },
    {
        "query": f"SELECT word, word_count, corpus, corpus_date FROM {SHAKESPEARE}",
        "expected_concepts": ["all", "column"],
        "description": "Every column named explicitly, same cost as SELECT * but no literal SELECT * text",
    },
]


def score(diagnosis: str, expected_concepts: list[str]) -> bool:
    """Checks whether every expected concept appears somewhere in the diagnosis."""
    diagnosis = diagnosis.lower()

    for concept in expected_concepts:
        if concept.lower() not in diagnosis:
            return False

    return True


def run():
    rule_based_passed = 0
    llm_passed = 0

    for case in CASES:
        query = case["query"]
        expected_concepts = case["expected_concepts"]

        rule_based_reasons = rule_based_diagnose(query)
        rule_based_text = " ".join(rule_based_reasons)
        rule_based_result = score(rule_based_text, expected_concepts)

        llm_text = llm_diagnose(query)
        llm_result = score(llm_text, expected_concepts)

        if rule_based_result:
            rule_based_passed = rule_based_passed + 1

        if llm_result:
            llm_passed = llm_passed + 1

        print(case["description"])

        if rule_based_result:
            print("  Rule-based: PASS")
        else:
            print("  Rule-based: FAIL")

        if llm_result:
            print("  LLM:        PASS")
        else:
            print("  LLM:        FAIL")

        print()

    total = len(CASES)
    print(f"Rule-based: {rule_based_passed}/{total} passed")
    print(f"LLM:        {llm_passed}/{total} passed")


if __name__ == "__main__":
    run()