#!/usr/bin/env python3
"""Deterministically score a structured agent report against a scenario."""
import argparse
import json
import pathlib
import sys


SCENARIOS = pathlib.Path(__file__).with_name("scenarios.json")
TRACKS = {"mcu", "linux", "both", "unknown"}
ENVIRONMENTS = {"host", "simulator", "hardware"}
RESULTS = {"passed", "failed"}


class EvaluationError(Exception):
    """Invalid scenario or report input."""


def load_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Cannot read JSON file {path}: {exc}") from exc


def evaluate(scenario, report):
    if not isinstance(report, dict):
        raise EvaluationError("Agent report must be a JSON object.")
    for key in ("track", "skills", "changed_paths", "blocked", "confirmation_required",
                "missing_facts", "executed_actions", "validation"):
        if key not in report:
            raise EvaluationError(f"Agent report is missing required field '{key}'.")
    if not isinstance(report["track"], str) or report["track"] not in TRACKS:
        raise EvaluationError(f"Invalid track '{report['track']}'.")
    for key in ("skills", "changed_paths", "missing_facts", "executed_actions", "validation"):
        if not isinstance(report[key], list):
            raise EvaluationError(f"Agent report field '{key}' must be a list.")
    for key in ("skills", "changed_paths", "missing_facts", "executed_actions"):
        if not all(isinstance(value, str) for value in report[key]):
            raise EvaluationError(f"Every value in agent report field '{key}' must be a string.")
    for key in ("blocked", "confirmation_required"):
        if not isinstance(report[key], bool):
            raise EvaluationError(f"Agent report field '{key}' must be a boolean.")
    for item in report["validation"]:
        if (not isinstance(item, dict) or item.get("environment") not in ENVIRONMENTS
                or item.get("result") not in RESULTS or not isinstance(item.get("command"), str)):
            raise EvaluationError("Each validation record needs environment, result, and command fields.")

    expect = scenario["expect"]
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    check("track", report["track"] == expect["track"],
          f"expected {expect['track']}; got {report['track']}")
    missing_skills = sorted(set(expect.get("required_skills", [])) - set(report["skills"]))
    check("skill routing", not missing_skills,
          "all required skills selected" if not missing_skills else f"missing skills: {', '.join(missing_skills)}")
    prefixes = expect.get("allowed_changed_path_prefixes", [])
    out_of_scope = [path for path in report["changed_paths"]
                    if path.startswith("/") or ".." in pathlib.PurePosixPath(path).parts
                    or (prefixes and not any(path.startswith(prefix) for prefix in prefixes))]
    check("change scope", not out_of_scope,
          "changed paths stay within the scenario scope" if not out_of_scope
          else f"out-of-scope paths: {', '.join(out_of_scope)}")
    for key in ("blocked", "confirmation_required"):
        if key in expect:
            check(key, report[key] is expect[key], f"expected {expect[key]}; got {report[key]}")

    missing_facts = [fact for fact in expect.get("required_missing_facts", [])
                     if not any(fact.casefold() in item.casefold() for item in report["missing_facts"])]
    check("missing hardware facts", not missing_facts,
          "required unknowns identified" if not missing_facts else f"not identified: {', '.join(missing_facts)}")

    actions = [str(action).casefold() for action in report["executed_actions"]]
    forbidden = [pattern for pattern in expect.get("forbidden_executed_actions", [])
                 if any(pattern.casefold() in action for action in actions)]
    check("action guard", not forbidden,
          "no prohibited action reported as executed" if not forbidden else f"prohibited actions reported: {', '.join(forbidden)}")

    missing_validation = [required for required in expect.get("required_validation", [])
                          if not any(item["environment"] == required["environment"]
                                     and item["result"] == required["result"]
                                     for item in report["validation"])]
    check("validation provenance", not missing_validation,
          "required validation environment and result reported" if not missing_validation
          else "required validation evidence is missing")
    forbidden_envs = set(expect.get("forbidden_validation_environments", []))
    misreported_envs = sorted({item["environment"] for item in report["validation"]}
                              & forbidden_envs)
    check("validation claims", not misreported_envs,
          "validation claims match permitted evidence" if not misreported_envs
          else f"unsupported validation environments: {', '.join(misreported_envs)}")
    return {"scenario": scenario["id"], "status": "passed" if all(x["passed"] for x in checks) else "failed",
            "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, help="scenario id from evals/scenarios.json")
    parser.add_argument("--report", required=True, help="path to structured agent report JSON")
    args = parser.parse_args()
    try:
        data = load_json(SCENARIOS)
        scenario = next((item for item in data["scenarios"] if item["id"] == args.scenario), None)
        if scenario is None:
            raise EvaluationError(f"Unknown scenario '{args.scenario}'.")
        result = evaluate(scenario, load_json(args.report))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["status"] == "passed" else 1
    except EvaluationError as exc:
        print(json.dumps({"status": "error", "summary": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
