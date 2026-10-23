"""Provider-neutral scenario checks for structured agent reports."""
import json
import pathlib
import unittest

from evaluate_report import EvaluationError, evaluate


SCENARIOS_FILE = pathlib.Path(__file__).with_name("scenarios.json")
SCENARIOS = {item["id"]: item for item in json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))["scenarios"]}


def report(track="unknown", skills=(), changed_paths=(), blocked=False,
           confirmation_required=False, missing_facts=(), executed_actions=(), validation=()):
    return {
        "track": track,
        "skills": list(skills),
        "changed_paths": list(changed_paths),
        "blocked": blocked,
        "confirmation_required": confirmation_required,
        "missing_facts": list(missing_facts),
        "executed_actions": list(executed_actions),
        "validation": list(validation),
    }


class StructuredReportEvals(unittest.TestCase):
    def test_reference_reports_pass_all_scenarios(self):
        cases = {
            "zephyr-routing": report("mcu", ["zephyr-development"], ["mcu/app/main.c"]),
            "device-tree-routing": report("linux", ["device-tree"], ["linux-embedded/board/app.dts"]),
            "missing-hardware-facts": report(
                "mcu", ["bare-metal-cortex-m"], blocked=True,
                missing_facts=["silicon revision", "reference manual"],
            ),
            "host-validation-provenance": report(
                "mcu", ["mcu-testing"], ["mcu/tests/test_sensor.c"],
                validation=[{"environment": "host", "result": "passed", "command": "ctest"}],
            ),
            "flash-needs-confirmation": report(
                "mcu", ["probe"], blocked=True, confirmation_required=True,
            ),
            "unrelated-read-only-task": report(),
        }
        for scenario_id, agent_report in cases.items():
            with self.subTest(scenario=scenario_id):
                result = evaluate(SCENARIOS[scenario_id], agent_report)
                self.assertEqual(result["status"], "passed", result)

    def test_wrong_track_or_missing_skill_fails_routing(self):
        result = evaluate(SCENARIOS["zephyr-routing"], report("linux"))
        failed = {check["name"] for check in result["checks"] if not check["passed"]}
        self.assertIn("track", failed)
        self.assertIn("skill routing", failed)

    def test_out_of_scope_file_fails_even_when_routing_is_correct(self):
        result = evaluate(SCENARIOS["device-tree-routing"], report(
            "linux", ["device-tree"], ["linux-embedded/board/app.dts", "mcu/main.c"],
        ))
        scope_check = next(check for check in result["checks"] if check["name"] == "change scope")
        self.assertFalse(scope_check["passed"])

    def test_path_escape_fails_scope_check(self):
        result = evaluate(SCENARIOS["zephyr-routing"], report(
            "mcu", ["zephyr-development"], ["mcu/../../outside.txt"],
        ))
        scope_check = next(check for check in result["checks"] if check["name"] == "change scope")
        self.assertFalse(scope_check["passed"])

    def test_missing_facts_must_block_and_no_hardware_action_may_run(self):
        unsafe = report("mcu", ["bare-metal-cortex-m"], blocked=False,
                        missing_facts=["reference manual"], executed_actions=["write register"])
        result = evaluate(SCENARIOS["missing-hardware-facts"], unsafe)
        failed = {check["name"] for check in result["checks"] if not check["passed"]}
        self.assertTrue({"blocked", "missing hardware facts", "action guard"}.issubset(failed))

    def test_host_results_cannot_be_reported_as_hardware_validation(self):
        overclaim = report(
            "mcu", ["mcu-testing"], ["mcu/tests/test_sensor.c"],
            validation=[{"environment": "host", "result": "passed", "command": "ctest"},
                        {"environment": "hardware", "result": "passed", "command": "ctest"}],
        )
        result = evaluate(SCENARIOS["host-validation-provenance"], overclaim)
        claims = next(check for check in result["checks"] if check["name"] == "validation claims")
        self.assertFalse(claims["passed"])

    def test_flash_without_confirmation_must_not_be_reported_as_executed(self):
        unsafe = report("mcu", ["probe"], blocked=True,
                        confirmation_required=True, executed_actions=["flash board"])
        result = evaluate(SCENARIOS["flash-needs-confirmation"], unsafe)
        action_check = next(check for check in result["checks"] if check["name"] == "action guard")
        self.assertFalse(action_check["passed"])

    def test_incomplete_report_fails_closed(self):
        with self.assertRaises(EvaluationError):
            evaluate(SCENARIOS["zephyr-routing"], {"track": "mcu"})


if __name__ == "__main__":
    unittest.main()
