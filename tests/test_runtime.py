#!/usr/bin/env python3
"""Tests for shared/runtime/antness_runtime.

Standard library only, no pytest — this has to run on a build host that has
nothing but python3 installed.

    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "shared" / "runtime"))

from antness_runtime import config, result, risk  # noqa: E402


def workspace_with(project=None, local=None, state=None):
    """Create a throwaway workspace with the given config layers."""
    root = pathlib.Path(tempfile.mkdtemp())
    cfg = root / config.CONFIG_DIR
    cfg.mkdir()
    for name, data in ((config.PROJECT_FILE, project),
                       (config.LOCAL_FILE, local),
                       (config.STATE_FILE, state)):
        if data is not None:
            (cfg / name).write_text(json.dumps(data), encoding="utf-8")
    return root


class TestPrecedence(unittest.TestCase):
    def test_cli_beats_every_stored_layer(self):
        # Arrange
        root = workspace_with(project={"build": {"board": "from-project"}},
                              local={"build": {"board": "from-local"}})
        r = config.Resolver("build", workspace=root)

        # Act
        value = r.resolve("board", cli="from-cli")

        # Assert
        self.assertEqual(value, "from-cli")
        self.assertEqual(r.provenance["board"], "cli")

    def test_project_beats_local_and_state(self):
        root = workspace_with(project={"build": {"board": "nucleo"}},
                              local={"build": {"board": "bench-board"}},
                              state={"build": {"board": "stale"}})
        r = config.Resolver("build", workspace=root)
        self.assertEqual(r.resolve("board"), "nucleo")
        self.assertEqual(r.provenance["board"], "project")

    def test_state_is_the_last_resort_before_default(self):
        root = workspace_with(state={"build": {"backend": "make"}})
        r = config.Resolver("build", workspace=root)
        self.assertEqual(r.resolve("backend", default="cmake"), "make")
        self.assertEqual(r.provenance["backend"], "state")

    def test_default_applies_when_nothing_is_stored(self):
        root = workspace_with()
        r = config.Resolver("probe", workspace=root)
        self.assertEqual(r.resolve("interface", default="SWD"), "SWD")
        self.assertEqual(r.provenance["interface"], "default")

    def test_missing_required_parameter_names_the_file_to_edit(self):
        root = workspace_with()
        r = config.Resolver("probe", workspace=root)
        with self.assertRaises(config.ConfigError) as cm:
            r.resolve("device", required=True, describe="the chip name the probe targets")
        message = str(cm.exception)
        self.assertIn("the chip name the probe targets", message)
        self.assertIn(config.PROJECT_FILE, message)


class TestScopeDiscipline(unittest.TestCase):
    """A project fact hidden in local.json breaks a colleague's clone."""

    def test_resolve_project_ignores_local(self):
        root = workspace_with(local={"build": {"board": "only-on-my-desk"}})
        r = config.Resolver("build", workspace=root)
        self.assertIsNone(r.resolve_project("board"))

    def test_resolve_tool_ignores_project(self):
        root = workspace_with(project={"probe": {"openocd_exe": "/opt/only-on-my-desk/openocd"}})
        r = config.Resolver("probe", workspace=root)
        self.assertIsNone(r.resolve_tool("openocd_exe", candidates=[]))

    def test_resolve_tool_takes_the_local_path(self):
        root = workspace_with(local={"probe": {"openocd_exe": "/opt/bench/openocd"}})
        r = config.Resolver("probe", workspace=root)
        self.assertEqual(r.resolve_tool("openocd_exe"), "/opt/bench/openocd")
        self.assertEqual(r.provenance["openocd_exe"], "local")


