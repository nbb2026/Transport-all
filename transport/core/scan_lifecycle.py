"""Shared scan shutdown coordination and zero-output result reporting.

This module orchestrates callbacks and reports their results; it does not
issue hardware commands or define instrument-specific zeroing policies.
"""

from __future__ import annotations

import threading

class ScanCloseHandoff:
    """The program closing during a scan (review, 2026-10-18): the page's
    instrument clean-up (disconnect) must come after the scan's worker has
    zeroed its sources (read back) and closed its run log, or that zero
    finds them "not connected" and the log says so.  SHV queues its clean-up
    on its one worker; a page whose close cannot queue behind the scan
    (several workers, or queued jobs to cancel) uses this: the worker calls
    begin() when the scan starts and end() as its very last step; the close
    calls defer(cleanup), which leaves cleanup for end() while a scan is
    active, or returns False, and the close then runs it itself."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = False
        self.cleanup = None

    def begin(self) -> None:
        with self.lock:
            self.active = True

    def defer(self, cleanup) -> bool:
        with self.lock:
            if not self.active:
                return False
            self.cleanup = cleanup
            return True

    def end(self) -> None:
        with self.lock:
            self.active = False
            cleanup, self.cleanup = self.cleanup, None
        if cleanup is not None:
            cleanup()


ZERO_SENT_NOT_READ_BACK = "0 A sent, not read back"
# The states of zero_scan_outputs that need no CHECK IT.
SCAN_ZERO_OK_STATES = ("zeroed", "not connected", ZERO_SENT_NOT_READ_BACK)


def zero_scan_outputs(steps) -> dict[str, str]:
    """A scan's end on the page's worker (user, 2026-10-18: every scan page
    zeroes its sources at every end, as SHV).  steps: (label, zero) pairs in
    order.  Each zero() is tried whatever the others did.  zero() raises when
    its output is not confirmed at zero (read back where the instrument
    allows), or returns "not connected" when there is nothing to zero, or
    ZERO_SENT_NOT_READ_BACK when it only sent the zero.  It never raises and
    returns {label: "zeroed" | "not connected" | ZERO_SENT_NOT_READ_BACK |
    "zero FAILED: <error>"}, for outputs_zeroed and scan_end_outputs_text."""
    results = {}
    for label, zero in steps:
        try:
            state = zero()
            results[label] = state if state in ("not connected", ZERO_SENT_NOT_READ_BACK) else "zeroed"
        except Exception as error:
            results[label] = f"zero FAILED: {error}"
    return results


def scan_end_outputs_text(results, outputs=(), check: bool = True, together: str = "") -> str:
    """The outputs part of a scan's finish status, from zero_scan_outputs'
    results in zeroing order, generalised from SHV's (user, 2026-10-18):
    "<all> zeroed"; "<all> not confirmed zeroed: check them" when there are
    no results (the zeroing never reported); "zero FAILED: A and B: check
    them" when every one failed; otherwise each in turn, "A zeroed; B zero
    FAILED: check it" ("not connected" is no failure).  outputs: the labels
    in zeroing order, for missing results (a label without one counts as
    failed).  together: how all of them are named at once, "A and B" (or "A,
    B and C") by default.  check=False leaves out ": check it" / ": check
    them" for a status line with more after it; the dialog and the log say
    it in full."""
    def joined(names):
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

    results = dict(results or {})
    names = list(outputs) + [name for name in results if name not in outputs]
    together = together or (joined(names) if names else "the outputs")
    if not results:
        return f"{together} not confirmed zeroed" + ((": check it" if len(names) == 1 else ": check them")
                                                     if check else "")
    states = [results.get(name, "") for name in names]
    if all(state == "zeroed" for state in states):
        return f"{together} zeroed"
    # ZERO_SENT_NOT_READ_BACK is said as it is: neither zeroed nor failed
    # (review, 2026-10-18).
    failed = [name for name, state in zip(names, states) if state not in SCAN_ZERO_OK_STATES]
    if len(names) > 1 and len(failed) == len(names):
        text = "zero FAILED: " + joined(failed)
    else:
        text = "; ".join(f"{name} {state}" if state in SCAN_ZERO_OK_STATES else f"{name} zero FAILED"
                         for name, state in zip(names, states))
    if check and failed:
        text += ": check it" if len(failed) == 1 else ": check them"
    return text


