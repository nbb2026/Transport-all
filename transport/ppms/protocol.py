"""Hardware-independent PPMS command validation and planning utilities."""

from __future__ import annotations

import math

PPMS_TEMPERATURE_MIN_K = 5.0
PPMS_TEMPERATURE_MAX_K = 380.0
PPMS_TEMPERATURE_LOW_BOUNDARY_K = 9.0
PPMS_TEMPERATURE_MAX_RATE_K_MIN = 10.0
PPMS_TEMPERATURE_LOW_MAX_RATE_K_MIN = 1.0

PPMS_FIELD_LIMIT_OE = 89_900.0
PPMS_FIELD_RATE_LIMIT_OE_S = 150.0  # strictly below 150 Oe/s


def validate_ppms_temperature_command(
    target_k: float,
    rate_k_min: float,
    current_k: float | None = None,
) -> tuple[float, float]:
    """Validate PPMS temperature and return (target K, rate K/min).

    Any command whose path enters the 5–9 K interval (inclusive) is limited to
    1 K/min. Commands wholly above 9 K may use up to 10 K/min.
    This conservative whole-ramp limit avoids changing rate mid-ramp.
    """
    target_k = float(target_k)
    rate_k_min = float(rate_k_min)
    if not math.isfinite(target_k) or not math.isfinite(rate_k_min):
        raise ValueError("PPMS target temperature and ramp rate must be finite values")
    if not PPMS_TEMPERATURE_MIN_K <= target_k <= PPMS_TEMPERATURE_MAX_K:
        raise ValueError(
            f"PPMS target temperature must be within {PPMS_TEMPERATURE_MIN_K:g}–"
            f"{PPMS_TEMPERATURE_MAX_K:g} K"
        )
    if rate_k_min <= 0:
        raise ValueError("PPMS temperature ramp rate must be greater than 0 K/min")
    current_valid = current_k is not None and math.isfinite(float(current_k))
    enters_low_range = target_k <= PPMS_TEMPERATURE_LOW_BOUNDARY_K
    if current_valid:
        enters_low_range = enters_low_range or (
            float(current_k) <= PPMS_TEMPERATURE_LOW_BOUNDARY_K
        )
    maximum = (
        PPMS_TEMPERATURE_LOW_MAX_RATE_K_MIN
        if enters_low_range
        else PPMS_TEMPERATURE_MAX_RATE_K_MIN
    )
    if rate_k_min > maximum + 1e-12:
        region = "within the 5–9 K range" if enters_low_range else "above 9 K"
        raise ValueError(
            f"PPMS temperature ramp rate {region} must not exceed {maximum:g} K/min"
        )
    return target_k, rate_k_min


def validate_ppms_field_command(
    target_oe: float,
    rate_oe_s: float,
) -> tuple[float, float]:
    """Validate the PPMS field guardrails used by all field commands."""
    target_oe = float(target_oe)
    rate_oe_s = float(rate_oe_s)
    if not math.isfinite(target_oe) or not math.isfinite(rate_oe_s):
        raise ValueError("PPMS target field and field ramp rate must be finite values")
    if abs(target_oe) > PPMS_FIELD_LIMIT_OE:
        raise ValueError(
            f"PPMS target field must be within ±{PPMS_FIELD_LIMIT_OE:g} Oe"
        )
    if rate_oe_s <= 0 or rate_oe_s >= PPMS_FIELD_RATE_LIMIT_OE_S:
        raise ValueError(
            f"PPMS field ramp rate must be greater than 0 and below "
            f"{PPMS_FIELD_RATE_LIMIT_OE_S:g} Oe/s"
        )
    return target_oe, rate_oe_s


def ppms_scan_temperature_segments(
    current_k: float,
    target_k: float,
    rate_k_min: float,
) -> list[tuple[float, float]]:
    """A scan's temperature change as [(target K, rate K/min)].  The typed
    rate is kept; a segment at or below 9 K is lowered to 1 K/min, never
    raised to it: min(rate, 1) (review, 2026-10-18: a typed 0.5 K/min went
    up to exactly 1.0 there, against the README's "a typed temperature rate
    is kept").  A warm-up from at or below 9 K returns to the typed rate
    during live polling, in the scan worker."""
    current_k, target_k, rate_k_min = float(current_k), float(target_k), float(rate_k_min)
    validate_ppms_temperature_command(target_k, 1.0)
    validate_ppms_temperature_command(10.0, rate_k_min, 10.0)
    if not math.isfinite(current_k):
        raise ValueError("Current temperature readback is invalid; cannot plan the temperature change")
    boundary = PPMS_TEMPERATURE_LOW_BOUNDARY_K
    low_rate = min(rate_k_min, PPMS_TEMPERATURE_LOW_MAX_RATE_K_MIN)
    # Stage slightly above the inclusive low-temperature boundary, so the
    # high-rate command does not itself request a low-temperature target.
    if target_k <= boundary and current_k > boundary + 0.1:
        return [(boundary + 0.1, rate_k_min), (target_k, low_rate)]
    return [(target_k, low_rate if min(current_k, target_k) <= boundary else rate_k_min)]
