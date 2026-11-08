"""Pure lock-in settling calculations and formatting for transport measurements."""

from __future__ import annotations

import math
from typing import Any, Iterable

DEFAULT_LOCKIN_SETTLE_TAUS: float = 1.0


def calculate_lockin_settle_s(
    settle_s: float | int,
    time_constants_s: Iterable[Any],
    settle_taus: float | int = DEFAULT_LOCKIN_SETTLE_TAUS,
) -> float:
    """The wait before a transport scan point is read, after its field,
    temperature, angle, current or harmonic changed: the page's Settle s, or
    settle_taus (default 1) time constants of the slowest lock-in the scan
    measures if that is longer.

    Rounded to 1e-12 s, so a product such as 7 x 0.1 s (0.7000000000000001
    in binary, under the earlier 7 x TC rule) reads 0.7 in the CSV's
    effective_settle_s, as the Start confirmation does.
    The shortest SR830 wait, 10 us, keeps every digit.
    """
    slowest = 0.0
    for value in time_constants_s:
        tau = float(value)
        if math.isfinite(tau) and tau > slowest:
            slowest = tau
    return round(max(float(settle_s), float(settle_taus) * slowest), 12)


def format_settle_status_text(seconds: float | int) -> str:
    """The wait before each reading, as a status line shows it: whole
    seconds from 100 s, 3 significant digits below (12345.7 -> "12346",
    0.0864199 -> "0.0864").  With {:g} a typed Settle s such as 12345.7 or
    a small Zurich TC gave six digits and widened the RT-E status line past
    the label, which then cut its end with an ellipsis.  The CSV and the log
    keep the exact value."""
    seconds = float(seconds)
    return f"{seconds:.0f}" if seconds >= 100 else f"{seconds:.3g}"


def format_lockin_settle_text(
    settle_s: Any,
    effective_s: Any,
    slowest_tc_s: Any,
    meter: str,
    settle_taus: Any = DEFAULT_LOCKIN_SETTLE_TAUS,
) -> str:
    """How the PPMS / RT-E wait before each reading was chosen, in words for
    the Start confirmation and the log."""
    if not slowest_tc_s:
        return f"{effective_s:g} s (Settle s)"
    rule_s = settle_taus * slowest_tc_s
    if effective_s > settle_s:
        return (
            f"{effective_s:g} s ({settle_taus:g} x {slowest_tc_s:g} s, the time constant of "
            f"{meter}, the slowest lock-in measured; Settle s is {settle_s:g} s)"
        )
    return (
        f"{effective_s:g} s (Settle s; {settle_taus:g} x the slowest lock-in time constant, "
        f"{slowest_tc_s:g} s on {meter}, is {rule_s:g} s)"
    )
