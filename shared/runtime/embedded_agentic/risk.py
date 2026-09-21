"""Risk gating for operations that touch hardware.

Two independent things decide whether an action runs:

  risk level      declared by the tool, per action, and never guessed
  operation_mode  chosen by the operator for this machine, in local.json

                     low        medium        high      irreversible
  mode 1 (bench)     run        run           run+warn  confirm
  mode 2 (default)   run        run+warn      confirm   confirm
  mode 3 (careful)   run+warn   confirm       confirm   confirm

Mode 1 is for a development board on your desk with a known recovery path.
Mode 3 is for a customer or production unit. The default is 2.

"irreversible" is never auto-approved at any mode, because there is no mode in
which burning a fuse should happen without a human saying so. This mirrors
shared/rules/10-hardware-safety.md, which applies whether or not this module
is in the call path.
"""
from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

RISK_LEVELS = ("low", "medium", "high", "irreversible")

_ORDER = {level: index for index, level in enumerate(RISK_LEVELS)}

# Minimum risk level that requires confirmation, per operation_mode.
_CONFIRM_AT = {1: "irreversible", 2: "high", 3: "medium"}
# A high-risk action is always recorded in the result, even on a bench machine.
# Silence costs nothing to produce and everything to reconstruct afterwards.
_WARN_AT = {1: "high", 2: "medium", 3: "low"}


class ConfirmationRequired(Exception):
    def __init__(self, action: str, risk: str, token: str, reasons: List[str], recovery: str) -> None:
        super().__init__("confirmation required for {}".format(action))
        self.action = action
        self.risk = risk
        self.token = token
        self.reasons = reasons
        self.recovery = recovery

    def details(self) -> Dict[str, object]:
        return {
            "action": self.action,
            "risk": self.risk,
            "confirm_token": self.token,
            "what_is_at_stake": self.reasons,
            "recovery_path": self.recovery,
            "how_to_proceed": (
                "Show this to the user, including the target device and the recovery path. "
                "If they approve, re-run the same command with --confirm {}".format(self.token)
            ),
        }


def confirm_token(action: str, target: str) -> str:
    raw = "{}|{}".format(action, target).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:8]


def check_operation(
    action: str,
    risk: str,
    mode: int,
    target: str,
    reasons: Optional[List[str]] = None,
    recovery: str = "unknown — state the recovery path before proceeding",
    confirmed: Optional[str] = None,
) -> List[str]:
    """Gate an action. Returns warnings to attach; raises ConfirmationRequired to stop.

    `target` identifies the specific device (probe serial, port, board id). It is
    part of the token so an approval for one board does not approve another.
    """
    if risk not in _ORDER:
        raise ValueError("unknown risk level {!r}; use one of {}".format(risk, RISK_LEVELS))

    warnings: List[str] = []
    level = _ORDER[risk]

    if level >= _ORDER[_WARN_AT.get(mode, "medium")]:
        warnings.append(
            "{} is a {}-risk operation on {} (operation_mode={})".format(action, risk, target, mode)
        )

    if level >= _ORDER[_CONFIRM_AT.get(mode, "high")]:
        token = confirm_token(action, target)
        if confirmed == token:
            warnings.append("confirmed by the user for {}".format(target))
            return warnings
        if confirmed:
            raise ConfirmationRequired(
                action, risk, token,
                (reasons or []) + [
                    "the supplied confirmation token does not match this target; "
                    "an approval for one device does not carry to another"
                ],
                recovery,
            )
        raise ConfirmationRequired(action, risk, token, reasons or [], recovery)

    return warnings