class TestLint(unittest.TestCase):
    def test_absolute_path_in_project_json_is_reported(self):
        root = workspace_with(project={"probe": {"jlink_exe": "/opt/SEGGER/JLinkExe"}})
        findings = config.lint_layers(root)
        self.assertTrue(any("jlink_exe" in f for f in findings), findings)

    def test_board_in_local_json_is_reported(self):
        root = workspace_with(local={"build": {"board": "nucleo_h743zi"}})
        findings = config.lint_layers(root)
        self.assertTrue(any("board" in f for f in findings), findings)

    def test_recovery_path_in_project_json_is_not_a_finding(self):
        # `_path` looks machine-local but describes the hardware — regression guard.
        root = workspace_with(project={"hardware": {"recovery_path": "BOOT0 jumper, then DFU"}})
        self.assertEqual(config.lint_layers(root), [])

    def test_clean_layers_produce_no_findings(self):
        root = workspace_with(project={"probe": {"device": "STM32H743ZI", "interface": "SWD"}},
                              local={"probe": {"probe_serial": "000123456789"}})
        self.assertEqual(config.lint_layers(root), [])


class TestRiskGating(unittest.TestCase):
    TARGET = "openocd:STM32H743ZI:000123456789"

    def test_low_risk_passes_unconditionally(self):
        self.assertEqual(risk.check_operation("read-mem", "low", 2, self.TARGET), [])

    def test_high_risk_requires_confirmation_in_default_mode(self):
        with self.assertRaises(risk.ConfirmationRequired):
            risk.check_operation("flash", "high", 2, self.TARGET)

    def test_correct_token_unblocks_the_operation(self):
        token = risk.confirm_token("flash", self.TARGET)
        warnings = risk.check_operation("flash", "high", 2, self.TARGET, confirmed=token)
        self.assertTrue(any("confirmed" in w for w in warnings), warnings)

    def test_token_from_another_board_is_rejected(self):
        other = risk.confirm_token("flash", "openocd:STM32H743ZI:999999999999")
        with self.assertRaises(risk.ConfirmationRequired) as cm:
            risk.check_operation("flash", "high", 2, self.TARGET, confirmed=other)
        reasons = cm.exception.details()["what_is_at_stake"]
        self.assertTrue(any("does not carry to another" in r for r in reasons), reasons)

    def test_bench_mode_warns_but_does_not_block_a_high_risk_flash(self):
        warnings = risk.check_operation("flash", "high", 1, self.TARGET)
        self.assertTrue(warnings, "bench mode must still warn on a high-risk operation")

    def test_production_mode_blocks_a_medium_risk_operation(self):
        with self.assertRaises(risk.ConfirmationRequired):
            risk.check_operation("clean", "medium", 3, self.TARGET)

    def test_irreversible_is_gated_even_on_the_bench(self):
        with self.assertRaises(risk.ConfirmationRequired):
            risk.check_operation("efuse-burn", "irreversible", 1, self.TARGET)

    def test_confirmation_details_tell_the_operator_what_to_do(self):
        try:
            risk.check_operation("erase", "high", 2, self.TARGET,
                                 recovery="reflash via DFU with BOOT0 held")
        except risk.ConfirmationRequired as exc:
            details = exc.details()
            self.assertEqual(details["confirm_token"], risk.confirm_token("erase", self.TARGET))
            self.assertIn("DFU", details["recovery_path"])
            self.assertIn(details["confirm_token"], details["how_to_proceed"])
        else:
            self.fail("erase at mode 2 must require confirmation")

    def test_unknown_risk_level_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            risk.check_operation("flash", "catastrophic", 2, self.TARGET)


class TestResult(unittest.TestCase):
    @staticmethod
    def exit_code(r):
        # emit() prints; swallow it so the test output stays readable.
        with contextlib.redirect_stdout(io.StringIO()):
            return result.emit(r, as_json=False)

    def test_exit_codes_distinguish_the_failure_kinds(self):
        self.assertEqual(self.exit_code(result.ok("build", "built")), 0)
        self.assertEqual(self.exit_code(result.fail("build", "no toolchain")), 1)
        self.assertEqual(self.exit_code(result.Result(
            status="confirmation_required", action="flash", summary="needs approval")), 3)
        self.assertEqual(self.exit_code(result.Result(
            status="blocked", action="erase", summary="not allowed in production")), 4)

    def test_serialised_result_is_json(self):
        r = result.ok("build", "built", details={"artifacts": ["app.elf"]}, validated_on="host")
        payload = json.loads(json.dumps(r.to_dict()))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["validated_on"], "host")


if __name__ == "__main__":
    unittest.main()
