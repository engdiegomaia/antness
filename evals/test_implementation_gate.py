"""Offline behavior evaluations for the implementation step gate."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "implementation_gate.py"
HARDWARE_GUARD = ROOT / "hooks" / "guard-destructive-hardware.sh"


class ImplementationGateEvals(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.temp.name) / "implementation.json"

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), "--state-file", str(self.state), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def payload(self, completed):
        return json.loads(completed.stdout)

    def start(self):
        return self.call("start", "--task", "test task", "--step", "one small change",
                         "--acceptance", "observable result")

    def test_happy_path_requires_evidence_at_each_gate(self):
        self.assertEqual(self.start().returncode, 0)
        implemented = self.call("advance", "--to", "implemented", "--evidence", "diff contains the change")
        self.assertEqual(implemented.returncode, 0)
        verified = self.call("advance", "--to", "verified", "--check", "python -m unittest", "--result", "passed")
        self.assertEqual(verified.returncode, 0)
        reviewed = self.call("advance", "--to", "reviewed", "--evidence", "diff reviewed; no findings")
        self.assertEqual(reviewed.returncode, 0)
        self.assertEqual(self.payload(reviewed)["step"]["stage"], "reviewed")

    def test_cannot_skip_implementation_or_verification(self):
        self.start()
        skipped = self.call("advance", "--to", "verified", "--check", "make test", "--result", "passed")
        self.assertEqual(skipped.returncode, 2)
        self.assertIn("Invalid transition", self.payload(skipped)["summary"])

    def test_missing_evidence_is_rejected(self):
        self.start()
        missing = self.call("advance", "--to", "implemented")
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(self.payload(missing)["status"], "error")

    def test_failed_check_blocks_progress_and_is_recorded(self):
        self.start()
        self.call("advance", "--to", "implemented", "--evidence", "change made")
        failed = self.call("advance", "--to", "verified", "--check", "make test", "--result", "failed")
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(self.payload(failed)["status"], "blocked")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(state["steps"][-1]["stage"], "implemented")
        self.assertEqual(state["steps"][-1]["checks"][-1]["result"], "failed")

    def test_check_command_is_evidence_only_and_is_never_executed(self):
        self.start()
        self.call("advance", "--to", "implemented", "--evidence", "change made")
        marker = pathlib.Path(self.temp.name) / "must-not-exist"
        command = f"touch {marker}"
        recorded = self.call("advance", "--to", "verified", "--check", command, "--result", "passed")
        self.assertEqual(recorded.returncode, 0)
        self.assertFalse(marker.exists(), "the gate must record commands, never execute them")

    def test_next_step_requires_reviewed_current_step(self):
        self.start()
        next_step = self.call("start", "--task", "test task", "--step", "next", "--acceptance", "done")
        self.assertEqual(next_step.returncode, 2)

    def test_step_history_is_preserved_across_baby_steps(self):
        self.start()
        self.call("advance", "--to", "implemented", "--evidence", "change one")
        self.call("advance", "--to", "verified", "--check", "check one", "--result", "passed")
        self.call("advance", "--to", "reviewed", "--evidence", "review one")
        second = self.call("start", "--task", "test task", "--step", "next", "--acceptance", "done")
        self.assertEqual(second.returncode, 0)
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(len(state["steps"]), 2)
        self.assertEqual(state["steps"][0]["stage"], "reviewed")
        self.assertEqual(state["steps"][1]["stage"], "ready")


class HardwareGuardEvals(unittest.TestCase):
    def evaluate(self, command):
        return subprocess.run(
            [str(HARDWARE_GUARD), command],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_irreversible_flash_fuse_and_block_device_writes_are_blocked(self):
        commands = (
            "espefuse.py burn_efuse SECURE_BOOT_EN",
            "dd if=core-image.wic of=/dev/mmcblk0",
            "nrfjprog --eraseall",
            "fw_setenv bootcmd 'run mmcboot'",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.evaluate(command).returncode, 2)

    def test_build_and_read_only_commands_remain_allowed(self):
        commands = (
            "west build -b nucleo_h743zi app",
            "bitbake core-image-minimal",
            "git status",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.evaluate(command).returncode, 0)


if __name__ == "__main__":
    unittest.main()
